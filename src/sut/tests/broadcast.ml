# machine: npu-base
# A rank-1 operand is added to every row of a rank-2 operand (spec §8.4).
def main():
    m = iota((4, 4))
    v = tensor([100, 200, 300, 400])
    print(m + v)
    print(v * m)
