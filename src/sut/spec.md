# NPU and MiniLang Specification

This document is the single source of truth for the NPU accelerator, its
hardware profiles, the MiniLang language and its compiler, and the test
format. When code or a test disagrees with this document, the code or the test
is wrong.

Sections 1 to 6 define the NPU. Sections 7 to 9 define MiniLang and its
compiler. Section 10 defines the tests.

## 1. Machine state

1.1. The NPU has a DRAM of `data_words` 32-bit words (§6.2), addressed
`0 .. data_words-1`, and a scratchpad (SPAD) of `spad_words` 32-bit words
(§4), addressed `0 .. spad_words-1`.

1.2. All words start as 0, except the DRAM words that `.word` sets (§6.3).

1.3. All values are signed 32-bit two's complement integers. Every result is
reduced modulo 2^32 (wraparound). There is no overflow trap.

1.4. The NPU has no registers and no branches. It runs each instruction once,
in program order, and stops after the last instruction.

## 2. Operands and matrices

2.1. All operands are non-negative integers. `spad`, `dst`, `a`, and `b` are
scratchpad addresses. `dram` is a DRAM address. `rows`, `cols`, `m`, `k`,
`n`, and `len` are counts. `rstride` and `cstride` are DRAM strides.

2.2. A matrix in the scratchpad is dense and row-major: element (r, c) of an
R x C matrix at address p is at `p + r*C + c`.

2.3. A matrix in DRAM is a strided view: element (r, c) is at
`dram + r*rstride + c*cstride`. A stride of 0 reads the same words again. For
example, `rstride = 0` repeats one row, and a transposed matrix is read with
`rstride = 1` and `cstride` = the row length.

## 3. Instruction semantics

3.1. Instructions (r < rows, c < cols, i < len):

| Instruction | Semantics |
|---|---|
| `load spad, dram, rows, cols, rstride, cstride` | `spad[spad + r*cols + c] = dram[dram + r*rstride + c*cstride]` |
| `store dram, spad, rows, cols, rstride` | `dram[dram + r*rstride + c] = spad[spad + r*cols + c]` |
| `mm dst, a, b, m, k, n` | D = A x B, where A is the m x k matrix at a, B is the k x n matrix at b, and D is the m x n matrix at dst |
| `mma dst, a, b, m, k, n` | D = D + A x B |
| `vadd dst, a, b, len` | `spad[dst + i] = spad[a + i] + spad[b + i]` |
| `vsub dst, a, b, len` | `spad[dst + i] = spad[a + i] - spad[b + i]` |
| `vmul dst, a, b, len` | `spad[dst + i] = spad[a + i] * spad[b + i]` (low 32 bits) |
| `vrelu dst, a, len` | `spad[dst + i] = max(spad[a + i], 0)` |
| `out dram, rows, cols, rstride, cstride` | for each r, output one line with the values `dram[dram + r*rstride + c*cstride]` for c = 0 .. cols-1, in signed decimal, separated by one space |

3.2. An instruction reads all of its inputs before it writes its result, so
the ranges may overlap.

3.3. Example values: `mm` of [[1, 2], [3, 4]] by itself gives
[[7, 10], [15, 22]]. `vmul` of 65536 by 65536 gives 0. `vrelu` of -5 gives 0.

## 4. Hardware profiles and validity

4.1. A hardware profile is a file `machines/<name>.toml` with these keys:

| Key | Meaning |
|---|---|
| `mm_shape` | `[M, K, N]`: the largest `m`, `k`, and `n` of `mm` and `mma` (the shape of the matrix unit) |
| `vlen` | the largest `len` of a vector instruction |
| `has_mma` | `true` if the `mma` instruction exists |
| `stride_bits` | width of the unsigned `rstride` field of `load` and `store` |
| `dma_align` | the DRAM address of every `load` and `store` must be a multiple of this |
| `spad_words` | number of scratchpad words |
| `dram_words` | number of DRAM words |

4.2. An unsigned field of width w accepts every value v with
`0 <= v <= 2^w - 1`. For example, with `stride_bits = 4` the value 15 is
valid and 16 is invalid.

