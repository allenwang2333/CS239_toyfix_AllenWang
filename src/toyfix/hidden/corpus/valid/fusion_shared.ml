# machine: npu-wide
def main():
    x = iota((4, 9)) - 20
    w = iota((9, 4)) - 18
    y = x @ w + tensor([5, -500, 50, -5])
    r = relu(y)
    print(y)
    print(r)
