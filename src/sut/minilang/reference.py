"""Reference interpreter for MiniLang (spec §8).

This is the oracle for MiniLang tests. It does not use the compiler, the IR,
or the simulator. It shares only the frontend walker (parser.py).
"""

from .parser import Domain, Tensor, TensorType, parse, run, to_s32


class _Eval(Domain):
    """Tensor handles are flat row-major lists of signed 32-bit ints."""

    def __init__(self):
        self.output: list[str] = []

    def constant(self, type: TensorType, values: list[int]):
        return list(values) * type.size if len(values) == 1 else list(values)

    def broadcast(self, x: Tensor, type: TensorType):
        return x.handle * type.shape[0]

    def binary(self, op: str, a: Tensor, b: Tensor, type: TensorType):
        f = {"add": lambda x, y: x + y, "sub": lambda x, y: x - y, "mul": lambda x, y: x * y}[op]
        return [to_s32(f(x, y)) for x, y in zip(a.handle, b.handle)]

    def matmul(self, a: Tensor, b: Tensor, type: TensorType):
        (m, k), n = a.type.shape, b.type.shape[1]
        A, B = a.handle, b.handle
        return [to_s32(sum(A[i * k + t] * B[t * n + j] for t in range(k)))
                for i in range(m) for j in range(n)]

    def relu(self, x: Tensor, type: TensorType):
        return [max(v, 0) for v in x.handle]

    def transpose(self, x: Tensor, type: TensorType):
        m, n = x.type.shape
        return [x.handle[i * n + j] for j in range(n) for i in range(m)]

    def print(self, x: Tensor) -> None:
        cols = x.type.shape[-1]
        v = x.handle
        for r in range(0, len(v), cols):
            self.output.append(" ".join(str(e) for e in v[r:r + cols]))


def evaluate(source: str) -> list[str]:
    """Run a program and return its output lines. Raises ParseError for
    invalid programs."""
    program = parse(source)
    ev = _Eval()
    run(program, ev)
    return ev.output
