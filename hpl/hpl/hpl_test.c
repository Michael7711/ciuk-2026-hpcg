#include <stdio.h>
#include <stdlib.h>
#include <time.h>

double elapsed_time(struct timespec start, struct timespec end)
{
    return (end.tv_sec - start.tv_sec)
        + (end.tv_nsec - start.tv_nsec) / 1e9;
}

int main(int argc, char *argv[])
{
    int n = 1000;

    if (argc > 1) {
        n = atoi(argv[1]);
    }

    size_t elements = (size_t)n * n;

    double *a = malloc(elements * sizeof(double));
    double *b = malloc(elements * sizeof(double));
    double *c = calloc(elements, sizeof(double));

    if (a == NULL || b == NULL || c == NULL) {
        fprintf(stderr, "Memory allocation failed\n");
        return 1;
    }

    for (size_t i = 0; i < elements; i++) {
        a[i] = 1.0;
        b[i] = 1.0;
    }

    struct timespec start;
    struct timespec end;

    clock_gettime(CLOCK_MONOTONIC, &start);

    for (int i = 0; i < n; i++) {
        for (int k = 0; k < n; k++) {
            double a_ik = a[(size_t)i * n + k];

            for (int j = 0; j < n; j++) {
                c[(size_t)i * n + j] +=
                    a_ik * b[(size_t)k * n + j];
            }
        }
    }

    clock_gettime(CLOCK_MONOTONIC, &end);

    double seconds = elapsed_time(start, end);

    /*
     * Matrix multiplication requires approximately
     * 2 * N^3 floating-point operations.
     */
    double flops = 2.0 * n * n * n;
    double gflops = flops / seconds / 1e9;

    printf("Matrix size: %d x %d\n", n, n);
    printf("Runtime: %.3f seconds\n", seconds);
    printf("Performance: %.3f GFLOPS\n", gflops);

    /* Prevent compiler from discarding the calculation */
    printf("Check value: %.1f\n", c[0]);

    free(a);
    free(b);
    free(c);

    return 0;
}