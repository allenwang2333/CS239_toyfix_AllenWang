; machine: t32-tiny
; A program may use all 256 data words of t32-tiny.
.data 256
  addi r1, r0, 255
  addi r2, r0, 42
  sw r2, 0(r1)
  lw r3, 255(r0)
  out r3
  halt
