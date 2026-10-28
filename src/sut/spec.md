# T32 and MiniLang Specification

This document is the single source of truth for the T32 instruction set, the
hardware profiles, the MiniLang language, and the test format. When code or a
test disagrees with this document, the code or the test is wrong.

## 1. Machine state

1.1. T32 has 32-bit registers `r0` to `r(N-1)`. N is `num_regs` from the
hardware profile (§4).

1.2. `r0` always reads as 0. A write to `r0` has no effect.

1.3. All register values are 32-bit two's complement integers. Every
arithmetic result is reduced modulo 2^32 (wraparound). There is no overflow
trap.

1.4. Instruction memory and data memory are separate. The program counter
`pc` is an instruction index. Execution starts at `pc = 0`.

1.5. Data memory has `mem_words` 32-bit words, addressed by word index
`0 .. mem_words-1`. All words start as 0.

1.6. The program also declares `data_words` (§6). This is the number of data
words that the program is allowed to use.

## 2. Encoding

2.1. Every instruction is one 32-bit word. Bits `[31:26]` hold the opcode.

2.2. Formats (field positions are bit ranges, immediates are two's complement
unless noted):

| Format | Fields |
|---|---|
| R | op[31:26] rd[25:22] rs1[21:18] rs2[17:14] |
| I | op[31:26] rd[25:22] rs1[21:18] imm[17:0] (signed, 18 bits) |
| S | op[31:26] rs2[25:22] rs1[21:18] imm[17:0] (signed, 18 bits) |
| B | op[31:26] rs1[25:22] rs2[21:18] off[17:0] (signed, 18 bits) |
| U | op[31:26] rd[25:22] imm[21:0] (unsigned, 22 bits) |
| J | op[31:26] rd[25:22] off[21:0] (signed, 22 bits) |
| O | op[31:26] rs1[21:18] |
| N | op[31:26] |

2.3. The encoding fields are wider than most hardware profiles allow. The
assembler only rejects values that do not fit the encoding field. The
validator (§4) rejects values that do not fit the hardware profile.

## 3. Instruction semantics

3.1. Notation: `sext(x)` is the signed value of an immediate. `s(x)` is the
signed 32-bit value of a register, `u(x)` is the unsigned 32-bit value.

| Mnemonic | Fmt | Opcode | Semantics |
|---|---|---|---|
| `add rd, rs1, rs2` | R | 0x01 | rd = rs1 + rs2 |
| `sub rd, rs1, rs2` | R | 0x02 | rd = rs1 - rs2 |
| `and rd, rs1, rs2` | R | 0x03 | rd = rs1 & rs2 |
| `or rd, rs1, rs2` | R | 0x04 | rd = rs1 \| rs2 |
| `xor rd, rs1, rs2` | R | 0x05 | rd = rs1 ^ rs2 |
| `sll rd, rs1, rs2` | R | 0x06 | rd = rs1 << (rs2 & 31) |
| `srl rd, rs1, rs2` | R | 0x07 | rd = u(rs1) >> (rs2 & 31), zero fill |
| `sra rd, rs1, rs2` | R | 0x08 | rd = s(rs1) >> (rs2 & 31), sign fill |
| `slt rd, rs1, rs2` | R | 0x09 | rd = 1 if s(rs1) < s(rs2) else 0 |
| `sltu rd, rs1, rs2` | R | 0x0A | rd = 1 if u(rs1) < u(rs2) else 0 |
| `mul rd, rs1, rs2` | R | 0x0B | rd = low 32 bits of rs1 * rs2 |
| `div rd, rs1, rs2` | R | 0x0C | rd = s(rs1) / s(rs2), truncated toward zero |
| `rem rd, rs1, rs2` | R | 0x0D | rd = s(rs1) - s(rs2) * div(rs1, rs2); the sign follows rs1 |
| `addi rd, rs1, imm` | I | 0x10 | rd = rs1 + sext(imm) |
| `andi rd, rs1, imm` | I | 0x11 | rd = rs1 & sext(imm) |
| `ori rd, rs1, imm` | I | 0x12 | rd = rs1 \| sext(imm) |
| `xori rd, rs1, imm` | I | 0x13 | rd = rs1 ^ sext(imm) |
| `slti rd, rs1, imm` | I | 0x14 | rd = 1 if s(rs1) < sext(imm) else 0 |
| `sltiu rd, rs1, imm` | I | 0x15 | rd = 1 if u(rs1) < u(sext(imm)) else 0 |
| `lw rd, imm(rs1)` | I | 0x16 | rd = mem[rs1 + sext(imm)] |
| `jalr rd, rs1, imm` | I | 0x17 | t = rs1 + sext(imm); rd = pc + 1; pc = t |
| `sw rs2, imm(rs1)` | S | 0x18 | mem[rs1 + sext(imm)] = rs2 |
| `beq rs1, rs2, off` | B | 0x20 | if rs1 == rs2: pc = pc + off |
| `bne rs1, rs2, off` | B | 0x21 | if rs1 != rs2: pc = pc + off |
| `blt rs1, rs2, off` | B | 0x22 | if s(rs1) < s(rs2): pc = pc + off |
| `bge rs1, rs2, off` | B | 0x23 | if s(rs1) >= s(rs2): pc = pc + off |
| `lui rd, imm` | U | 0x28 | rd = imm << 12 (low 32 bits) |
| `jal rd, off` | J | 0x30 | rd = pc + 1; pc = pc + off |
| `out rs1` | O | 0x3E | append the decimal value of s(rs1) and a newline to the output |
| `halt` | N | 0x3F | stop execution |

