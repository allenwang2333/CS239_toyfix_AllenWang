; machine: t32-base
; Arithmetic and logical right shifts of a negative value.
  addi r1, r0, -8
  addi r2, r0, 1
  sra r3, r1, r2
  out r3
  srl r3, r1, r2
  out r3
  addi r2, r0, 33
  sra r3, r1, r2
  out r3
  halt
