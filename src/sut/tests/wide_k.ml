# machine: npu-wide
# A non-square 8 x 16 x 4 matrix unit and an inner dimension of 37 (spec §9.2).
def main():
    x = iota((9, 37)) - 100
    w = iota((37, 6)) - 50
    print(relu(x @ w + tensor([1, -2, 3, -4, 5, -6])))
    print(x.T @ (x @ w))
