from devito import Operator, Inc, Grid, Function, dimensions

# Expected result: [ -5. -11. -17.]


def fully_connected(weights, vector):
    weight_size = (len(weights), len(weights[0]))

    a, b = dimensions('a b')
    gridW = Grid(shape=weight_size, dimensions=(a, b))
    W = Function(name='W', grid=gridW, space_order=0)

    gridV = Grid(shape=len(vector), dimensions=(b,))
    V = Function(name='V', grid=gridV, space_order=0)

    W.data[:] = weights
    V.data[:] = vector

    gridR = Grid(shape=weight_size[0], dimensions=(a,))
    R = Function(name='R', grid=gridR, space_order=0)

    op = Operator(Inc(R, W * V))
    op.cfunction

    return (op, R.data)


if __name__ == "__main__":
    weights = [[1, 2, 3],
               [4, 5, 6],
               [7, 8, 9]]
    vector = [-1, 1, -2]

    op, result = fully_connected(weights, vector)
    op.apply()

    print(result)
