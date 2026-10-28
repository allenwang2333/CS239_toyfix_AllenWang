# machine: npu-tiny
def main():
    x = tensor([[2, -3, 1], [-1, 4, -2], [0, -1, 5]])
    y = x @ x + 1
    print(relu(y))
    print(y - relu(y))
