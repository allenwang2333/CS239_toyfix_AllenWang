; machine: t32-base
addi r1, r0, -1
  add r2, r1, r1
  out r2
  lui r3, 0x7ffff
  addi r3, r3, 2047
  addi r3, r3, 2047
  addi r3, r3, 1
  add r4, r3, r2
  out r3
  out r4
  halt
