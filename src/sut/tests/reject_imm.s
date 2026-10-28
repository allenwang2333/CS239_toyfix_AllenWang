; machine: t32-base
; 2048 does not fit a 12-bit signed immediate.
  addi r1, r0, 2048
  halt
