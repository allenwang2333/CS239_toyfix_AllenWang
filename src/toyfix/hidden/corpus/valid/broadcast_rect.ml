# machine: npu-base
def main():
    m = iota((3, 6)) - 4
    v = tensor([10, -20, 30, -40, 50, -60])
    print(m + v)
    print(v - m)
    print(m * v + 1)
