from __future__ import absolute_import
import weakref
import abc
import gc

import numpy as np
import sympy
from operator import mul
from functools import reduce

from devito.parameters import configuration
from devito.tools import single_or

__all__ = ['Symbol', 'Indexed']

configuration.add('first_touch', 0, [0, 1], lambda i: bool(i))

# This cache stores a reference to each created data object
# so that we may re-create equivalent symbols during symbolic
# manipulation with the correct shapes, pointers, etc.
_SymbolCache = {}


class Basic(object):
    """
    Base class for API objects, mainly used to build equations.

    There are three relevant sub-types of :class:`Basic`: ::

        * AbstractSymbol: represents a scalar; may carry data; may be used
                          to build equations.
        * AbstractFunction: represents a discrete function as a tensor; may
                            carry data; may be used to build equations.
        * Object: represents a generic object, for example a (pointer to) data
                  structure.

                                        Basic
                                          |
                    ------------------------------------------
                    |                     |                  |
             AbstractSymbol       AbstractFunction        Object

    .. note::

        The :class:`AbstractFunction` sub-hierarchy is mainly implemented in
        :mod:`function.py`.
    """

    # Top hierarchy
    is_AbstractFunction = False
    is_AbstractSymbol = False
    is_Object = False

    # Symbolic objects created internally by Devito
    is_Symbol = False
    is_SymbolicData = False
    is_Array = False

    # Scalar symbolic objects created by the user
    is_Dimension = False
    is_Constant = False
    # Tensor symbolic objects created by the user
    is_SymbolicFunction = False
    is_TensorFunction = False
    is_Function = False
    is_TimeFunction = False
    is_CompositeFunction = False
    is_SparseFunction = False

    # Basic symbolic object properties
    is_Scalar = False
    is_Tensor = False

    @abc.abstractmethod
    def __init__(self, *args, **kwargs):
        return

    @abc.abstractmethod
    def argument_defaults(self):
        """
        Returns a map of default argument values defined by this symbol.
        """
        raise NotImplementedError('%s does not provide any default arguments' %
                                  self.__class__)

    @abc.abstractmethod
    def argument_values(self, **kwargs):
        """
        Returns a map of argument values after evaluating user input.

        :param kwargs: Dictionary of user-provided argument overrides.
        """
        raise NotImplementedError('%s does not provide argument value derivation' %
                                  self.__class__)



class Cached(object):
    """
    Base class for symbolic objects that caches on the class type.

    In order to maintain meta information across the numerous
    re-instantiation SymPy performs during symbolic manipulation, we inject
    the symbol name as the class name and cache all created objects on that
    name. This entails that a symbolic object inheriting from :class:`Cached`
    should implement `__init__` in the following way:

        .. code-block::
            def __init__(self, \*args, \*\*kwargs):
                if not self._cached():
                    ... # Initialise object properties from kwargs
    """

    @classmethod
    def _cached(cls):
        """Test if current class is already in the symbol cache."""
        return cls in _SymbolCache

    @classmethod
    def _cache_put(cls, obj):
        """Store given object instance in symbol cache.

        :param obj: Object to be cached.
        """
        _SymbolCache[cls] = weakref.ref(obj)

    @classmethod
    def _symbol_type(cls, name):
        """Create new type instance from cls and inject symbol name"""
        return type(name, (cls, ), dict(cls.__dict__))

    def _cached_init(self):
        """Initialise symbolic object with a cached object state"""
        original = _SymbolCache[self.__class__]
        self.__dict__ = original().__dict__


class AbstractSymbol(sympy.Symbol, Basic):
    """
    Base class for dimension-free symbols, only cached by SymPy.

    The sub-hierarchy is structured as follows

                             AbstractSymbol
                                   |
                 -------------------------------------
                 |                                   |
        AbstractCachedSymbol                      Dimension
                 |
        --------------------
        |                  |
     Symbol            Constant

    There are three relevant :class:`AbstractSymbol` sub-types: ::

        * Symbol: A generic scalar symbol that can be used to build an equation.
                  It does not carry data. Typically, :class:`Symbol`s are
                  created internally by Devito (e.g., for temporary variables)
        * Constant: A generic scalar symbol that can be used to build an equation.
                    It carries data (a scalar value).
        * Dimension: A problem dimension, used to create an iteration space. It
                     may be used to build equations; typically, it is used as
                     an index for a :class:`Indexed`.
    """

    is_AbstractSymbol = True

    @property
    def indices(self):
        return ()

    @property
    def shape(self):
        return ()

    @property
    def symbolic_shape(self):
        return ()

    @property
    def function(self):
        return self

    def indexify(self):
        return self


class AbstractCachedSymbol(AbstractSymbol, Cached):
    """
    Base class for dimension-free symbols, cached by both Devito and Sympy.

    For more information, refer to the documentation of :class:`AbstractSymbol`.
    """

    def __new__(cls, *args, **kwargs):
        options = kwargs.get('options', {})
        if cls in _SymbolCache:
            newobj = sympy.Symbol.__new__(cls, *args, **options)
            newobj._cached_init()
        else:
            name = kwargs.get('name')

            # Create the new Function object and invoke __init__
            newcls = cls._symbol_type(name)
            newobj = sympy.Symbol.__new__(newcls, name, *args, **options)
            newobj.__init__(*args, **kwargs)

            # Store new instance in symbol cache
            newcls._cache_put(newobj)
        return newobj


