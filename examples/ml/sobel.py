from devito import Function, dimensions, Operator, Eq


def run():
    m, n, k, l = dimensions('m n k l')
    A = Function(name='A', shape=(3, 3), dimensions=(m, n))
    B = Function(name='B', shape=(5, 5), dimensions=(k, l))
    R = Function(name='R', shape=(5, 5), dimensions=(k, l))
    op = Operator(Eq(R,
                     sum([A[2 - i, 2 - j]
                          * B[k + i - 1, l + j - 1] for i in range(3)
                          for j in range(3)])))
    A.data[:] = [[1, 0, -1],
                 [2, 0, -2],
                 [1, 0, -1]]
    B.data[:] = [[10, 16, 22, 4, 11],
                 [2, 2, 10, 10, 10],
                 [1, 2, 3, 4, 5],
                 [15, 15, 15, 15, 15],
                 [5, 5, 10, 10, 5]]
    print(op.ccode)
    print(B.data_with_halo)
    op.apply()
    print(R.data)


if __name__ == "__main__":
    run()
