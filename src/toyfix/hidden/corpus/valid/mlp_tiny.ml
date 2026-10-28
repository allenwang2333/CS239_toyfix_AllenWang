# machine: npu-tiny
def dense(x: Tensor[3, 5, i32], w: Tensor[5, 3, i32], b: Tensor[3, i32]) -> Tensor[3, 3, i32]:
    return relu(x @ w + b)

def main():
    x = iota((3, 5)) - 6
    w1 = tensor([[1, -2, 0], [2, 1, -1], [0, 3, 1], [-1, 0, 2], [1, 1, 1]])
    h = dense(x, w1, tensor([1, -2, 3]))
    print(h)
    print(h @ tensor([[2, -1], [0, 1], [1, 3]]) + tensor([-5, 5]))
