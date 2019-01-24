import abc
from collections import OrderedDict
from ctypes import c_void_p
from functools import reduce
from itertools import product
from operator import mul

from sympy import Integer

from devito.data import OWNED, HALO, NOPAD, LEFT, RIGHT
from devito.ir.equations import DummyEq
from devito.ir.iet import (ArrayCast, Call, Callable, Conditional, Expression,
                           Iteration, List, iet_insert_C_decls, PARALLEL)
from devito.symbolics import CondNe, FieldFromPointer, Macro
from devito.tools import dtype_to_mpitype, flatten
from devito.types import Array, Dimension, Symbol, LocalObject

__all__ = ['HaloExchangeBuilder']


class HaloExchangeBuilder(object):

    """
    Build IET-based routines to implement MPI halo exchange.
    """

    def __new__(cls, threaded):
        obj = object.__new__(BasicHaloExchangeBuilder)
        obj.__init__(threaded)
        return obj

    def __init__(self, threaded):
        self._threaded = threaded

    @abc.abstractmethod
    def make(self, halo_spots):
        """
        Construct Callables and Calls implementing a halo exchange for the
        provided HaloSpots.

        For each (unique) HaloSpot, three Callables are built:

            * ``update_halo``, to be called when a halo exchange is necessary,
            * ``sendrecv``, called multiple times by ``update_halo``.
            * ``copy``, called twice by ``sendrecv``, to implement, for example,
              data gathering prior to an MPI_Send, and data scattering following
              an MPI recv.
        """
        calls = OrderedDict()
        generated = OrderedDict()
        for hs in halo_spots:
            for f, v in hs.fmapper.items():
                # Sanity check
                assert f.is_Function
                assert f.grid is not None

                # Callables construction
                # ----------------------
                # Note: to construct the halo exchange Callables, use the generic `df`,
                # instead of `f`, so that we don't need to regenerate code for Functions
                # that are symbolically identical to `f` except for the name
                df = f.__class__.__base__(name='a', grid=f.grid, shape=f.shape_global,
                                          dimensions=f.dimensions)
                # `gather`, `scatter`, `sendrecv` are generic by construction -- they
                # only need to be generated once for each `ndim`
                if f.ndim not in generated:
                    gather, extra = self._make_copy(df, v.loc_indices)
                    scatter, _ = self._make_copy(df, v.loc_indices, swap=True)
                    sendrecv = self._make_sendrecv(df, v.loc_indices, extra)
                    generated[f.ndim] = [gather, scatter, sendrecv]
                # `haloupdate` is generic by construction -- it only needs to be
                # generated once for each (`ndim`, `mask`)
                if (f.ndim, v) not in generated:
                    uniquekey = len([i for i in generated if isinstance(i, tuple)])
                    generated[(f.ndim, v)] = [self._make_haloupdate(df, v.loc_indices,
                                                                    hs.mask[f], extra,
                                                                    uniquekey)]

                # `haloupdate` Call construction
                comm = f.grid.distributor._obj_comm
                nb = f.grid.distributor._obj_neighborhood
                loc_indices = list(v.loc_indices.values())
                args = [f, comm, nb] + loc_indices + extra
                call = Call(generated[(f.ndim, v)][0].name, args)
                calls.setdefault(hs, []).append(call)

        return flatten(generated.values()), calls

    @abc.abstractmethod
    def _make_haloupdate(self, f, fixed, halos, **kwargs):
        """
        Construct a Callable performing, for a given DiscreteFunction, a halo exchange.
        """
        return

    @abc.abstractmethod
    def _make_sendrecv(self, f, fixed, **kwargs):
        """
        Construct a Callable performing, for a given DiscreteFunction, a halo exchange
        along given Dimension and DataSide.
        """
        return

    def _make_copy(self, f, fixed, swap=False):
        """
        Construct a Callable performing a copy of:

            * an arbitrary convex region of ``f`` into a contiguous Array, OR
            * if ``swap=True``, a contiguous Array into an arbitrary convex
              region of ``f``.
        """
        buf_dims = []
        buf_indices = []
        for d in f.dimensions:
            if d not in fixed:
                buf_dims.append(Dimension(name='buf_%s' % d.root))
                buf_indices.append(d.root)
        buf = Array(name='buf', dimensions=buf_dims, dtype=f.dtype)

        f_offsets = []
        f_indices = []
        for d in f.dimensions:
            offset = Symbol(name='o%s' % d.root)
            f_offsets.append(offset)
            f_indices.append(offset + (d.root if d not in fixed else 0))

        if swap is False:
            eq = DummyEq(buf[buf_indices], f[f_indices])
            name = 'gather%dd' % f.ndim
        else:
            eq = DummyEq(f[f_indices], buf[buf_indices])
            name = 'scatter%dd' % f.ndim

        iet = Expression(eq)
        for i, d in reversed(list(zip(buf_indices, buf_dims))):
            # The -1 below is because an Iteration, by default, generates <=
            iet = Iteration(iet, i, d.symbolic_size - 1, properties=PARALLEL)
        iet = List(body=[ArrayCast(f), ArrayCast(buf), iet])

        # Optimize the memory copy with the DLE
        from devito.dle import transform
        state = transform(iet, 'simd', {'openmp': self._threaded})

        parameters = [buf] + list(buf.shape) + [f] + f_offsets + state.input
        return Callable(name, state.nodes, 'void', parameters, ('static',)), state.input


