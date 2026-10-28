; machine: t32-base
; The extreme values of a 12-bit immediate are valid.
  addi r1, r0, -2048
  out r1
  addi r1, r0, 2047
  out r1
  halt
