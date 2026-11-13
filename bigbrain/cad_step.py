"""Analytic STEP measurements through OpenCascade with native-body matching."""

import math
from pathlib import Path


def inspect_step(path: Path, native_bodies):
    """Validate exported solids and integrate their surfaces without meshing."""
    try:
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepBndLib import BRepBndLib
        from OCP.BRepGProp import BRepGProp
        from OCP.Bnd import Bnd_Box
        from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
        from OCP.GProp import GProp_GProps
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
        from OCP.TopExp import TopExp, TopExp_Explorer
        from OCP.TopoDS import TopoDS
    except ImportError as error:
        raise ValueError('Analytic CAD inspection requires the cadquery-ocp-novtk CAD dependency') from error

    def explore(shape, kind):
        explorer = TopExp_Explorer(shape, kind)
        while explorer.More():
            yield explorer.Current()
            explorer.Next()

    def xyz(point):
        return [point.X(), point.Y(), point.Z()]

    shape = load_step_shape(path)
    solids = list(explore(shape, TopAbs_SOLID))
    if not solids or len(solids) != len(native_bodies):
        raise ValueError('STEP solid count differs from the native body inventory')
    bodies = {}
    for solid in solids:
        if not all(BRep_Tool.IsClosed_s(shell) for shell in explore(solid, TopAbs_SHELL)):
            raise ValueError('STEP solid has an open shell')
        bounds = Bnd_Box()
        BRepBndLib.AddOptimal_s(solid, bounds, False, False)
        coordinates = bounds.Get()
        # Native boxes may come from a mesh. This tolerance selects identity;
        # requirement checks subsequently use the analytic bounds themselves.
        matches = native_bodies if len(solids) == 1 else [body for body in native_bodies if all(
            abs(a-b) <= 0.05 for a, b in zip(coordinates, (*body['bbox']['min'], *body['bbox']['max'])))]
        if len(matches) != 1 or matches[0]['name'] in bodies:
            raise ValueError('STEP solid cannot be matched unambiguously to a native body')
        properties = GProp_GProps()
        # Adaptive integration on the actual surfaces; triangulations are disabled.
        error = BRepGProp.VolumeProperties_s(solid, properties, 1e-10, True, False)
        volume = properties.Mass()
        if not math.isfinite(volume) or volume <= 0 or not math.isfinite(error) or error > 1e-8:
            raise ValueError('STEP volume integration failed its accuracy check')
        faces = []
        for index, raw in enumerate(explore(solid, TopAbs_FACE)):
            face = TopoDS.Face_s(raw)
            surface = BRepAdaptor_Surface(face, True)
            item = {'index': index, 'analytic_surface': False}
            area = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, area)
            item.update(area=area.Mass(), centroid=xyz(area.CentreOfMass()))
            if surface.GetType() == GeomAbs_Cylinder:
                cylinder = surface.Cylinder()
                item.update(analytic_surface=True, cylinder={
                    'origin': xyz(cylinder.Location()), 'axis': xyz(cylinder.Axis().Direction()),
                    'radius': cylinder.Radius()})
            elif surface.GetType() == GeomAbs_Plane:
                item.update(analytic_surface=True, plane_normal=xyz(surface.Plane().Axis().Direction()))
            faces.append(item)
        edges = []
        for raw in explore(solid, TopAbs_EDGE):
            edge = TopoDS.Edge_s(raw)
            first, last = TopExp.FirstVertex_s(edge), TopExp.LastVertex_s(edge)
            if not first.IsNull() and not last.IsNull():
                edges.append({'start': xyz(BRep_Tool.Pnt_s(first)), 'end': xyz(BRep_Tool.Pnt_s(last))})
        name = matches[0]['name']
        bodies[name] = {'body': name, 'faces': faces, 'edges': edges, 'volume_mm3': volume,
            'integration_relative_error': error, 'bounds_min_mm': list(coordinates[:3]),
            'bounds_max_mm': list(coordinates[3:])}
    return {'method': 'occt-step-surfaces', 'units': 'mm', 'bodies': bodies,
            'volume_mm3': sum(body['volume_mm3'] for body in bodies.values())}


def load_step_shape(path):
    """Load millimetre STEP geometry and reject invalid or loose surfaces."""
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError('STEP reader rejected the exported artifact')
    reader.SetSystemLengthUnit(1.0)  # All returned coordinates are millimetres.
    if not reader.TransferRoots():
        raise ValueError('STEP reader transferred no geometry')
    shape = reader.OneShape()
    if shape.IsNull() or not BRepCheck_Analyzer(shape).IsValid():
        raise ValueError('Exported STEP has an invalid boundary representation')
    loose = TopExp_Explorer(shape, TopAbs_FACE, TopAbs_SOLID)
    if loose.More():
        raise ValueError('Exported STEP contains faces outside its solids')
    return shape
