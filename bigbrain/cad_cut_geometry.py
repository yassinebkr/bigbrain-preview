"""Independent exact-surface checks of cutter overruns against existing material."""

import math
from pathlib import Path


def read_solids(path: Path):
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRep import BRep_Tool
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE, TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError('Cut safety STEP read failed')
    reader.SetSystemLengthUnit(1.0)
    if not reader.TransferRoots():
        raise ValueError('Cut safety STEP transferred no geometry')
    shape = reader.OneShape()
    if shape.IsNull() or not BRepCheck_Analyzer(shape).IsValid():
        raise ValueError('Cut safety requires valid boundary representations')
    if TopExp_Explorer(shape, TopAbs_FACE, TopAbs_SOLID).More():
        raise ValueError('Cut safety requires every face to belong to a solid')
    result = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        solid = TopoDS.Solid_s(explorer.Current())
        shells = TopExp_Explorer(solid, TopAbs_SHELL)
        while shells.More():
            if not BRep_Tool.IsClosed_s(TopoDS.Shell_s(shells.Current())):
                raise ValueError('Cut safety requires closed shells')
            shells.Next()
        if volume(solid) <= 1e-9:
            raise ValueError('Cut safety requires positive solid volumes')
        result.append(solid)
        explorer.Next()
    if not result:
        raise ValueError('Cut safety requires solid geometry')
    return shape, result


def volume(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    value = props.Mass()
    if not math.isfinite(value):
        raise ValueError('Cut safety returned a non-finite intersection volume')
    if value < -1e-9:
        raise ValueError('Cut safety encountered reversed solid orientation')
    return abs(value)


def common(a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepCheck import BRepCheck_Analyzer
    operation = BRepAlgoAPI_Common(a, b)
    operation.Build()
    if not operation.IsDone():
        raise ValueError('Cut safety intersection is inconclusive')
    result = operation.Shape()
    if result.IsNull() or not BRepCheck_Analyzer(result).IsValid():
        raise ValueError('Cut safety intersection returned invalid geometry')
    return result


def inspect_overruns(material_path, cutter_path, boundaries):
    """Require each tool extension to remain outside all existing material."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
    from OCP.TopAbs import TopAbs_IN, TopAbs_OUT, TopAbs_ON
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    material, solids = read_solids(Path(material_path))
    cutter, _ = read_solids(Path(cutter_path))
    report = []
    # This threshold distinguishes numerical zero from removed material. It is
    # deliberately independent of the much looser delivery dimension tolerance.
    zero_volume_mm3 = 1e-9
    for boundary in boundaries:
        point, normal = boundary['origin_mm'], boundary['outward_normal']
        requested_point, requested_normal = list(point), list(normal)
        alignment = None
        tolerance = boundary.get('alignment_tolerance_mm', 0)
        if tolerance:
            if boundary['role'] != 'opening' or not 0 < tolerance <= 0.05:
                raise ValueError('Measured alignment requires an opening and the confirmed length tolerance')
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.BRepExtrema import BRepExtrema_DistShapeShape
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
            from OCP.GeomAbs import GeomAbs_Plane
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE
            from OCP.TopoDS import TopoDS
            vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
            candidates = []
            faces = TopExp_Explorer(material, TopAbs_FACE)
            while faces.More():
                face_shape = TopoDS.Face_s(faces.Current())
                surface = BRepAdaptor_Surface(face_shape)
                if surface.GetType() == GeomAbs_Plane:
                    distance = BRepExtrema_DistShapeShape(vertex, face_shape)
                    distance.Perform()
                    if not distance.IsDone():
                        raise ValueError('Measured opening alignment is inconclusive')
                    if distance.Value() <= tolerance:
                        plane = surface.Plane()
                        direction = plane.Axis().Direction()
                        n = [direction.X(), direction.Y(), direction.Z()]
                        dot = sum(a*b for a, b in zip(n, normal))
                        if abs(dot) >= math.cos(math.radians(0.1)):
                            if dot < 0:
                                n = [-a for a in n]
                            p = distance.PointOnShape2(1)
                            candidates.append((distance.Value(), [p.X(), p.Y(), p.Z()], n))
                faces.Next()
            if not candidates:
                raise ValueError(f"{boundary['label']}: no measured planar opening within its alignment tolerance")
            candidates.sort(key=lambda item: item[0])
            offset, point, normal = candidates[0]
            # Ambiguous nearby surfaces need an explicit geometric distinction.
            if any(abs(sum((a-b)*n for a, b, n in zip(p, point, normal))) > 1e-7
                   for _, p, _ in candidates[1:]):
                raise ValueError(f"{boundary['label']}: measured opening alignment is ambiguous")
            alignment = {'distance_mm': offset, 'tolerance_mm': tolerance,
                         'requested_origin_mm': requested_point, 'requested_normal': requested_normal,
                         'measured_origin_mm': point, 'measured_normal': normal}
        if boundary['role'] == 'opening':
            def states(sign):
                probe = gp_Pnt(*(value + sign * 1e-4 * axis for value, axis in zip(point, normal)))
                return [BRepClass3d_SolidClassifier(solid, probe, 1e-7).State() for solid in solids]
            # STEP-exported trimmed faces can classify an exact boundary point
            # as IN. Confirm its distance to actual faces independently.
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
            from OCP.BRepExtrema import BRepExtrema_DistShapeShape
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE
            vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
            on_boundary = TopAbs_ON in states(0)
            faces = TopExp_Explorer(material, TopAbs_FACE)
            while faces.More() and not on_boundary:
                distance = BRepExtrema_DistShapeShape(vertex, faces.Current())
                distance.Perform()
                if not distance.IsDone():
                    raise ValueError('Cut opening boundary distance is inconclusive')
                on_boundary = distance.Value() <= 1e-7
                faces.Next()
            if (not on_boundary or TopAbs_IN not in states(-1)
                    or any(state != TopAbs_OUT for state in states(1))):
                raise ValueError(f"{boundary['label']}: opening does not resolve to an outward material boundary")
        plane = gp_Pln(gp_Pnt(*point), gp_Dir(*normal))
        face = BRepBuilderAPI_MakeFace(plane).Face()
        exterior = BRepPrimAPI_MakeHalfSpace(face, gp_Pnt(*(a + n for a, n in zip(point, normal)))).Solid()
        extension = common(cutter, exterior)
        tool_volume = volume(extension)
        material_volume = volume(common(extension, material)) if tool_volume > zero_volume_mm3 else 0.0
        row = {**boundary, 'tool_overrun_mm3': tool_volume, 'material_intersection_mm3': material_volume}
        if alignment:
            row['alignment'] = alignment
        report.append(row)
        if boundary['role'] == 'stop' and tool_volume > zero_volume_mm3:
            raise ValueError(f"{boundary['label']}: cutter crosses the blind stop limit")
        if material_volume > zero_volume_mm3:
            raise ValueError(f"{boundary['label']}: cutter extension intersects protected material ({material_volume:g} mm3)")
    return {'method': 'occt-cut-overrun-intersection', 'units': 'mm',
            'zero_volume_mm3': zero_volume_mm3, 'boundaries': report}
