# machine: npu-tiny
def main():
    a = iota((2, 24))
    print(a + relu(a))
    x = iota((2, 18))
    print(x @ x.T)
