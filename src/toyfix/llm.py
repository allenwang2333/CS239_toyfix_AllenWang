"""Chat-completions clients: DeepSeek (OpenAI-compatible HTTP) and a scripted
client for offline tests."""

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"


@dataclass
class Reply:
    content: str
    tool_calls: list[dict]
    reasoning: str = ""
    usage: dict = field(default_factory=dict)


class LLMError(Exception):
    pass


def load_dotenv(start: Path | None = None) -> None:
    """Load KEY=VALUE lines from the nearest .env file into os.environ.
    Existing environment variables win."""
    here = (start or Path.cwd()).resolve()
    for d in [here, *here.parents]:
        env = d / ".env"
        if env.is_file():
            for line in env.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
            return


class ChatClient:
    model = "none"

    def chat(self, messages: list[dict], tools: list[dict]) -> Reply:
        raise NotImplementedError


class DeepSeekClient(ChatClient):
    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, timeout: int = 300, max_retries: int = 4):
        raw_url = (base_url or os.environ.get("TOYFIX_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        if not raw_url.endswith("/v1") and ("localhost" in raw_url or "127.0.0.1" in raw_url or raw_url.startswith("http://")):
            raw_url = f"{raw_url}/v1"
        self.base_url = raw_url
        model_name = model or os.environ.get("TOYFIX_MODEL")
        if not model_name:
            if "localhost" in self.base_url or "127.0.0.1" in self.base_url:
                model_name = "Qwen/Qwen3.8-27B"
            else:
                model_name = DEFAULT_MODEL
        if model_name.lower() in ("qwen", "qwen3.8", "qwen3.8-27b", "qwen-27b", "qwen/qwen3.8-27b"):
            model_name = "Qwen/Qwen3.8-27B"
        self.model = model_name
        self.api_key = api_key or os.environ.get("TOYFIX_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            if "localhost" in self.base_url or "127.0.0.1" in self.base_url:
                self.api_key = "local"
            else:
                raise LLMError("set DEEPSEEK_API_KEY (or TOYFIX_API_KEY) in the environment or .env")
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(self, messages: list[dict], tools: list[dict]) -> Reply:
        body = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
        data = json.dumps(body).encode()
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=data,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.load(resp)
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:500]
                if e.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise LLMError(f"HTTP {e.code}: {detail}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < self.max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise LLMError(f"request failed: {e}") from None
        msg = payload["choices"][0]["message"]
        return Reply(content=msg.get("content") or "", tool_calls=msg.get("tool_calls") or [],
                     reasoning=msg.get("reasoning_content") or msg.get("reasoning") or "",
                     usage=payload.get("usage") or {})


class ScriptedClient(ChatClient):
    """Replays fixed replies. Each script item is either a string (a text
    reply) or a list of (tool_name, args) pairs (one reply with tool calls).
    Used by the offline test suite."""

    model = "scripted"

    def __init__(self, script: list):
        self.script = list(script)
        self.calls = 0
        self.seen: list[list[dict]] = []  # every message list sent, for leak tests

    def chat(self, messages: list[dict], tools: list[dict]) -> Reply:
        self.seen.append([dict(m) for m in messages])
        if not self.script:
            raise LLMError("scripted client has no more replies")
        item = self.script.pop(0)
        self.calls += 1
        if isinstance(item, str):
            return Reply(content=item, tool_calls=[])
        calls = [{"id": f"call_{self.calls}_{i}", "type": "function",
                  "function": {"name": name, "arguments": json.dumps(args)}}
                 for i, (name, args) in enumerate(item)]
        return Reply(content="", tool_calls=calls)
