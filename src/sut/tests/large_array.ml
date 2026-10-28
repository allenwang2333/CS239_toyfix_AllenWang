// machine: t32-base
// Data addresses above 2047 need a register base.
array buf[3000];
var last = 7;
buf[0] = 11;
buf[2999] = 22;
buf[2500] = buf[0] + buf[2999];
print buf[2500];
print last;
