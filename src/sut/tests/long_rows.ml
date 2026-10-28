# machine: npu-tiny
# Rows longer than the DMA row stride limit, no mma, and vlen = 2 (spec §9.2).
def main():
    x = tensor([[-8, -7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8],
                [3, -1, 4, -1, 5, -9, 2, -6, 5, -3, 5, -8, 9, -7, 9, -3, 2]])
    w = iota((17, 2))
    print(x @ w)
    print(relu(x) + iota(17))
    print(x @ x.T)
