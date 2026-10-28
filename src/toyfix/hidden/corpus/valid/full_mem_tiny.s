; machine: t32-tiny
.data 256
  addi r1, r0, 31
  sw r1, 255(r0)
  sw r1, 0(r0)
  lw r2, 255(r0)
  out r2
  halt
