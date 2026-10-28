# machine: npu-base
def main():
    a = iota((16, 16)) - 100
    b = iota((16, 16)) * -1 + 128
    print(a @ b)
