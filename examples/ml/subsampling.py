from devito import *
from sympy import Max


def subsampling(kernel_size, feature_map, function, stride=1):
    if stride != 1:
        raise Exception("Stride other than 1 not supported yet")

    gridB = Grid(shape=(len(feature_map), len(feature_map[0])))
    B = Function(name='B', grid=gridB)

    width, height = kernel_size

    a, b = dimensions('a b')
    gridR = Grid(shape=(gridB.shape[0] - height + 1,
                        gridB.shape[1] - width + 1),
                 dimensions=(a, b))
    R = Function(name='R', grid=gridR)

    B.data[:] = feature_map

    op = Operator(Eq(R[a, b],
                     function([B[a + i, b + j]
                               for i in range(height)
                               for j in range(width)])))
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
