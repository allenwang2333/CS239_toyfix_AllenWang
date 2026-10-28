; machine: t32-base
.data 2
  addi r1, r0, 1
  out r1
  lw r2, 2(r0)
  out r2
  halt
