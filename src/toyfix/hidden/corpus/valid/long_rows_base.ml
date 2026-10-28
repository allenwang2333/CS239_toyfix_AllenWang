# machine: npu-base
def main():
    a = iota((2, 260))
    print(relu(a - 300))
