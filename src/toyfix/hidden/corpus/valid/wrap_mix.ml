# machine: npu-base
def main():
    a = full((2, 3), 1073741824)
    print(a + a)
    print(a * 4)
    m = tensor([[46341, 46341], [-46341, 46341]])
    print(m @ m)
    print(-full(2, -2147483648) - 1)
