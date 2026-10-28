// machine: t32-wide
var n = 2; var count = 0;
while (n < 200) {
  var d = 2; var prime = 1;
  d = 2; prime = 1;
  while (d * d <= n) { if (n % d == 0) { prime = 0; } d = d + 1; }
  count = count + prime;
  n = n + 1;
}
print count;
