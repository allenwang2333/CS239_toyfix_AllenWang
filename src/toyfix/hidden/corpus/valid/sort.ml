// machine: t32-base
array a[8];
a[0] = 5; a[1] = -3; a[2] = 9; a[3] = 0; a[4] = -8; a[5] = 2; a[6] = 7; a[7] = 1;
var i = 0;
while (i < 8) {
  var j = 0;
  j = 0;
  while (j < 7 - i) {
    if (a[j] > a[j + 1]) { var t = 0; t = a[j]; a[j] = a[j + 1]; a[j + 1] = t; }
    j = j + 1;
  }
  i = i + 1;
}
i = 0;
while (i < 8) { print a[i]; i = i + 1; }
