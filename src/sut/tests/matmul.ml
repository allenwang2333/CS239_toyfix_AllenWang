# machine: npu-base
# Matrix products whose inner dimension is larger than the tile (spec §8.5, §9.2).
def main():
    x = iota((4, 8)) - 10
    w = iota((8, 4)) * 2 - 31
    print(x @ w)
    y = tensor([[1, 2], [3, 4], [5, 6]])
    z = tensor([[7, 8, 9, 10, 11, 12], [-1, -2, -3, -4, -5, -6]])
    print(y @ z)
