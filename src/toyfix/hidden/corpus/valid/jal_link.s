; machine: t32-base
addi r1, r0, 0
  jal r2, f
  out r2
  jal r2, f
  out r2
  halt
f:
  addi r1, r1, 1
  out r1
  jalr r0, r2, 0
