; machine: t32-base
; blt and bge compare signed values.
  addi r1, r0, -1
  addi r2, r0, 1
  blt r1, r2, less
  addi r3, r0, 0
  out r3
  halt
less:
  addi r3, r0, 1
  out r3
  bge r1, r2, wrong
  out r3
  halt
wrong:
  out r0
  halt
