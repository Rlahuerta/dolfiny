import numpy
from mpi4py import MPI

import dolfinx
from dolfinx.io import XDMFFile
import dolfiny.mesh
import ufl


def test_simple_triangle():
    import gmsh

    gmsh.initialize()
    gmsh.model.add("test")

    p0 = gmsh.model.geo.addPoint(0.0, 0.0, 0.0)
    p1 = gmsh.model.geo.addPoint(1.0, 0.0, 0.0)
    p2 = gmsh.model.geo.addPoint(1.0, 1.0, 0.0)
    p3 = gmsh.model.geo.addPoint(0.0, 1.0, 0.0)
    p4 = gmsh.model.geo.addPoint(1.0, 0.5, 0.0)

    l0 = gmsh.model.geo.addLine(p0, p1)
    l1 = gmsh.model.geo.addCircleArc(p1, p4, p2)
    l2 = gmsh.model.geo.addLine(p2, p3)
    l3 = gmsh.model.geo.addLine(p3, p0)

    cl0 = gmsh.model.geo.addCurveLoop([l0, l1, l2, l3])
    s0 = gmsh.model.geo.addPlaneSurface([cl0])

    gmsh.model.addPhysicalGroup(1, [l0, l2], 2)
    gmsh.model.setPhysicalName(1, 2, "sides")

    gmsh.model.addPhysicalGroup(1, [l1], 3)
    gmsh.model.setPhysicalName(1, 3, "arc")

    gmsh.model.addPhysicalGroup(2, [s0], 4)
    gmsh.model.setPhysicalName(2, 4, "surface")

    gmsh.model.geo.synchronize()
    gmsh.model.mesh.generate()
    gmsh.model.mesh.setOrder(2)

    mesh, mts = dolfiny.mesh.gmsh_to_dolfin(gmsh.model, 2, prune_z=True)

    assert mesh.geometry.dim == 2
    assert mesh.topology.dim == 2
    assert mts["arc"].dim == 1

    with XDMFFile(MPI.COMM_WORLD, "mesh.xdmf", "w") as file:
        file.write_mesh(mesh)
        mesh.topology.create_connectivity(1, 2)
        file.write_meshtags(mts["arc"])

    ds_arc = ufl.Measure("ds", subdomain_data=mts["arc"], domain=mesh, subdomain_id=3)

    val = dolfinx.fem.assemble_scalar(1.0 * ds_arc)
    val = mesh.mpi_comm().allreduce(val, op=MPI.SUM)
    assert numpy.isclose(val, 2.0 * numpy.pi * 0.5 / 2.0, rtol=1.0e-3)
