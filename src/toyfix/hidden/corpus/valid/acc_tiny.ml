# machine: npu-tiny
def main():
    x = tensor([[-4, 3, -2, 1, 0, -1, 2], [5, -6, 7, -8, 9, -1, 0], [1, 1, -1, 1, -1, 1, 1]])
    w = iota((7, 3)) - 10
    print(x @ w + tensor([1, 2, 3]))
    print(relu(x @ (w * 2)))
