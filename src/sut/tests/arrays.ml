// machine: t32-base
// Arrays and loops: first squares, then a reverse copy.
array sq[10];
array rev[10];
var i = 0;
while (i < 10) {
  sq[i] = i * i;
  i = i + 1;
}
i = 0;
while (i < 10) {
  rev[9 - i] = sq[i];
  i = i + 1;
}
print rev[0];
print rev[9];
print sq[3] + rev[3];
