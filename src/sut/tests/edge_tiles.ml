# machine: npu-tiny
# Shapes that are not multiples of the 2x2 tile (spec §9.2).
def main():
    x = tensor([[1, -2, 3, 0, 2], [4, 5, -6, 1, 1], [0, 1, 2, 3, 4]])
    w = iota((5, 3)) - 7
    print(x @ w)
    print(x @ w + 100)
    print(x + iota((3, 5)))