class Symbol(AbstractCachedSymbol):

    """A :class:`sympy.Symbol` capable of mimicking an :class:`sympy.Indexed`"""

    is_Symbol = True

    def __init__(self, *args, **kwargs):
        if not self._cached():
            self.dtype = kwargs.get('dtype', np.int32)

    @property
    def base(self):
        return self


class AbstractFunction(sympy.Function, Basic):
    """
    Base class for tensor symbols, only cached by SymPy. It inherits from and
    mimick the behaviour of a :class:`sympy.Function`.

    The sub-hierarchy is structured as follows

                            AbstractFunction
                                   |
                         AbstractCachedFunction
                                   |
                 -------------------------------------
                 |                                   |
            SymbolicData                      SymbolicFunction
                 |                                   |
               Array                           TensorFunction
                                                     |
                                                 Function
                                                     |
                                            --------------------
                                            |                  |
                                      TimeFunction     CompositeFunction
                                                               |
                                                         SparseFunction

    There are four relevant :class:`AbstractFunction` sub-types: ::

        * Array: Like any :class:`SymbolicData`, an array does not carry data.
                 Usually, it is only created internally by Devito (e.g., by the DSE).
        * Function: A space-varying discrete function, which carries user data.
        * TimeFunction: A time-varying discrete function, which carries user data.
        * CompositeFunction: A nest of :class:`Function` objects. This comes in handy
                             to express sparse functions.
    """

    is_AbstractFunction = True


class AbstractCachedFunction(AbstractFunction, Cached):
    """
    Base class for tensor symbols, cached by both Devito and Sympy.

    For more information, refer to the documentation of :class:`AbstractFunction`.
    """

    def __new__(cls, *args, **kwargs):
        if cls in _SymbolCache:
            options = kwargs.get('options', {})
            newobj = sympy.Function.__new__(cls, *args, **options)
            newobj._cached_init()
        else:
            name = kwargs.get('name')
            if len(args) < 1:
                args = cls._indices(**kwargs)

            # Create the new Function object and invoke __init__
            newcls = cls._symbol_type(name)
            options = kwargs.get('options', {})
            newobj = sympy.Function.__new__(newcls, *args, **options)
            newobj.__init__(*args, **kwargs)

            # All objects cached on the AbstractFunction /newobj/ keep a reference
            # to /newobj/ through the /function/ field. Thus, all indexified
            # object will point to /newobj/, the "actual Function".
            newobj.function = newobj

            # Store new instance in symbol cache
            newcls._cache_put(newobj)
        return newobj

    @classmethod
    def _indices(cls, **kwargs):
        """Return the default dimension indices."""
        return []

    @property
    def dim(self):
        """Return the rank of the object."""
        return len(self.shape)

    @property
    def indexed(self):
        """Extract a :class:`IndexedData` object from the current object."""
        return IndexedData(self.name, shape=self.shape, function=self.function)

    @property
    def symbolic_shape(self):
        """
        Return the symbolic shape of the object. For an entry ``E`` in ``self.shape``,
        there are two possibilities: ::

            * ``E`` is already in symbolic form, then simply use ``E``.
            * ``E`` is an integer representing the size along a dimension ``D``,
              then, use a symbolic representation of ``D``.
        """
        sshape = []
        for i, j in zip(self.shape, self.indices):
            try:
                i.is_algebraic_expr()
                sshape.append(i)
            except AttributeError:
                sshape.append(j.symbolic_size)
        return tuple(sshape)

    @property
    def _mem_external(self):
        """Return True if the associated data was/is/will be allocated directly
        from Python (e.g., via NumPy arrays), False otherwise."""
        return False

    @property
    def _mem_stack(self):
        """Return True if the associated data was/is/will be allocated on the stack
        in a C module, False otherwise."""
        return False

    @property
    def _mem_heap(self):
        """Return True if the associated data was/is/will be allocated on the heap
        in a C module, False otherwise."""
        return False

    @property
    def size(self):
        """Return the number of elements this function is expected to store in memory.
           Note that this would need to be combined with self.dtype to give the actual
           size in bytes
        """
        return reduce(mul, self.shape)

    def indexify(self, indices=None):
        """Create a :class:`sympy.Indexed` object from the current object."""
        if indices is not None:
            return Indexed(self.indexed, *indices)

        subs = dict([(i.spacing, 1) for i in self.indices])
        indices = [a.subs(subs) for a in self.args]
        return Indexed(self.indexed, *indices)


