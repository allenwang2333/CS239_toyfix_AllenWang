# machine: npu-wide
def main():
    x = iota((6, 12)) - 30
    w = iota((12, 10)) * 3 - 170
    b = iota(10) * 100 - 450
    h = relu(x @ w + b)
    print(h)
    print(h @ iota((10, 3)))
