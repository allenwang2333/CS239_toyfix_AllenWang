# machine: npu-base
def main():
    x = iota((3, 5)) - 7
    print(x + 0)
    print(x * 1 - 0)
    print(x * 0)
    print(relu(relu(x)))
    print(x.T.T)
    print(relu(full((2, 2), -3)) + full((2, 2), 4) * 2)
    print(x @ zeros((5, 2)) + x @ ones((5, 2)))