3.2. Branch and jump offsets are relative to the address of the branch or
jump instruction itself. An offset of 0 jumps to the same instruction.

3.3. If no branch or jump is taken, `pc = pc + 1`.

3.4. Division by zero (`div` or `rem` with rs2 = 0) traps with reason
`div_by_zero`. `div` of -2^31 by -1 gives -2^31. `rem` of -2^31 by -1 gives 0.

3.5. Example values: `div` of -7 by 2 is -3. `rem` of -7 by 2 is -1.
`sra` of -8 by 1 is -4. `srl` of -8 by 1 is 2147483644.

## 4. Hardware profiles and validity

4.1. A hardware profile is a file `machines/<name>.toml` with these keys:

| Key | Meaning |
|---|---|
| `num_regs` | number of registers N; valid registers are r0 .. r(N-1) |
| `imm_bits` | width of the signed immediate for I-type and S-type instructions |
| `branch_bits` | width of the signed offset for B-type instructions |
| `jump_bits` | width of the signed offset for `jal` |
| `mem_words` | number of data memory words |
| `has_mul` | `true` if the `mul` instruction exists |

4.2. A signed field of width w accepts every value v with
`-2^(w-1) <= v <= 2^(w-1) - 1`. For example, with `imm_bits = 12` the
values -2048 and 2047 are valid, and -2049 and 2048 are invalid.

4.3. The `lui` immediate must satisfy `0 <= imm <= 2^20 - 1` on every profile.

4.4. A program is **valid** for a profile if and only if all of these are
true:

- (a) every instruction word has a defined opcode;
- (b) every register field that the instruction uses names a register
  below `num_regs`;
- (c) every I-type and S-type immediate fits `imm_bits` (§4.2);
- (d) every B-type offset fits `branch_bits`, and every `jal` offset fits
  `jump_bits`;
- (e) every B-type and `jal` target address is in `0 .. len(program)-1`;
- (f) `mul` is used only if `has_mul` is true;
- (g) `data_words <= mem_words`. A program that uses exactly `mem_words`
  words is valid.

4.5. The validator must reject a program if and only if §4.4 is false. It
must not reject a program for any other reason.

4.6. Profiles shipped with the toolchain:

| Profile | num_regs | imm_bits | branch_bits | jump_bits | mem_words | has_mul |
|---|---|---|---|---|---|---|
| `t32-base` | 16 | 12 | 12 | 22 | 4096 | true |
| `t32-tiny` | 8 | 12 | 8 | 16 | 256 | false |
| `t32-wide` | 16 | 16 | 16 | 22 | 65536 | true |

## 5. Traps

5.1. The simulator stops with a trap when one of these happens:

| Reason | Condition |
|---|---|
| `div_by_zero` | §3.4 |
| `mem_out_of_range` | a load or store address is outside `0 .. data_words-1` |
| `pc_out_of_range` | `pc` is outside the program |
| `illegal_instruction` | the opcode is not defined |
| `step_limit` | the number of executed instructions reaches the step limit |

5.2. Output produced before a trap is kept.

## 6. Program file format

6.1. Assembly source is one instruction per line. `;` starts a comment.
A line `name:` defines a label. Registers are written `r0` .. `r15`.
Immediates are decimal or `0x` hexadecimal and may be negative.

