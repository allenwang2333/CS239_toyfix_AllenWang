# machine: npu-tiny
def main():
    a = tensor([[1, 2, 3, 4, 5, 6, 7]])
    b = tensor([[1], [-1], [2], [-2], [3], [-3], [4]])
    print(a @ b)
    print(b @ a)
