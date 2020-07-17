from devito import Function, Operator, Eq, Grid, dimensions

# Expected result (R.data):
# [[ 34.  32. -16. -22. -18.]
#  [ 22.  30.   6.  -9. -28.]
#  [ 21.  12.  12.   4. -33.]
#  [ 37.   7.   7.  -3. -44.]
#  [ 25.  10.  10. -10. -35.]]


SOBEL_VERTICAL = [[1, 0, -1],
                  [2, 0, -2],
                  [1, 0, -1]]


def error_check(kernel, image):
    if kernel is None or len(kernel) == 0:
        raise Exception("kernel must not be empty")

    if image is None or len(image) == 0:
        raise Exception("image must not be empty")

    different_row_length = False
    for row in kernel:
        if len(row) != len(kernel[0]):
            different_row_length = True
            break

    if different_row_length:
        raise Exception("kernel has an invalid shape")

    different_row_length = False
    for row in image:
        if len(row) != len(image[0]):
            different_row_length = True
            break

    if different_row_length:
        raise Exception("image has an invalid shape")

    if len(kernel) % 2 == 0 or len(kernel[0]) % 2 == 0:
        raise Exception("The dimensions of kernel must be odd")


def run(kernel, image):
    # It is assumed that both kernel and image have only two dimensions.

    error_check(kernel, image)

    gridA = Grid(shape=(len(kernel), len(kernel[0])),
                 dimensions=dimensions('m n'))
    A = Function(name='A', grid=gridA, space_order=0)
    A.data[:] = kernel

    gridBR = Grid(shape=(len(image), len(image[0])))

    B = Function(name='B', grid=gridBR, space_order=1)
    B.data[:] = image

    R = Function(name='R', grid=gridBR, space_order=0)

    x, y = B.dimensions
    kernel_rows, kernel_cols = A.shape
    op = Operator(Eq(R[x, y],
                     sum([A[kernel_rows - i - 1,
                            kernel_cols - j - 1] *
                          B[x - kernel_rows // 2 + i,
                            y - kernel_cols // 2 + j]
                          for i in range(kernel_rows)
                          for j in range(kernel_cols)])))

    op.apply()
    return R.data


if __name__ == "__main__":
    result = run(SOBEL_VERTICAL,
                 [[10, 16, 22, 4, 11],
                  [2, 2, 10, 10, 10],
                  [1, 2, 3, 4, 5],
                  [15, 15, 15, 15, 15],
                  [5, 5, 10, 10, 5]])

    print(result)