class SymbolicData(AbstractCachedFunction):

    """
    A symbolic function object, created and managed directly by Devito.

    Unlike :class:`SymbolicFunction` objects, the state of a SymbolicData
    is mutable.
    """

    is_SymbolicData = True

    def __new__(cls, *args, **kwargs):
        kwargs.update({'options': {'evaluate': False}})
        return AbstractCachedFunction.__new__(cls, *args, **kwargs)

    def update(self):
        return


class Scalar(Symbol):
    """Symbolic object representing a scalar.

    :param name: Name of the symbol
    :param dtype: Data type of the scalar
    """

    is_Scalar = True

    def __init__(self, *args, **kwargs):
        if not self._cached():
            self.dtype = kwargs.get('dtype', np.float32)

    @property
    def _mem_stack(self):
        """Return True if the associated data should be allocated on the stack
        in a C module, False otherwise."""
        return True

    def update(self, dtype=None, **kwargs):
        self.dtype = dtype or self.dtype


class Array(SymbolicData):
    """Symbolic object representing a tensor.

    :param name: Name of the symbol
    :param dtype: Data type of the scalar
    :param shape: The shape of the tensor
    :param dimensions: The symbolic dimensions of the tensor.
    :param external: Pass True if there is no need to allocate storage
    :param onstack: Pass True to enforce allocation on the stack
    :param onheap: Pass True to enforce allocation on the heap
    """

    is_Array = True
    is_Tensor = True

    def __init__(self, *args, **kwargs):
        if not self._cached():
            self.name = kwargs.get('name')
            self.shape = kwargs.get('shape')
            self.indices = kwargs.get('dimensions')
            self.dtype = kwargs.get('dtype', np.float32)

            self._external = bool(kwargs.get('external', False))
            self._onstack = bool(kwargs.get('onstack', False))
            self._onheap = bool(kwargs.get('onheap', True))

            # The memory scope of an Array must be well-defined
            assert single_or([self._external, self._onstack, self._onheap])

    @classmethod
    def _indices(cls, **kwargs):
        return kwargs.get('dimensions')

    @property
    def _mem_external(self):
        return self._external

    @property
    def _mem_stack(self):
        return self._onstack

    @property
    def _mem_heap(self):
        return self._onheap

    def update(self, dtype=None, shape=None, dimensions=None, onstack=None,
               onheap=None, external=None):
        self.dtype = dtype or self.dtype
        self.shape = shape or self.shape
        self.indices = dimensions or self.indices

        if any(i is not None for i in [external, onstack, onheap]):
            self._external = bool(external)
            self._onstack = bool(onstack)
            self._onheap = bool(onheap)
            assert single_or([self._external, self._onstack, self._onheap])


class SymbolicFunction(AbstractCachedFunction):
    """A symbolic object associated with data.

    Unlike :class:`SymbolicData` objects, the structure of a SymbolicFunction
    is immutable (e.g., shape, dtype, ...). Obviously, the object value (``data``)
    may be altered, either directly by the user or by an :class:`Operator`.
    """

    is_SymbolicFunction = True

    @property
    def _data_buffer(self):
        """Reference to the actual data. This is *not* a view of the data.
        This method is for internal use only."""
        return self.data

    @abc.abstractproperty
    def data(self):
        """The value of the data object."""
        return


# Objects belonging to the Devito API not involving data, such as data structures
# that need to be passed to external libraries


class Object(object):

    """
    Represent a generic pointer object.
    """

    is_Object = True

    def __init__(self, name, dtype, value=None):
        self.name = name
        self.dtype = dtype
        self.value = value

    def __repr__(self):
        return self.name


# Extended SymPy hierarchy follows, for essentially two reasons:
# - To keep track of `function`
# - To override SymPy caching behaviour


class IndexedData(sympy.IndexedBase):
    """Wrapper class that inserts a pointer to the symbolic data object"""

    def __new__(cls, label, shape=None, function=None):
        obj = sympy.IndexedBase.__new__(cls, label, shape)
        obj.function = function
        return obj

    def func(self, *args):
        obj = super(IndexedData, self).func(*args)
        obj.function = self.function
        return obj

    def __getitem__(self, indices, **kwargs):
        """
        Return :class:`Indexed`, rather than :class:`sympy.Indexed`.
        """
        indexed = super(IndexedData, self).__getitem__(indices, **kwargs)
        return Indexed(*indexed.args)


class Indexed(sympy.Indexed):

    # The two type flags have changed in upstream sympy as of version 1.1,
    # but the below interpretation is used throughout the DSE and DLE to
    # identify Indexed objects. With the sympy-1.1 changes a new flag
    # obj.is_Indexed was introduced which should be preferred, but the
    # required changes are cumbersome and many...
    is_Symbol = False
    is_Atom = False

    def _hashable_content(self):
        return super(Indexed, self)._hashable_content() + (self.base.function,)


# Utilities


class CacheManager(object):

    """
    Drop unreferenced objects from the SymPy and Devito caches. The associated
    data is lost (and thus memory is freed).
    """

    @classmethod
    def clear(cls):
        sympy.cache.clear_cache()
        gc.collect()
        for key, val in list(_SymbolCache.items()):
            if val() is None:
                del _SymbolCache[key]
