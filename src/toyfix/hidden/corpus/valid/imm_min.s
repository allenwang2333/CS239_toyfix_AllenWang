; machine: t32-base
.data 4
  addi r1, r0, -2048
  out r1
  andi r2, r1, -2048
  out r2
  ori r3, r0, -2048
  out r3
  addi r4, r0, 2047
  addi r4, r4, 3
  sw r1, -2048(r4)
  lw r5, -2047(r4)
  out r5
  halt
