from devito import Grid, Function, Operator, dimensions, Eq
from sympy import Max
import numpy as np

# This example uses a 3x3 max pooling function.
# Expected result (R.data):
# [[22. 22. 22.]
#  [15. 15. 15.]
#  [15. 15. 15.]]


def error_check(kernel_size, feature_map, stride, padding):
    if feature_map is None or len(feature_map) == 0:
        raise Exception("Feature map must not be empty")

    if kernel_size is None or len(kernel_size) != 2:
        raise Exception("Kernel size is incorrect")

    if stride is None or len(stride) != 2:
        raise Exception("Stride is incorrect")

    if stride[0] < 1 or stride[1] < 1:
        raise Exception("Stride cannot be less than 1")

    if padding is None or len(padding) != 2:
        raise Exception("Padding is incorrect")

    if padding[0] < 0 or padding[1] < 0:
        raise Exception("Padding cannot be negative")


def subsampling(kernel_size, feature_map, function, stride=(1, 1),
                padding=(0, 0)):
    # All sizes are expressed as (rows, columns).

    error_check(kernel_size, feature_map, stride, padding)

    map_height = len(feature_map) + 2 * padding[0]
    map_width = len(feature_map[0]) + 2 * padding[1]
    kernel_height, kernel_width = kernel_size

    if (map_height - kernel_height) % stride[0] != 0 or \
       (map_width - kernel_width) % stride[1] != 0:
        raise Exception("Stride " + str(stride) + " is not compatible "
                        "with feature map, kernel and padding sizes")

    gridB = Grid(shape=(map_height, map_width))
    B = Function(name='B', grid=gridB, space_order=0)

    a, b = dimensions('a b')
    gridR = Grid(shape=((map_height - kernel_height + stride[0])
                        // stride[0],
                        (map_width - kernel_width + stride[1])
                        // stride[1]),
                 dimensions=(a, b))
    R = Function(name='R', grid=gridR, space_order=0)

    for i in range(padding[0], map_height - padding[0]):
        B.data[i] = \
            np.concatenate(([0] * padding[1],
                            feature_map[i - padding[0]],
                            [0] * padding[1]))

    op = Operator(Eq(R[a, b],
                     function([B[stride[0] * a + i, stride[1] * b + j]
                               for i in range(kernel_height)
                               for j in range(kernel_width)])))
    op.cfunction

    return (op, R.data)


if __name__ == "__main__":
    feature_map = [[10, 16, 22, 4, 11],
                   [2, 2, 10, 10, 10],
                   [1, 2, 3, 4, 5],
                   [15, 15, 15, 15, 15],
                   [5, 5, 10, 10, 5]]

    op, result = subsampling(kernel_size=(3, 3),
                             feature_map=feature_map,
                             function=lambda l: Max(*l))
    op.apply()

    print(result)
