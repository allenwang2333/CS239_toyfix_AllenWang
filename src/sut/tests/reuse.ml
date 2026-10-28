# machine: npu-base
# Buffers are reused after their last use (spec §9.4).
def main():
    x = iota((8, 8)) - 20
    w = tensor([[1, 0, 0, 0, 0, 0, 0, 1],
                [0, 2, 0, 0, 0, 0, 1, 0],
                [0, 0, -1, 0, 0, 1, 0, 0],
                [0, 0, 0, 1, 1, 0, 0, 0],
                [1, 1, 1, 1, 0, 0, 0, 0],
                [0, 0, 0, 0, 1, 1, 1, 1],
                [-1, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 3]])
    y = x @ w
    print(y)
    for i in range(3):
        y = relu(y @ w) - 50
    print(y)
