# machine: npu-base
def main():
    x = iota((8, 8)) - 30
    w = iota((8, 8)) - 32
    for i in range(3):
        x = x @ w - 7
        print(x)
