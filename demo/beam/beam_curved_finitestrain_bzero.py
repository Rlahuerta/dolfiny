#!/usr/bin/env python3

import numpy as np
from petsc4py import PETSc
from mpi4py import MPI

import dolfinx
import ufl

import dolfiny.io
import dolfiny.mesh
import dolfiny.utils
import dolfiny.function
import dolfiny.expression
import dolfiny.interpolation
import dolfiny.snesblockproblem

import mesh_curve3d_gmshapi as mg
import postprocess_matplotlib as pp

# Basic settings
name = "beam_curved_finitestrain_bzero"
comm = MPI.COMM_WORLD

# Geometry and mesh parameters
L = 1.0  # beam length
N = 8 * 4  # number of nodes
p = 2  # physics: polynomial order
q = 2  # geometry: polynomial order

# Create the regular mesh of an annulus with given dimensions
gmsh_model, tdim = mg.mesh_curve3d_gmshapi(name, shape="f_arc", L=L, nL=N, order=q)

# # Create the regular mesh of an annulus with given dimensions and save as msh, then read into gmsh model
# mg.mesh_curve3d_gmshapi(name, shape="xline", L=L, nL=N, order=q, msh_file=f"{name}.msh")
# gmsh_model, tdim = dolfiny.mesh.msh_to_gmsh(f"{name}.msh")

# Get mesh and meshtags
mesh, mts = dolfiny.mesh.gmsh_to_dolfin(gmsh_model, tdim)

# # Write mesh and meshtags to file
# with dolfiny.io.XDMFFile(comm, f"{name}.xdmf", "w") as ofile:
#     ofile.write_mesh_meshtags(mesh, mts)

# # Read mesh and meshtags from file
# with dolfiny.io.XDMFFile(comm, f"{name}.xdmf", "r") as ifile:
#     mesh, mts = ifile.read_mesh_meshtags()

# Get merged MeshTags for each codimension
subdomains, subdomains_keys = dolfiny.mesh.merge_meshtags(mts, tdim - 0)
interfaces, interfaces_keys = dolfiny.mesh.merge_meshtags(mts, tdim - 1)

# Define shorthands for labelled tags
beg = interfaces_keys["beg"]
end = interfaces_keys["end"]

# Structure: section geometry
b = 1.0  # [m]
h = L / 500  # [m]
A = b * h  # [m^2]
I = b * h**3 / 12  # [m^4]  # noqa: E741

# Structure: material parameters
n = 0  # [-] Poisson ratio
E = 1.0e+8  # [N/m^2] elasticity modulus
lamé_λ = E * n / (1 + n) / (1 - 2 * n)  # Lamé constant λ
lamé_μ = E / 2 / (1 + n)  # Lamé constant μ


def S(E):
    """
    Stress as function of strain from strain energy function
    """
    E = ufl.variable(E)
    W = lamé_μ * ufl.inner(E, E) + lamé_λ / 2 * ufl.tr(E)**2  # Saint-Venant Kirchhoff
    S = ufl.diff(W, E)
    return S


# Structure: shear correction factor, see Cowper (1966)
sc_fac = 10 * (1 + n) / (12 + 11 * n)

# Structure: load parameters
μ = dolfinx.Constant(mesh, 1.0)  # load factor

p_x = μ * dolfinx.Constant(mesh, 1.0 * 0)
p_z = μ * dolfinx.Constant(mesh, 1.0 * 0)
m_y = μ * dolfinx.Constant(mesh, 1.0 * 0)

F_x = μ * dolfinx.Constant(mesh, (2.0 * np.pi / L)**2 * E * I * 0)  # prescribed F_x: 2, 4
F_z = μ * dolfinx.Constant(mesh, (0.5 * np.pi / L)**2 * E * I * 0)  # prescribed F_z: 4, 8
M_y = μ * dolfinx.Constant(mesh, (2.0 * np.pi / L)**1 * E * I * 1)  # prescribed M_y: 1, 2

# Define integration measures
dx = ufl.Measure("dx", domain=mesh, subdomain_data=subdomains)
ds = ufl.Measure("ds", domain=mesh, subdomain_data=interfaces)

# Function spaces
Ue = ufl.FiniteElement("CG", mesh.ufl_cell(), p)
We = ufl.FiniteElement("CG", mesh.ufl_cell(), p)
Re = ufl.FiniteElement("CG", mesh.ufl_cell(), p)

