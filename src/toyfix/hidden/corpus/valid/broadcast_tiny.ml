# machine: npu-tiny
def main():
    m = iota((5, 3))
    b = tensor([1, 10, 100])
    print(relu(m @ tensor([[1, -1, 0], [0, 1, -1], [-1, 0, 1]]) + b))
