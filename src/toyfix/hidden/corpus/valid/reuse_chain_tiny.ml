# machine: npu-tiny
def main():
    y = iota((4, 4)) - 7
    w = tensor([[1, 0, 0, 1], [0, 2, 1, 0], [0, 1, -1, 1], [1, 0, 0, -1]])
    for i in range(3):
        y = relu(y @ w) - 3
    print(y)