4.3. Only `rstride` has a width limit. `cstride`, and the strides of `out`,
have no limit.

4.4. A program is **valid** for a profile if and only if all of these are
true:

- (a) every instruction is one of §3.1 with the correct number of operands;
- (b) for `mm` and `mma`: `1 <= m <= M`, `1 <= k <= K`, and `1 <= n <= N`,
  where `mm_shape = [M, K, N]`;
- (c) `mma` is used only if `has_mma` is true;
- (d) for `vadd`, `vsub`, `vmul`, and `vrelu`: `1 <= len <= vlen`;
- (e) for `load`, `store`, and `out`: `rows >= 1` and `cols >= 1`. For `load`
  and `store`, `rstride` fits `stride_bits` (§4.2);
- (f) for `load` and `store`: `dram` is a multiple of `dma_align`. Scratchpad
  addresses and the address of `out` need no alignment;
- (g) every scratchpad word that an instruction reads or writes is in
  `0 .. spad_words-1`. `load` and `store` use `rows*cols` words at `spad`.
  `mm` and `mma` use `m*n` words at `dst`, `m*k` words at `a`, and `k*n` words
  at `b`. A vector instruction uses `len` words at each of `dst`, `a`, and `b`
  (`vrelu` has no `b`);
- (h) every DRAM word that an instruction reads or writes is in
  `0 .. data_words-1`. For `load` and `out`, the largest address is
  `dram + (rows-1)*rstride + (cols-1)*cstride`. For `store`, it is
  `dram + (rows-1)*rstride + cols-1`;
- (i) `data_words <= dram_words`, and every word that `.word` sets is in
  `0 .. data_words-1`. A program that uses exactly `dram_words` words is
  valid.

4.5. The validator must reject a program if and only if §4.4 is false. It
must not reject a program for any other reason.

4.6. Profiles shipped with the toolchain:

| Profile | mm_shape | vlen | has_mma | stride_bits | dma_align | spad_words | dram_words |
|---|---|---|---|---|---|---|---|
| `npu-tiny` | [2, 2, 2] | 2 | false | 4 | 2 | 16 | 256 |
| `npu-base` | [4, 4, 4] | 8 | true | 8 | 4 | 64 | 4096 |
| `npu-wide` | [8, 16, 4] | 64 | true | 16 | 4 | 256 | 65536 |

Every profile also satisfies these two conditions, which the compiler needs:
`spad_words >= M*K + K*N + 2*M*N`, and `dma_align` divides M, K, and N.

## 5. Traps

5.1. The simulator stops with a trap when one of these happens:

| Reason | Condition |
|---|---|
| `spad_out_of_range` | a scratchpad address is outside `0 .. spad_words-1` |
| `dram_out_of_range` | a DRAM address is outside `0 .. data_words-1` |
| `step_limit` | the number of executed instructions reaches the step limit |

5.2. Valid programs never get the first two traps. Output produced before a
trap is kept.

## 6. Program file format

6.1. NPU assembly has one instruction per line. `;` starts a comment.
Operands are separated by commas and are decimal or `0x` hexadecimal.

6.2. The directive `.data N` sets `data_words = N`. The default is 0.

6.3. The directive `.word ADDR, V0, V1, ...` sets DRAM word `ADDR + i` to `Vi`
when the program starts. Each `Vi` is in `-2^31 .. 2^32-1` and is reduced to
32 bits.

6.4. The assembler rejects an unknown instruction, a wrong number of
operands, and a negative operand. It does not check the hardware profile.

## 7. MiniLang syntax

7.1. A MiniLang program is a Python source file that uses only the subset in
this section. Python syntax rules apply: indentation, `#` comments, and
operator precedence and associativity. A Python syntax error is an error.

7.2. The top level contains only function definitions (`def`) and string
docstrings. One function must be `main`. `main` has no parameters and returns
no value.

