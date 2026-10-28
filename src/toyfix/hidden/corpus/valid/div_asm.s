; machine: t32-base
lui r1, 0x80000
  addi r2, r0, -1
  div r3, r1, r2
  out r3
  rem r3, r1, r2
  out r3
  addi r4, r0, -9
  addi r5, r0, 4
  div r3, r4, r5
  out r3
  rem r3, r4, r5
  out r3
  halt
