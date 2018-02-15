"""
Extended SymPy hierarchy.
"""

import sympy
from sympy import Expr, Float
from sympy.core.basic import _aresame
from sympy.functions.elementary.trigonometric import TrigonometricFunction

from devito.region import DOMAIN
from devito.tools import as_tuple

__all__ = ['FrozenExpr', 'Eq', 'CondEq', 'CondNe', 'Inc', 'Mul', 'Add', 'IntDiv',
           'FunctionFromPointer', 'ListInitializer', 'taylor_sin', 'taylor_cos',
           'bhaskara_sin', 'bhaskara_cos']


class FrozenExpr(Expr):

    """
    Use :class:`FrozenExpr` in place of :class:`sympy.Expr` to make sure than
    an expression is no longer transformable; that is, standard manipulations
    such as xreplace, collect, expand, ... have no effect, thus building a
    new expression identical to self.

    :Notes:

    At the moment, only xreplace is overridded (to prevent unpicking factorizations)
    """

    def xreplace(self, rule):
        if self in rule:
            return rule[self]
        elif rule:
            args = []
            for a in self.args:
                try:
                    args.append(a.xreplace(rule))
                except AttributeError:
                    args.append(a)
            args = tuple(args)
            if not _aresame(args, self.args):
                return self.func(*args, evaluate=False)
        return self


class Eq(sympy.Eq, FrozenExpr):

    """A customized version of :class:`sympy.Eq` which suppresses evaluation."""

    is_Increment = False

    def __new__(cls, *args, **kwargs):
        kwargs['evaluate'] = False
        region = kwargs.pop('region', DOMAIN)
        obj = sympy.Eq.__new__(cls, *args, **kwargs)
        obj._region = region
        return obj


class CondEq(sympy.Eq, FrozenExpr):
    """A customized version of :class:`sympy.Eq` representing a conditional
    equality. It suppresses evaluation."""

    def __new__(cls, *args, **kwargs):
        kwargs['evaluate'] = False
        return sympy.Eq.__new__(cls, *args, **kwargs)


class CondNe(sympy.Ne, FrozenExpr):
    """A customized version of :class:`sympy.Ne` representing a conditional
    inequality. It suppresses evaluation."""

    def __new__(cls, *args, **kwargs):
        kwargs['evaluate'] = False
        return sympy.Ne.__new__(cls, *args, **kwargs)


class Inc(Eq):
    """
    A special :class:`Eq` carrying the information that a linear increment is
    performed.
    """

    is_Increment = True


class Mul(sympy.Mul, FrozenExpr):
    pass


class Add(sympy.Add, FrozenExpr):
    pass


class IntDiv(sympy.Expr):

    """
    A support type for integer division. Should only be used by the compiler
    for code generation purposes (i.e., not for symbolic manipulation).
    This works around the annoying way SymPy represents integer division,
    namely as a ``Mul`` between the numerator and the reciprocal of the
    denominator (e.g., ``a*3.args -> (a, 1/3)), which ends up generating
    "weird" C code.
    """
    is_Atom = True

    def __new__(cls, lhs, rhs, params=None):
        obj = sympy.Expr.__new__(cls)
        obj.lhs = lhs
        obj.rhs = rhs
        return obj

    def __str__(self):
        return "%s / %s" % (self.lhs, self.rhs)

    __repr__ = __str__


class FunctionFromPointer(sympy.Expr):

    """
    Symbolic representation of the C notation ``pointer->function(params)``.
    """

    def __new__(cls, function, pointer, params=None):
        obj = sympy.Expr.__new__(cls)
        obj.function = function
        obj.pointer = pointer
        obj.params = as_tuple(params)
        return obj

    def __str__(self):
        return '%s->%s(%s)' % (self.pointer, self.function,
                               ", ".join(str(i) for i in as_tuple(self.params)))

    __repr__ = __str__

    def _hashable_content(self):
        return super(FunctionFromPointer, self)._hashable_content() +\
            (self.function, self.pointer) + self.params


class ListInitializer(sympy.Symbol):

    """
    Symbolic representation of the C++ list initializer notation ``{a, b, ...}``.
    """

    def __new__(cls, params):
        obj = sympy.Symbol.__new__(cls, ','.join('%s' % i for i in params))
        obj.params = params or ()
        return obj

    def __str__(self):
        return "{%s}" % ", ".join(str(i) for i in self.params)

    __repr__ = __str__


class taylor_sin(TrigonometricFunction):

    """
    Approximation of the sine function using a Taylor polynomial.
    """

    @classmethod
    def eval(cls, arg):
        return eval_taylor_sin(arg)


class taylor_cos(TrigonometricFunction):

    """
    Approximation of the cosine function using a Taylor polynomial.
    """

    @classmethod
    def eval(cls, arg):
        return 1.0 if arg == 0.0 else eval_taylor_cos(arg)


class bhaskara_sin(TrigonometricFunction):

    """
    Approximation of the sine function using a Bhaskara polynomial.
    """

    @classmethod
    def eval(cls, arg):
        return eval_bhaskara_sin(arg)


class bhaskara_cos(TrigonometricFunction):

    """
    Approximation of the cosine function using a Bhaskara polynomial.
    """

    @classmethod
    def eval(cls, arg):
        return 1.0 if arg == 0.0 else eval_bhaskara_sin(arg + 1.5708)


# Utils

def eval_bhaskara_sin(expr):
    return 16.0*expr*(3.1416-abs(expr))/(49.3483-4.0*abs(expr)*(3.1416-abs(expr)))


def eval_taylor_sin(expr):
    v = expr + Mul(-1/6.0,
                   Mul(expr, expr, expr, evaluate=False),
                   1.0 + Mul(Mul(expr, expr, evaluate=False), -0.05, evaluate=False),
                   evaluate=False)
    try:
        Float(expr)
        return v.doit()
    except (TypeError, ValueError):
        return v


def eval_taylor_cos(expr):
    v = 1.0 + Mul(-0.5,
                  Mul(expr, expr, evaluate=False),
                  1.0 + Mul(expr, expr, -1/12.0, evaluate=False),
                  evaluate=False)
    try:
        Float(expr)
        return v.doit()
    except (TypeError, ValueError):
        return v
