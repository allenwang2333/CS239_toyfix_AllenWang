# machine: npu-base
# Values that are also used before the relu must not change (spec §9.4).
def main():
    x = tensor([[1, -2, 3], [-4, 5, -6]])
    w = tensor([[2, -1], [1, 3], [-2, 1]])
    b = tensor([1, -1])
    y = x @ w + b
    print(y)
    print(relu(y))
    m = x @ (w * 2)
    print(relu(m))
    print(m)
