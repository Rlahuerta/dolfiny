import dolfiny.expression
import ufl
import dolfinx

import numpy


def test_expression_evaluate(V1, V2, squaremesh_5):

    u1, v1 = ufl.TrialFunction(V1), ufl.TestFunction(V1)
    u2, v2 = ufl.TrialFunction(V2), ufl.TestFunction(V2)

    dx = ufl.dx(squaremesh_5)

    # Test evaluation of expressions

    assert dolfiny.expression.evaluate(1 * u1, u1, u2) == 1 * u2
    assert dolfiny.expression.evaluate(2 * u1 + u2, u1, u2) == 2 * u2 + 1 * u2
    assert dolfiny.expression.evaluate(u1**2 + u2, u1, u2) == u2**2 + 1 * u2

    assert dolfiny.expression.evaluate(u1 + u2, [u1, u2], [v1, v2]) == v1 + v2
    assert dolfiny.expression.evaluate([u1, u2], u1, v1) == [v1, u2]
    assert dolfiny.expression.evaluate([u1, u2], [u1, u2], [v1, v2]) == [v1, v2]

    # Test evaluation of forms

    assert dolfiny.expression.evaluate(1 * u1 * dx, u1, u2) == 1 * u2 * dx
    assert dolfiny.expression.evaluate(2 * u1 * dx + u2 * dx, u1, u2) == 2 * u2 * dx + 1 * u2 * dx
    assert dolfiny.expression.evaluate(u1**2 * dx + u2 * dx, u1, u2) == u2**2 * dx + 1 * u2 * dx

    assert dolfiny.expression.evaluate(u1 * dx + u2 * dx, [u1, u2], [v1, v2]) == v1 * dx + v2 * dx
    assert dolfiny.expression.evaluate([u1 * dx, u2 * dx], u1, v1) == [v1 * dx, u2 * dx]
    assert dolfiny.expression.evaluate([u1 * dx, u2 * dx], [u1, u2], [v1, v2]) == [v1 * dx, v2 * dx]


def test_expression_derivative(V1, V2, squaremesh_5):

    u1, du1, v1 = dolfinx.Function(V1), ufl.TrialFunction(V1), ufl.TestFunction(V1)
    u2, du2, v2 = dolfinx.Function(V2), ufl.TrialFunction(V2), ufl.TestFunction(V2)

    dx = ufl.dx(squaremesh_5)

    # Test derivative of expressions

    assert dolfiny.expression.derivative(1 * u1, u1, du1) == 1 * du1
    assert dolfiny.expression.derivative(2 * u1 + u2, u1, du1) == 2 * du1
    assert dolfiny.expression.derivative(u1**2 + u2, u1, du1) == du1 * 2 * u1

    assert dolfiny.expression.derivative(u1 + u2, [u1, u2], [v1, v2]) == v1 + v2
    assert dolfiny.expression.derivative([u1, u2], u1, v1) == [v1, 0]
    assert dolfiny.expression.derivative([u1, u2], [u1, u2], [v1, v2]) == [v1, v2]

    # Test derivative of forms

    assert dolfiny.expression.derivative(1 * u1 * dx, u1, du1) == 1 * du1 * dx
    assert dolfiny.expression.derivative(2 * u1 * dx + u2 * dx, u1, du1) == 2 * du1 * dx
    assert dolfiny.expression.derivative(u1**2 * dx + u2 * dx, u1, du2) == du2 * 2 * u1 * dx

    assert dolfiny.expression.derivative(u1 * dx + u2 * dx, [u1, u2], [v1, v2]) == v1 * dx + v2 * dx
    assert dolfiny.expression.derivative([u1 * dx, u2 * dx], u1, v1) == [v1 * dx, ufl.Form([])]
    assert dolfiny.expression.derivative([u1 * dx, u2 * dx], [u1, u2], [v1, v2]) == [v1 * dx, v2 * dx]

    # Test derivative of expressions at u0

    u10, u20 = dolfinx.Function(V1), dolfinx.Function(V2)

    assert dolfiny.expression.derivative(1 * u1, u1, du1, u0=u10) == 1 * du1
    assert dolfiny.expression.derivative(2 * u1 + u2, u1, du1, u0=u10) == 2 * du1
    assert dolfiny.expression.derivative(u1**2 + u2, u1, du1, u0=u10) == du1 * 2 * u10

    assert dolfiny.expression.derivative(u1**2 + u2**2, [u1, u2], [v1, v2], [u10, u20]) == v1 * 2 * u10 + v2 * 2 * u20
    assert dolfiny.expression.derivative([u1**2, u2], u1, v1, u0=u10) == [v1 * 2 * u10, 0]
    assert dolfiny.expression.derivative([u1**2 + u2, u2], [u1, u2], [v1, v2], [u10, u20]) == [v1 * 2 * u10 + v2, v2]


