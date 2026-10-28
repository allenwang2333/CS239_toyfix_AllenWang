// machine: t32-tiny
var a = 1071; var b = 462;
while (b != 0) { var t = 0; t = a % b; a = b; b = t; }
print a;
