#cython: boundscheck=False
#cython: wraparound=False
#cython: initializedcheck=False
#cython: cdivision=True
#cython: embedsignature=True
#cython: language_level=3

from hashlib import sha1
from cython cimport floating, integral
import numpy as np
cimport numpy as np
from libc.stdlib cimport rand, srand, RAND_MAX


ctypedef fused numeric:
    integral
    floating


cdef inline bint isnan(numeric x) nogil:
    return x != x


def argmaxrnd(numeric[:] vec, object random_seed=None):

    """
    Returns the index of the maximum value for a given 1D array.
    In case of multiple indices corresponding to the maximum value,
    the result is chosen randomly among those. The random number
    generator, used by the C lang function 'rand', can be seeded
    by forwarding a hashable python object. If -1 is passed, the
    input array is hashed instead.

    :param vec: 1D input array (vector) of real numbers
    :type vec: np.ndarray

    :param random_seed: used to initialize the random number generator
    :type random_seed: hashable python object

    :return: index of the maximum value
    """

    if vec.ndim != 1:
        raise ValueError("1D array of shape (n,) is expected.")

    if random_seed is not None:
        if random_seed == -1:
            srand(int(sha1(bytes(vec)).hexdigest(), base=16) & 0xffffffff)
        else:
            srand(hash(random_seed) & 0xffffffff)

    return _argmaxrnd(vec)


cdef Py_ssize_t _argmaxrnd(numeric[:] vec):
    cdef:
        Py_ssize_t i, m_i
        int c = 0
        numeric curr, m

    for i in range(vec.shape[0]):
        curr = vec[i]
        if not isnan(curr):
            if curr > m or c == 0:
                m = curr
                c = 1
                m_i = i
            elif curr == m:
                c += 1
                if 1 + <int>(1.0 * c * rand() / RAND_MAX) == c:
                    m_i = i
    return m_i
