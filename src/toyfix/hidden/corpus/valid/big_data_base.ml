// machine: t32-base
array big[4000];
var t = 0;
big[3999] = 17; big[2048] = 3; big[2047] = 4;
t = big[3999] * big[2048] + big[2047];
print t;
