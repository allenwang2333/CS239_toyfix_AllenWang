; machine: t32-base
; jal and jalr store the address of the next instruction.
  jal r5, sub
  out r5
  halt
sub:
  addi r6, r0, 9
  out r6
  jalr r0, r5, 0