U = dolfinx.FunctionSpace(mesh, Ue)
W = dolfinx.FunctionSpace(mesh, We)
R = dolfinx.FunctionSpace(mesh, Re)

# Define functions
u = dolfinx.Function(U, name='u')
w = dolfinx.Function(W, name='w')
r = dolfinx.Function(R, name='r')

δu = ufl.TestFunction(U)
δw = ufl.TestFunction(W)
δr = ufl.TestFunction(R)

# Define state as (ordered) list of functions
m = [u, w, r]
δm = [δu, δw, δr]

# GEOMETRY -------------------------------------------------------------------
# Coordinates of undeformed configuration
x0 = ufl.SpatialCoordinate(mesh)

# Function spaces for geometric quantities extracted from mesh
N = dolfinx.VectorFunctionSpace(mesh, ("DG", q), mesh.geometry.dim)

# Normal vector (gdim x 1)
n0i = dolfinx.Function(N)

# Jacobi matrix of map reference -> undeformed
J0 = ufl.geometry.Jacobian(mesh)
# Tangent basis
gs = J0[:, 0]
gη = ufl.as_vector([0, 1, 0])  # unit vector e_y (assume curve in x-z plane)
gξ = ufl.cross(gs, gη)
# Unit tangent basis
gs /= ufl.sqrt(ufl.dot(gs, gs))
gη /= ufl.sqrt(ufl.dot(gη, gη))
gξ /= ufl.sqrt(ufl.dot(gξ, gξ))
# Interpolate normal vector
dolfiny.interpolation.interpolate(gξ, n0i)
# ----------------------------------------------------------------------------

# Orthogonal projection operator (assumes sufficient geometry approximation)
P = ufl.Identity(mesh.geometry.dim) - ufl.outer(n0i, n0i)

# Thickness variable
X = dolfinx.FunctionSpace(mesh, ("DG", q))
ξ = dolfinx.Function(X, name='ξ')

# Undeformed configuration: director d0 and placement b0
d0 = n0i  # normal of manifold mesh, interpolated
b0 = x0 + ξ * d0

# Deformed configuration: director d and placement b, assumed kinematics, director uses rotation matrix
d = ufl.as_matrix([[ufl.cos(r), 0, ufl.sin(r)], [0, 1, 0], [-ufl.sin(r), 0, ufl.cos(r)]]) * d0
b = x0 + ufl.as_vector([u, 0, w]) + ξ * d

# Configuration gradient, undeformed configuration
J0 = ufl.grad(b0) - ufl.outer(d0, d0)  # = P * ufl.grad(x0) + ufl.grad(ξ * d0)
J0 = ufl.algorithms.apply_algebra_lowering.apply_algebra_lowering(J0)
J0 = ufl.algorithms.apply_derivatives.apply_derivatives(J0)
J0 = ufl.replace(J0, {ufl.grad(ξ): d0})

# Configuration gradient, deformed configuration
J = ufl.grad(b) - ufl.outer(d0, d0)  # = P * ufl.grad(x0) + ufl.grad(ufl.as_vector([u, 0, w]) + ξ * d)
J = ufl.algorithms.apply_algebra_lowering.apply_algebra_lowering(J)
J = ufl.algorithms.apply_derivatives.apply_derivatives(J)
J = ufl.replace(J, {ufl.grad(ξ): d0})

# Green-Lagrange strains (total): determined by deformation kinematics
E_total = 1 / 2 * (J.T * J - J0.T * J0)

# Green-Lagrange strains (elastic): E_total = E_elast + E_presc
E = E_elast = E_total

# Membrane strain
Em = P * ufl.replace(E, {ξ: 0.0}) * P

# Bending strain
Eb = ufl.diff(E, ξ)
Eb = ufl.algorithms.apply_algebra_lowering.apply_algebra_lowering(Eb)
Eb = ufl.algorithms.apply_derivatives.apply_derivatives(Eb)
Eb = P * ufl.replace(Eb, {ξ: 0.0}) * P

# Shear strain
Es = ufl.replace(E, {ξ: 0.0}) - P * ufl.replace(E, {ξ: 0.0}) * P

# Variation of elastic Green-Lagrange strains
δEm = dolfiny.expression.derivative(Em, m, δm)
δEs = dolfiny.expression.derivative(Es, m, δm)
δEb = dolfiny.expression.derivative(Eb, m, δm)