class BasicHaloExchangeBuilder(HaloExchangeBuilder):

    """
    Build basic routines for MPI halo exchanges. No optimisations are performed.

    The only constraint is that the built ``update_halo`` Callable is called prior
    to executing the code region requiring up-to-date halos.
    """

    def _make_sendrecv(self, f, fixed, extra=None):
        extra = extra or []
        comm = f.grid.distributor._obj_comm

        buf_dims = [Dimension(name='buf_%s' % d.root) for d in f.dimensions
                    if d not in fixed]
        bufg = Array(name='bufg', dimensions=buf_dims, dtype=f.dtype, scope='heap')
        bufs = Array(name='bufs', dimensions=buf_dims, dtype=f.dtype, scope='heap')

        ofsg = [Symbol(name='og%s' % d.root) for d in f.dimensions]
        ofss = [Symbol(name='os%s' % d.root) for d in f.dimensions]

        fromrank = Symbol(name='fromrank')
        torank = Symbol(name='torank')

        args = [bufg] + list(bufg.shape) + [f] + ofsg + extra
        gather = Call('gather%dd' % f.ndim, args)
        args = [bufs] + list(bufs.shape) + [f] + ofss + extra
        scatter = Call('scatter%dd' % f.ndim, args)

        # The `gather` is unnecessary if sending to MPI.PROC_NULL
        gather = Conditional(CondNe(torank, Macro('MPI_PROC_NULL')), gather)
        # The `scatter` must be guarded as we must not alter the halo values along
        # the domain boundary, where the sender is actually MPI.PROC_NULL
        scatter = Conditional(CondNe(fromrank, Macro('MPI_PROC_NULL')), scatter)

        srecv = MPIStatusObject(name='srecv')
        ssend = MPIStatusObject(name='ssend')
        rrecv = MPIRequestObject(name='rrecv')
        rsend = MPIRequestObject(name='rsend')

        count = reduce(mul, bufs.shape, 1)
        recv = Call('MPI_Irecv', [bufs, count, Macro(dtype_to_mpitype(f.dtype)),
                                  fromrank, Integer(13), comm, rrecv])
        send = Call('MPI_Isend', [bufg, count, Macro(dtype_to_mpitype(f.dtype)),
                                  torank, Integer(13), comm, rsend])

        waitrecv = Call('MPI_Wait', [rrecv, srecv])
        waitsend = Call('MPI_Wait', [rsend, ssend])

        iet = List(body=[recv, gather, send, waitsend, waitrecv, scatter])
        iet = List(body=iet_insert_C_decls(iet))
        parameters = ([f] + list(bufs.shape) + ofsg + ofss +
                      [fromrank, torank, comm] + extra)
        return Callable('sendrecv%dd' % f.ndim, iet, 'void', parameters, ('static',))

    def _make_haloupdate(self, f, fixed, mask, extra=None, uniquekey=None):
        extra = extra or []
        distributor = f.grid.distributor
        nb = distributor._obj_neighborhood
        comm = distributor._obj_comm

        fixed = {d: Symbol(name="o%s" % d.root) for d in fixed}

        # Build a mapper `(dim, side, region) -> (size, ofs)` for `f`. `size` and
        # `ofs` are symbolic objects. This mapper tells what data values should be
        # sent (OWNED) or received (HALO) given dimension and side
        mapper = {}
        for d0, side, region in product(f.dimensions, (LEFT, RIGHT), (OWNED, HALO)):
            if d0 in fixed:
                continue
            sizes = []
            offsets = []
            for d1 in f.dimensions:
                if d1 in fixed:
                    offsets.append(fixed[d1])
                else:
                    meta = f._C_get_field(region if d0 is d1 else NOPAD, d1, side)
                    offsets.append(meta.offset)
                    sizes.append(meta.size)
            mapper[(d0, side, region)] = (sizes, offsets)

        body = []
        for d in f.dimensions:
            if d in fixed:
                continue

            name = ''.join('r' if i is d else 'c' for i in distributor.dimensions)
            rpeer = FieldFromPointer(name, nb)
            name = ''.join('l' if i is d else 'c' for i in distributor.dimensions)
            lpeer = FieldFromPointer(name, nb)

            if mask[(d, LEFT)]:
                # Sending to left, receiving from right
                lsizes, loffsets = mapper[(d, LEFT, OWNED)]
                rsizes, roffsets = mapper[(d, RIGHT, HALO)]
                args = [f] + lsizes + loffsets + roffsets + [rpeer, lpeer, comm] + extra
                body.append(Call('sendrecv%dd' % f.ndim, args))

            if mask[(d, RIGHT)]:
                # Sending to right, receiving from left
                rsizes, roffsets = mapper[(d, RIGHT, OWNED)]
                lsizes, loffsets = mapper[(d, LEFT, HALO)]
                args = [f] + rsizes + roffsets + loffsets + [lpeer, rpeer, comm] + extra
                body.append(Call('sendrecv%dd' % f.ndim, args))

        if uniquekey is None:
            uniquekey = ''.join(str(int(i)) for i in mask.values())
        name = 'haloupdate%dd%s' % (f.ndim, uniquekey)
        iet = List(body=body)
        parameters = [f, comm, nb] + list(fixed.values()) + extra
        return Callable(name, iet, 'void', parameters, ('static',))


class MPIStatusObject(LocalObject):

    dtype = type('MPI_Status', (c_void_p,), {})

    def __init__(self, name):
        self.name = name

    # Pickling support
    _pickle_args = ['name']


class MPIRequestObject(LocalObject):

    dtype = type('MPI_Request', (c_void_p,), {})

    def __init__(self, name):
        self.name = name

    # Pickling support
    _pickle_args = ['name']
