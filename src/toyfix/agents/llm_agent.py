"""Tool-use loop shared by the LLM agents."""

import json
from dataclasses import dataclass

from ..context import EpisodeContext
from ..layers import PROMPTS_DIR
from ..llm import ChatClient, LLMError
from ..tools import TOOLS, call_tool, tools_for


@dataclass
class AgentSpec:
    name: str
    role: str
    prompt_file: str
    finish_tool: str
    tool_budget: int = 30
    max_turns: int = 45

    @property
    def system_prompt(self) -> str:
        """The full system prompt: the role prompt with the shared description
        of the toolchain inserted at {{SYSTEM}}."""
        shared = (PROMPTS_DIR / "_system.md").read_text().strip()
        return (PROMPTS_DIR / self.prompt_file).read_text().replace("{{SYSTEM}}", shared)


DIAGNOSER = AgentSpec("Diagnoser", "diagnoser", "diagnoser.md", "submit_diagnosis", 25)
REPAIR = AgentSpec("Repair Agent", "repair", "repair.md", "submit_patch", 30)
REVIEWER = AgentSpec("Reviewer", "reviewer", "reviewer.md", "submit_review", 20)
SOLO = AgentSpec("Solo Agent", "solo", "solo.md", "submit_patch", 45, 60)


def run_agent(spec: AgentSpec, client: ChatClient, ctx: EpisodeContext, task: str) -> dict | None:
    """Run one agent until it calls its finish tool. Return the finish-tool
    arguments, or None if the agent stops without finishing."""
    tools = tools_for(spec.role, ctx)
    schemas = [t.schema() for t in tools]
    messages = [{"role": "system", "content": spec.system_prompt},
                {"role": "user", "content": task}]
    ctx.agent_tool_calls = 0
    ctx.agent_tool_budget = spec.tool_budget
    ctx.log.emit("agent_start", agent=spec.name, role=spec.role, model=client.model,
                 tools=[t.name for t in tools], summary=f"attempt {ctx.attempt}", task=task)
    nudges = 0
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    result = None
    stop = "max_turns"
    for _ in range(spec.max_turns):
        try:
            reply = client.chat(messages, schemas)
        except LLMError as e:
            stop = f"llm_error: {e}"
            break
        for k in usage:
            usage[k] += int(reply.usage.get(k, 0) or 0)
        ctx.log.emit("llm_turn", agent=spec.name, content=reply.content,
                     reasoning=reply.reasoning[:4000],
                     tool_calls=[c["function"]["name"] for c in reply.tool_calls],
                     usage=reply.usage)
        msg = {"role": "assistant", "content": reply.content}
        if reply.reasoning:
            msg["reasoning_content"] = reply.reasoning
        if reply.tool_calls:
            msg["tool_calls"] = reply.tool_calls
        messages.append(msg)

        if not reply.tool_calls:
            nudges += 1
            if nudges > 2:
                stop = "no_tool_calls"
                break
            messages.append({"role": "user", "content":
                             f"Continue with your tools. Finish by calling {spec.finish_tool}."})
            continue

        for call in reply.tool_calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
            except (json.JSONDecodeError, ValueError) as e:
                res_text, ok, data = f"ERROR: invalid JSON arguments: {e}", False, None
            else:
                res = call_tool(ctx, spec.role, spec.name, name, args)
                res_text, ok, data = res.text, res.ok, res.data
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": res_text})
            if ok and name == spec.finish_tool and TOOLS[name].finish:
                result = data
        if result is not None:
            stop = "finished"
            break
        if ctx.agent_tool_calls >= spec.tool_budget + 3:
            stop = "budget"
            break
    ctx.log.emit("agent_end", agent=spec.name, stop=stop, usage=usage,
                 tool_calls=ctx.agent_tool_calls,
                 summary=f"{stop}: {json.dumps(result)[:300] if result else ''}", result=result)
    return result
