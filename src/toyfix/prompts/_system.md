## The system under repair

The workspace holds a toolchain for the T32 instruction set and the MiniLang
language. The pipeline is:

MiniLang source -> compiler -> T32 assembly -> assembler -> validator (checks the
hardware profile) -> simulator -> output.

`spec.md` is the specification and the single source of truth. When code or a
test disagrees with the spec, the code or the test is wrong.

The files belong to four repair layers:

- `tests`: `tests/*.ml`, `tests/*.s`, and their `tests/*.expected` files.
- `constraints`: `t32/validator.py`. It checks programs against the hardware
  profiles in `machines/*.toml`.
- `compiler`: `minilang/compiler.py`. It lowers MiniLang to T32 assembly.
- `simulator`: `t32/isa.py`, `t32/assembler.py`, `t32/simulator.py`.

These files are protected. They are correct by definition and are never the root
cause: `spec.md`, `machines/*.toml`, `minilang/parser.py`,
`minilang/reference.py` (the reference interpreter), `cli.py`, `t32/machine.py`.

The spec defines which programs are valid (§4.4, §4.5) and which MiniLang
programs the compiler must accept (§9.2, §9.3). A change that rejects or
restricts a program that the spec says is valid is wrong, even if it makes the
tests pass. A change that accepts a program that the spec says is invalid is
also wrong.