def test_expression_linearise(V1, V2, squaremesh_5):

    u1, u10 = dolfinx.Function(V1), dolfinx.Function(V1)
    u2, u20 = dolfinx.Function(V2), dolfinx.Function(V2)

    dx = ufl.dx(squaremesh_5)

    # Test linearisation of expressions at u0

    assert dolfiny.expression.linearise(1 * u1, u1, u0=u10) == \
        u10 + (u1 + (-1) * u10)
    assert dolfiny.expression.linearise(2 * u1 + u2, u1, u0=u10) == \
        (u2 + 2 * u10) + (2 * u1 + (-1) * (2 * u10))
    assert dolfiny.expression.linearise(u1**2 + u2, u1, u0=u10) == \
        (u10 * (2 * u1) + (-1) * (u10 * 2 * u10)) + (u10**2 + u2)

    assert dolfiny.expression.linearise(u1**2 + u2**2, [u1, u2], u0=[u10, u20]) == \
        (u10 * (2 * u1) + u20 * (2 * u2) + (-1) * (u10 * (2 * u10) + u20 * (2 * u20))) + (u10**2 + u20**2)
    assert dolfiny.expression.linearise([u1**2, u2], u1, u0=u10) == \
        [(u10 * (2 * u1) + (-1) * (u10 * 2 * u10)) + u10**2, u2]
    assert dolfiny.expression.linearise([u1**2 + u2, u2], [u1, u2], u0=[u10, u20]) == \
        [(u10 * (2 * u1) + u2 + (-1) * (u10 * (2 * u10) + u20)) + (u10**2 + u20), (u2 + (-1) * u20) + u20]

    # Test linearisation of forms at u0

    assert dolfiny.expression.linearise(1 * u1 * dx, u1, u0=u10) == \
        u10 * dx + (u1 * dx + (-1) * u10 * dx)
    assert dolfiny.expression.linearise([u1**2 * dx, u2 * dx], u1, u0=u10) == \
        [u10**2 * dx + u10 * (2 * u1) * dx + (-1) * (u10 * 2 * u10) * dx, u2 * dx]


def test_expression_assemble(V1, vV1, squaremesh_5):

    u1, u2 = dolfinx.Function(V1), dolfinx.Function(vV1)

    dx = ufl.dx(squaremesh_5)

    u1.vector.set(3.0)
    u2.vector.set(2.0)
    u1.vector.ghostUpdate()
    u2.vector.ghostUpdate()

    # check assembled shapes

    assert numpy.shape(dolfiny.expression.assemble(1.0, dx)) == ()
    assert numpy.shape(dolfiny.expression.assemble(ufl.grad(u1), dx)) == (2,)
    assert numpy.shape(dolfiny.expression.assemble(ufl.grad(u2), dx)) == (2, 2)

    # check assembled values

    assert numpy.isclose(dolfiny.expression.assemble(1.0, dx), 1.0)
    assert numpy.isclose(dolfiny.expression.assemble(u1, dx), 3.0)
    assert numpy.isclose(dolfiny.expression.assemble(u2, dx), 2.0).all()
    assert numpy.isclose(dolfiny.expression.assemble(u1 * u2, dx), 6.0).all()

    assert numpy.isclose(dolfiny.expression.assemble(ufl.grad(u1), dx), 0.0).all()
    assert numpy.isclose(dolfiny.expression.assemble(ufl.grad(u2), dx), 0.0).all()
