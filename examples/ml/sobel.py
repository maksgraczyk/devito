from devito import Function, dimensions, Operator, Eq, Grid

# Expected result (R.data):
# [[ 34. 32. -16. -22. -18.]
#  [ 22. 30.   6.  -9. -28.]
#  [ 21. 12.  12.   4. -33.]
#  [ 37.  7.   7.  -3. -44.]
#  [ 25. 10.  10. -10.  35.]]


def run():
    m, n = dimensions('m n')
    gridA = Grid(shape=(3, 3), dimensions=(m, n))
    gridBR = Grid(shape=(5, 5))

    A = Function(name='A', grid=gridA, space_order=0)
    B = Function(name='B', grid=gridBR, space_order=1)
    R = Function(name='R', grid=gridBR, space_order=0)

    A.data[:] = [[1, 0, -1],
                 [2, 0, -2],
                 [1, 0, -1]]
    B.data[:] = [[10, 16, 22, 4, 11],
                 [2, 2, 10, 10, 10],
                 [1, 2, 3, 4, 5],
                 [15, 15, 15, 15, 15],
                 [5, 5, 10, 10, 5]]

    x, y = B.dimensions
    op = Operator(Eq(R,
                     sum([A[2 - i, 2 - j]
                          * B[x + i - 1, y + j - 1] for i in range(3)
                          for j in range(3)])))

    op.apply()
    print(R.data)


if __name__ == "__main__":
    run()
