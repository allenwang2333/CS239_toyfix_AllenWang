# machine: npu-base
# Elementwise operations, int operands, and unary minus (spec §8.3, §8.4).
def main():
    a = tensor([[1, 2, 3, 4, 5], [-6, -7, -8, -9, -10]])
    b = iota((2, 5))
    print(a + b)
    print(a - b)
    print(a * b)
    print(a * 3 - 1)
    print(10 - a)
    print(-a)
    v = tensor([4, -5, 6])
    print(v * v + v)