6.2. The directive `.data N` sets `data_words = N`. The default is 0.

6.3. Branch and jump operands may be a label or a numeric offset.

## 7. MiniLang syntax

```
program := stmt*
stmt    := "var" IDENT ("=" expr)? ";"
         | "array" IDENT "[" INT "]" ";"
         | IDENT "=" expr ";"
         | IDENT "[" expr "]" "=" expr ";"
         | "print" expr ";"
         | "if" "(" expr ")" block ("else" block)?
         | "while" "(" expr ")" block
block   := "{" stmt* "}"
expr    := binary expression with the precedence below
primary := INT | IDENT | IDENT "[" expr "]" | "(" expr ")"
```

7.1. Operator precedence, from lowest to highest. All binary operators are
left associative.

| Level | Operators |
|---|---|
| 1 | `\|` |
| 2 | `^` |
| 3 | `&` |
| 4 | `==` `!=` |
| 5 | `<` `<=` `>` `>=` |
| 6 | `<<` `>>` |
| 7 | `+` `-` |
| 8 | `*` `/` `%` |
| 9 | unary `-` `!` `~` |

7.2. Comments start with `//` and end at the end of the line.

7.3. An integer literal is decimal and must be in `0 .. 2^32-1`. It is
reduced modulo 2^32 to a 32-bit value.

## 8. MiniLang semantics

8.1. All values are 32-bit two's complement integers with wraparound, the same
as T32 registers (§1.3).

8.2. All variables and arrays are global. A name must be declared before it
is used (in program text order) and may be declared only once. A `var`
statement sets the variable each time it runs; `var x;` sets x to 0. An
`array` statement has no runtime effect. Array elements start as 0.

8.3. `/` and `%` have the semantics of `div` and `rem` (§3.1, §3.4). Division
by zero is a runtime error with reason `div_by_zero`.

8.4. `<<` uses the low 5 bits of the right operand. `>>` is an arithmetic
(sign-filling) shift and uses the low 5 bits of the right operand.

8.5. Comparison operators and `!` give 1 for true and 0 for false. `~` is
bitwise not. Unary `-` is negation with wraparound.

8.6. `if` and `while` treat any nonzero value as true.

8.7. `print e;` outputs the signed decimal value of e and a newline.

8.8. An array index outside `0 .. size-1` is undefined behavior. Valid
programs never do this.

## 9. Compiler requirements

9.1. The compiler translates MiniLang to T32 assembly for a given hardware
profile. The output must be valid for that profile (§4.4) and must produce
the same output as the MiniLang semantics (§8).

9.2. The compiler must accept every syntactically valid MiniLang program
whose variables, arrays, and compiler temporaries fit in `mem_words`. In
particular:

- (a) every 32-bit integer constant must compile, on every profile. Constants
  that do not fit `imm_bits` are built with `lui` and `addi`;
- (b) expressions of any depth must compile. When temporary registers run
  out, the compiler spills values to data memory;
- (c) `if` and `while` bodies of any length must compile. When a branch
  offset does not fit `branch_bits`, the compiler uses an inverted branch over
  a `jal`;
- (d) `*` must compile on profiles without `mul`, by a software routine;
- (e) data addresses that do not fit `imm_bits` must compile, by building the
  address in a register.

9.3. The compiler may report an error only for a syntax error, a semantic
error from §8.2, a program that needs more than `mem_words` data words, or a
program so long that a `jal` offset does not fit `jump_bits`.

## 10. Test format

10.1. A test is a file `tests/<name>.ml` (MiniLang) or `tests/<name>.s`
(assembly) and a file `tests/<name>.expected`.

10.2. The first line of the test source names the profile:
`// machine: <profile>` for MiniLang or `; machine: <profile>` for assembly.

10.3. The test runner compiles (MiniLang only), assembles, validates, and runs
the program with a step limit of 200000. The actual result is:

- the program output lines, if the program halts normally;
- the output lines followed by `<trap: REASON>`, if the program traps;
- `<rejected>`, if the assembler or the validator rejects the program;
- `<compile error>`, if the compiler reports an error.

10.4. A test passes if the actual result equals the content of the
`.expected` file, ignoring trailing whitespace.

10.5. The expected result of a MiniLang test must equal the result of the
MiniLang semantics (§8), which the reference interpreter implements.
