// machine: t32-tiny
// More nested operands than temporary registers: needs spills.
var a = 1;
print a + (2 + (3 + (4 + (5 + (6 + (7 + (8 + (9 + 10))))))));
print (a - (2 - (3 - (4 - (5 - (6 - (7 - (8 - 9))))))));
