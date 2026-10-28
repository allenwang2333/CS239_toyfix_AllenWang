; machine: t32-base
.data 4096
  lui r1, 0x1
  addi r1, r1, -1
  addi r2, r0, 99
  sw r2, 0(r1)
  lw r3, 0(r1)
  out r3
  halt