7.3. A function definition is `def NAME(P1: T1, P2: T2, ...) -> R:`. Every
parameter needs a type annotation. A type is `int`, `Tensor[N, i32]` (rank 1),
or `Tensor[M, N, i32]` (rank 2). Dimensions are positive integer literals.
The return annotation `-> R` is optional. `-> None` means that the function
returns no value. Default values, `*args`, keyword parameters, and decorators
are errors. A function name must not be defined twice and must not be a
builtin name (§7.5).

7.4. Statements:

| Statement | Meaning |
|---|---|
| `NAME = EXPR` | assign a value to a name |
| `NAME += EXPR` (also `-=`, `*=`, `@=`) | `NAME = NAME op EXPR` |
| `print(EXPR)` | output a value (§8.10) |
| `for NAME in range(A)`, `range(A, B)`, `range(A, B, C)` | loop; A, B, C are ints; C is not 0; no `else` |
| `return EXPR`, `return` | only as the last statement of a function body, not in a loop |
| `pass`, a string docstring | no effect |

All other statements (for example `if`, `while`, `import`) are errors.

7.5. Expressions:

- integer literals in `0 .. 2^32-1`, reduced modulo 2^32 to a signed 32-bit
  value. `True`, `False`, floats, and strings are errors;
- names;
- `A + B`, `A - B`, `A * B`, `A @ B`, `-A`, `+A`, and `X.T`;
- calls of user functions and of these builtins: `relu(X)`, `transpose(X)`,
  `tensor(LIST)`, `zeros(SHAPE)`, `ones(SHAPE)`, `full(SHAPE, V)`, and
  `iota(SHAPE)`.

A SHAPE is an int, or a tuple of one or two ints. Every dimension must be at
least 1. `tensor` takes a list literal of int expressions (rank 1), or a list
literal of list literals of the same non-zero length (rank 2). Keyword
arguments are errors. Every other expression (for example `/`, indexing, or
`.shape`) is an error.

## 8. MiniLang semantics

8.1. A value is an int or a tensor. An int is a signed 32-bit integer. A
tensor has rank 1 or 2, a fixed shape, and signed 32-bit elements.

8.2. All int arithmetic and all tensor element arithmetic wraps modulo 2^32,
the same as NPU arithmetic (§1.3). This includes the sums in `@`.

8.3. `+`, `-`, and `*` on two ints give an int. If one operand is a tensor,
they work element by element and give a tensor.

8.4. Broadcasting. If one operand is an int, it is used as a tensor of the
shape of the other operand with that value in every element. If one operand
has shape [N] and the other has shape [M, N], the rank-1 operand is used for
every row: element (i, j) uses element j of the rank-1 operand. The shapes of
the two operands must then be equal. Any other shape pair is an error.

8.5. `A @ B` needs two rank-2 tensors with shapes [M, K] and [K, N]. The
result has shape [M, N] and element (i, j) is the sum of `A[i][k] * B[k][j]`
for k = 0 .. K-1. `relu(X)` is `max(x, 0)` for each element. `-X` is `0 - X`
and `+X` is `X`.

8.6. `transpose(X)` and `X.T` need a rank-2 tensor with shape [M, N]. The
result has shape [N, M] and element (j, i) is element (i, j) of X.

8.7. `zeros(S)`, `ones(S)`, and `full(S, V)` give a tensor of shape S with all
elements 0, 1, or V. `iota(S)` gives a tensor of shape S with the elements
0, 1, 2, ... in row-major order. `tensor(LIST)` gives the tensor that the list
literal shows.

8.8. Names. Every function call has its own names. There are no global names.
A name must be assigned before it is used. A name can be assigned again with
a value of any type. The name of a function or a builtin cannot be assigned. A call gives each parameter the value of its argument.
The number of arguments must equal the number of parameters, and each
argument type must equal the parameter annotation exactly (an int for `int`,
a tensor of exactly that shape for `Tensor[...]`). If a function has a return
annotation, its result must have that type. A call of a function that returns
no value cannot be used in an expression. Recursion is an error. A `for` loop
assigns each value of the range to its name. The name keeps the last value
after the loop.

