# machine: npu-base
# A two-layer perceptron. The compiler fuses matmul, bias add, and relu (spec §9.4).
def dense(x: Tensor[4, 6, i32], w: Tensor[6, 5, i32], b: Tensor[5, i32]) -> Tensor[4, 5, i32]:
    return relu(x @ w + b)

def main():
    x = iota((4, 6)) - 11
    w1 = tensor([[1, -1, 2, 0, 3],
                 [-2, 1, 0, 1, -1],
                 [0, 2, -3, 1, 1],
                 [1, 0, 1, -2, 2],
                 [3, -1, 0, 1, 0],
                 [-1, 1, 1, 0, -2]])
    b1 = tensor([3, -20, 0, 7, -1])
    h = dense(x, w1, b1)
    print(h)
    w2 = iota((5, 3)) - 6
    b2 = tensor([-50, 0, 50])
    print(h @ w2 + b2)
