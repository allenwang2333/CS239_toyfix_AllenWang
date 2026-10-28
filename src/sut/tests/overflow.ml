# machine: npu-wide
# 32-bit wraparound in elementwise operations and in matrix products (spec §8.2).
def main():
    big = tensor([[2147483647, 2147483646], [-2147483648, 65536]])
    print(big + 1)
    print(big * big)
    m = tensor([[65536, 65536, 3]])
    print(m @ m.T)
    print(-tensor([-2147483648, 2147483647, -5]))
