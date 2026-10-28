// machine: t32-tiny
// A loop body longer than the 8-bit branch range.
var i = 0;
var s = 0;
while (i < 3) {
  s = s + 1; s = s + 2; s = s + 3; s = s + 4; s = s + 5;
  s = s + 1; s = s + 2; s = s + 3; s = s + 4; s = s + 5;
  s = s + 1; s = s + 2; s = s + 3; s = s + 4; s = s + 5;
  s = s + 1; s = s + 2; s = s + 3; s = s + 4; s = s + 5;
  s = s + 1; s = s + 2; s = s + 3; s = s + 4; s = s + 5;
  s = s + 1; s = s + 2; s = s + 3; s = s + 4; s = s + 5;
  s = s + 1; s = s + 2; s = s + 3; s = s + 4; s = s + 5;
  s = s + 1; s = s + 2; s = s + 3; s = s + 4; s = s + 5;
  i = i + 1;
}
print s;
