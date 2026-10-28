# machine: npu-tiny
# Functions with int parameters, loops, and augmented assignment (spec §7, §8.7).
def scale(x: Tensor[3, 3, i32], k: int) -> Tensor[3, 3, i32]:
    return x * k

def power(x: Tensor[3, 3, i32], n: int) -> Tensor[3, 3, i32]:
    r = x
    for i in range(n - 1):
        r = r @ x
    return r

def main():
    x = tensor([[1, 1, 0], [0, 1, 1], [1, 0, 1]])
    print(power(x, 4))
    acc = zeros((3, 3))
    for k in range(1, 4):
        acc += scale(x, k * k)
    print(acc)
    n = 0
    for i in range(10, 0, -3):
        n += i
    print(n)
    print(ones(5) * n)
