# machine: npu-wide
def main():
    a = iota((3, 11)) - 9
    print(a.T)
    print(a.T @ a - transpose(a).T.T @ a)
    print(a @ a.T)