# Stress resultant tensors
N = S(Em) * A
T = S(Es) * A * sc_fac
M = S(Eb) * I

# Partial selective reduced integration of membrane/shear virtual work, see Arnold/Brezzi (1997)
A = dolfinx.FunctionSpace(mesh, ("DG", 0))
α = dolfinx.Function(A)
dolfiny.interpolation.interpolate(h**2 / ufl.JacobianDeterminant(mesh), α)

# Weak form: components (as one-form)
F = - ufl.inner(δEm, N) * α * dx - ufl.inner(δEm, N) * (1 - α) * dx(metadata={"quadrature_degree": p * (p - 1)}) \
    - ufl.inner(δEs, T) * α * dx - ufl.inner(δEs, T) * (1 - α) * dx(metadata={"quadrature_degree": p * (p - 1)}) \
    - ufl.inner(δEb, M) * dx \
    + δu * p_x * dx \
    + δw * p_z * dx \
    + δr * m_y * dx \
    + δu * F_x * ds(end) \
    + δw * F_z * ds(end) \
    + δr * M_y * ds(end)

# Optional: linearise weak form
# F = dolfiny.expression.linearise(F, m)  # linearise around zero state

# Overall form (as list of forms)
F = dolfiny.function.extract_blocks(F, δm)

# Create output xdmf file -- open in Paraview with Xdmf3ReaderT
ofile = dolfiny.io.XDMFFile(comm, f"{name}.xdmf", "w")
# Write mesh, meshtags
if q <= 2:
    ofile.write_mesh_meshtags(mesh, mts)

# Options for PETSc backend
opts = PETSc.Options("beam")

opts["snes_type"] = "newtonls"
opts["snes_linesearch_type"] = "basic"
opts["snes_atol"] = 1.0e-07
opts["snes_rtol"] = 1.0e-07
opts["snes_stol"] = 1.0e-06
opts["snes_max_it"] = 60
opts["ksp_type"] = "preonly"
opts["pc_type"] = "lu"
opts["pc_factor_mat_solver_type"] = "mumps"

opts_global = PETSc.Options()
opts_global["mat_mumps_icntl_14"] = 500
opts_global["mat_mumps_icntl_24"] = 1

# Create nonlinear problem: SNES
problem = dolfiny.snesblockproblem.SNESBlockProblem(F, m, prefix="beam")

# Identify dofs of function spaces associated with tagged interfaces/boundaries
beg_dofs_U = dolfiny.mesh.locate_dofs_topological(U, interfaces, beg)
beg_dofs_W = dolfiny.mesh.locate_dofs_topological(W, interfaces, beg)
beg_dofs_R = dolfiny.mesh.locate_dofs_topological(R, interfaces, beg)

u_beg = dolfinx.Function(U)
w_beg = dolfinx.Function(W)
r_beg = dolfinx.Function(R)

# Create custom plotter (via matplotlib)
plotter = pp.Plotter(f"{name}.pdf", r'finite strain beam (1st order shear, displacement-based, on $\mathcal{B}_{0}$)')

# Create vector function space and vector function for writing the displacement vector
Z = dolfinx.VectorFunctionSpace(mesh, ("CG", p), mesh.geometry.dim)
z = dolfinx.Function(Z)

# Process load steps
for factor in np.linspace(0, 1, num=20 + 1):

    # Set current time
    μ.value = factor

    # Set/update boundary conditions
    problem.bcs = [
        dolfinx.fem.DirichletBC(u_beg, beg_dofs_U),  # u beg
        dolfinx.fem.DirichletBC(w_beg, beg_dofs_W),  # w beg
        dolfinx.fem.DirichletBC(r_beg, beg_dofs_R),  # r beg
    ]

    dolfiny.utils.pprint(f"\n+++ Processing load factor μ = {μ.value:5.4f}")

    # Solve nonlinear problem
    m = problem.solve()

    # Assert convergence of nonlinear solver
    assert problem.snes.getConvergedReason() > 0, "Nonlinear solver did not converge!"

    # Add to plot
    if comm.size == 1:
        plotter.add(mesh, q, m, μ)

    # Write output
    if q <= 2:
        dolfiny.interpolation.interpolate(ufl.as_vector([u, 0, w]), z)
        ofile.write_function(z, μ.value)

ofile.close()