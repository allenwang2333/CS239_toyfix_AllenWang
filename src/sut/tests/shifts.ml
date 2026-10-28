// machine: t32-base
// Shifts use the low 5 bits; >> is arithmetic.
var n = -64;
print n >> 2;
print n << 1;
print 1 << 31;
print 1 << 33;
print 1000 >> 3;
print (0 - 1) >> 31;
