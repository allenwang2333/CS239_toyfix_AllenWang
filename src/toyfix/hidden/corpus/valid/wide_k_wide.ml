# machine: npu-wide
def main():
    x = iota((5, 40)) - 77
    w = iota((40, 7)) - 140
    print(relu(x @ w + iota(7) * 1000))
    print(transpose(x) @ (x @ w))
