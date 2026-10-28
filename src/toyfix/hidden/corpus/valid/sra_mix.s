; machine: t32-base
lui r1, 0x80000
  addi r2, r0, 4
  sra r3, r1, r2
  out r3
  srl r3, r1, r2
  out r3
  addi r2, r0, 31
  sra r3, r1, r2
  out r3
  halt
