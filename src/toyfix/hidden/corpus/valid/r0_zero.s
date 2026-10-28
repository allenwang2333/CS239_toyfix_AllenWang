; machine: t32-base
addi r0, r0, 5
  out r0
  jal r0, next
next:
  out r0
  lui r0, 0x1
  add r1, r0, r0
  out r1
  halt
