from devito import Grid, Function, Operator, dimensions, Eq
from sympy import Max

# This example uses a 3x3 max pooling function.
# Expected result (R.data):
# [[22. 22. 22.]
#  [15. 15. 15.]
#  [15. 15. 15.]]


def subsampling(kernel_size, feature_map, function, stride=(1, 1)):
    if feature_map is None or len(feature_map) == 0:
        raise Exception("Feature map must not be empty")

    if kernel_size is None or len(kernel_size) != 2:
        raise Exception("Kernel size is incorrect")

    map_height, map_width = len(feature_map), len(feature_map[0])
    kernel_height, kernel_width = kernel_size

    if (map_height - kernel_height) % stride[0] != 0 or \
       (map_width - kernel_width) % stride[1] != 0:
        raise Exception("Stride " + str(stride) + " is not compatible "
                        "with feature map and kernel sizes")

    gridB = Grid(shape=(map_height, map_width))
    B = Function(name='B', grid=gridB, space_order=0)

    a, b = dimensions('a b')
    gridR = Grid(shape=((map_height - kernel_height + stride[0])
                        // stride[0],
                        (map_width - kernel_width + stride[1])
                        // stride[1]),
                 dimensions=(a, b))
    R = Function(name='R', grid=gridR, space_order=0)

    B.data[:] = feature_map

    op = Operator(Eq(R[a, b],
                     function([B[stride[0] * a + i, stride[1] * b + j]
                               for i in range(kernel_height)
                               for j in range(kernel_width)])))
    op.apply()

    return R.data


if __name__ == "__main__":
    feature_map = [[10, 16, 22, 4, 11],
                   [2, 2, 10, 10, 10],
                   [1, 2, 3, 4, 5],
                   [15, 15, 15, 15, 15],
                   [5, 5, 10, 10, 5]]

    result = subsampling(kernel_size=(3, 3),
                         feature_map=feature_map,
                         function=lambda l: Max(*l))

    print(result)
