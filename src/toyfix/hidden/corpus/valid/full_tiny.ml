// machine: t32-tiny
array a[240];
var i = 0;
while (i < 240) { a[i] = i; i = i + 1; }
print a[239] + a[0] + a[120];
