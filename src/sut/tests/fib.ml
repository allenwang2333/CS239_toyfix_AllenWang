// machine: t32-wide
// Iterative Fibonacci and a conditional.
var a = 0;
var b = 1;
var n = 0;
while (n < 20) {
  var t = 0;
  t = a + b;
  a = b;
  b = t;
  n = n + 1;
}
print a;
if (a % 2 == 1) { print 1; } else { print 0; }
