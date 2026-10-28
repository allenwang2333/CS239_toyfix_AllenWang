; machine: t32-base
lui r1, 0x80000
  addi r2, r0, 1
  blt r1, r2, a
  out r0
  halt
a:
  addi r3, r0, 1
  out r3
  bge r2, r1, b
  out r0
  halt
b:
  addi r3, r0, 2
  out r3
  sltu r4, r2, r1
  out r4
  slt r4, r2, r1
  out r4
  halt
