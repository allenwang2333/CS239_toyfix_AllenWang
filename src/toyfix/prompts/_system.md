## The system under repair

The workspace holds a toolchain for the NPU, a small tile-based AI
accelerator, and for MiniLang, a small tensor language with Python syntax.
The pipeline is:

MiniLang source -> compiler (frontend -> MLIR-style IR passes -> NPU
assembly) -> NPU assembler -> NPU validator (checks the hardware profile) ->
NPU simulator -> output.

Tests can also start from NPU assembly (`.npu` files).

`spec.md` is the specification and the single source of truth. When code or a
test disagrees with the spec, the code or the test is wrong.

The files belong to four repair layers:

- `tests`: `tests/*.ml`, `tests/*.npu`, and their `tests/*.expected` files.
- `constraints`: `npu/validator.py`. It checks programs against the hardware
  profiles in `machines/*.toml`.
- `compiler`: `minilang/compiler.py`, `minilang/ir.py`, `minilang/passes.py`.
  They lower MiniLang to NPU assembly.
- `simulator`: `npu/isa.py`, `npu/assembler.py`, `npu/simulator.py`.

These files are protected. They are correct by definition and are never the root
cause: `spec.md`, `machines/*.toml`, `minilang/parser.py` (the MiniLang
frontend), `minilang/reference.py` (the reference interpreter), `cli.py`,
`npu/machine.py`.

The spec defines which programs are valid (§4.4, §4.5) and which MiniLang
programs the compiler must accept (§9.2, §9.3). A change that rejects or
restricts a program that the spec says is valid is wrong, even if it makes the
tests pass. A change that accepts a program that the spec says is invalid is
also wrong.