8.9. All ints are known before the program runs. Calls are inlined and loops
are unrolled. A program that executes more than 100000 statements and calls
in total is an error.

8.10. `print(X)` outputs a rank-2 tensor as one line per row, a rank-1 tensor
as one line, and an int as one line. A line holds the signed decimal values,
separated by one space.

8.11. MiniLang has no runtime errors. All errors in §7 and §8 are found
before the program runs.

## 9. Compiler requirements

9.1. The compiler translates a MiniLang program to NPU assembly for a given
profile. The output must be valid for that profile (§4.4) and must produce the
same output as the MiniLang semantics (§8).

9.2. The compiler must accept every valid MiniLang program that satisfies
§9.3, on every profile. In particular:

- (a) every tensor shape must compile, also when a dimension is not a
  multiple of a side of `mm_shape`. The last tile of such a dimension is
  smaller;
- (b) `@` of any size must compile. When K is larger than the K of
  `mm_shape`, the products of all K tiles are added together. On a profile
  without `mma`, the compiler adds them with `mm` and `vadd`;
- (c) vector work longer than `vlen` must compile, by more than one vector
  instruction;
- (d) a DRAM row stride that does not fit `stride_bits` must compile, for
  example with one `load` or `store` per row;
- (e) every DMA address must be a multiple of `dma_align`. The compiler may
  pad rows and buffers to meet this;
- (f) transposed and broadcast operands must compile. The compiler may read
  them with DMA strides instead of copying them;
- (g) a value that is used more than once must have the same value at each
  use.

9.3. The size of a tensor value with shape [R, C] is `R * round_up(C, A)`,
and the size of a value with shape [C] is `round_up(C, A)`, where A is
`dma_align`. Let S be the total size of all tensor values that the program
computes: the result of every operation, every constructor and literal, and
every int operand that is broadcast to a tensor (§8.4). If
S <= `dram_words`, the compiler must accept the program. The compiler may
report an error only for an invalid program (§7, §8), or for a program that
needs more than `dram_words` DRAM words.

9.4. The compiler works in stages. `python3 cli.py ir FILE --stage STAGE`
prints the intermediate representation (IR) after a stage, in MLIR generic
syntax:

| Stage | Result |
|---|---|
| `frontend` | `ml` dialect: one operation per tensor operation of §8, on value-semantic `tensor<...xi32>` types |
| `canonicalize` | the same program after algebraic folding (for example `x + 0`, `x * 1`, operations on all-equal constants), common subexpression elimination, and dead code elimination |
| `fuse` | `ml.matmul` followed by a bias `ml.add` and `ml.relu` becomes one `ml.linear` operation, when the intermediate values have no other uses |
| `bufferize` | every value has a DRAM layout, a `memref<...xi32, strided<[...], offset: ...>>`. Rows and buffers are padded to `dma_align`. Transposes, broadcasts, and all-equal constants are strided views. The DRAM of a tensor can be used again after its last use |
| `lower-npu` | `npu` dialect: one operation per NPU instruction, plus `npu.data` for the initial DRAM contents |

These stages are optimizations. They must not change the output (§9.1) and
must not cause an error that §9.3 does not allow.

## 10. Test format

10.1. A test is a file `tests/<name>.ml` (MiniLang) or `tests/<name>.npu`
(NPU assembly), and a file `tests/<name>.expected`.

10.2. The first line of the test source names the profile:
`# machine: <profile>` for MiniLang, or `; machine: <profile>` for assembly.

10.3. The test runner compiles (MiniLang only), assembles, validates, and runs
the program with a step limit of 200000. The actual result is:

- the program output lines, if the program ends normally;
- the output lines followed by `<trap: REASON>`, if the program traps;
- `<rejected>`, if the assembler or the validator rejects the program;
- `<compile error>`, if the compiler reports an error.

10.4. A test passes if the actual result equals the content of the
`.expected` file, ignoring trailing whitespace.

10.5. The expected result of a MiniLang test must equal the result of the
MiniLang semantics (§8), which the reference interpreter implements.
