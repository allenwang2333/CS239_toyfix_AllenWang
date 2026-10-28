# machine: npu-base
# transpose() and .T of non-square tensors (spec §8.6).
def main():
    a = tensor([[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]])
    print(a.T)
    print(a @ a.T)
    print(a.T @ tensor([[1, 0, -1], [0, 1, 2]]))
    b = transpose(a * 2 + 1)
    print(b - iota((6, 2)))
