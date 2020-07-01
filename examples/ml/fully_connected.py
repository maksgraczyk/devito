from devito import Operator, Inc, Grid, Function, dimensions
import numpy as np

# Expected result: [ -5. -11. -17.]


def fully_connected(weights, input_data):
    weight_size = (len(weights), len(weights[0]))

    try:
        input_size = (len(input_data), len(input_data[0]))
        is_vector = False
    except TypeError:
        input_size = len(input_data)
        is_vector = True

    a, b, c = dimensions('a b c')

    gridW = Grid(shape=weight_size, dimensions=(a, b))
    W = Function(name='W', grid=gridW, space_order=0)

    if is_vector:
        gridV_dimensions = (b,)
        gridR_dimensions = (a,)
        gridR_shape = weight_size[0]
    else:
        gridV_dimensions = (b, c)
        gridR_dimensions = (a, c)
        gridR_shape = (weight_size[0], input_size[1])

    gridV = Grid(shape=input_size, dimensions=gridV_dimensions)
    V = Function(name='V', grid=gridV, space_order=0)

    W.data[:] = weights
    V.data[:] = input_data

    gridR = Grid(shape=gridR_shape, dimensions=gridR_dimensions)
    R = Function(name='R', grid=gridR, space_order=0)

    op = Operator(Inc(R, W * V))
    op.cfunction

    return (op, R.data)


if __name__ == "__main__":
    weights = [[1, 2, 3],
               [4, 5, 6],
               [7, 8, 9]]
    vector = [-1, 1, -2]

    op, result = fully_connected(weights=weights,
                                 input_data=vector)
    op.apply()

    print(result)
