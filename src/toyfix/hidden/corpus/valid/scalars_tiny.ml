# machine: npu-tiny
def bump(x: Tensor[5, i32], k: int) -> Tensor[5, i32]:
    return x * k + k

def main():
    v = tensor([3, -1, 4, -1, 5])
    s = 0
    for k in range(1, 6):
        v = bump(v, k) - 7 * k
        s += k * k
    print(v)
    print(s)
    print(-v)
    print(ones(5) - v * 0)
