# machine: npu-tiny
def main():
    x = tensor([[1, -2, 3, 4, 0], [5, 6, -7, 8, 1], [2, 0, 1, -1, 3]])
    print(x.T @ x)
    print((x * 2 + tensor([1, 2, 3, 4, 5])).T)
    print(transpose(x @ x.T - 1))
