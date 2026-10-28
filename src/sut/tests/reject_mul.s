; machine: t32-tiny
; t32-tiny has no mul instruction.
  addi r1, r0, 3
  mul r2, r1, r1
  halt
