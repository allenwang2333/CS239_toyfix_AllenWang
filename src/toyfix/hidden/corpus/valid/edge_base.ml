# machine: npu-base
def main():
    a = iota((5, 7)) - 17
    b = iota((7, 6)) * 2 - 41
    print(a @ b)
    print(a * 3 + iota((5, 7)))
