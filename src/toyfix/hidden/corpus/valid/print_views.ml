# machine: npu-base
def main():
    v = tensor([7, 8, 9])
    print(zeros((2, 3)) + v)
    print(tensor([[1, 2], [3, 4], [5, 6]]).T)
    print(full(4, -9))
    print(123)
