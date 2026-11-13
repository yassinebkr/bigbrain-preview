"""Axis-line material intervals measured against exported STEP boundary surfaces."""

import math


def inspect_step_sections(path, sections):
    """Read one closed solid once and retain per-probe boundary diagnostics."""
    from .cad_step import load_step_shape
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    shape = load_step_shape(path)
    solids = TopExp_Explorer(shape, TopAbs_SOLID)
    if not solids.More():
        raise ValueError('STEP section verification requires one closed solid')
    solid = solids.Current()
    solids.Next()
    if solids.More():
        raise ValueError('STEP section verification requires one closed solid')
    shells = TopExp_Explorer(solid, TopAbs_SHELL)
    while shells.More():
        if not BRep_Tool.IsClosed_s(shells.Current()):
            raise ValueError('STEP section verification requires closed shells')
        shells.Next()
    result = {}
    for section in sections:
        try:
            result[section.id] = {'intervals_mm': _material_intervals(solid, section)}
        except ValueError as error:
            result[section.id] = {'error': str(error)}
    return result


def _material_intervals(solid, section):
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.Bnd import Bnd_Box
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP.IntCurveSurface import IntCurveSurface_Tangent
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_OUT
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

    tolerance = 1e-7
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(solid, box, False, False)
    bounds = box.Get()
    axis = section.axis
    direction = [0, 0, 0]
    direction[axis] = 1
    origin = list(section.point_mm)
    # Extend beyond both extrema so the first and last segments must be outside.
    margin = max(1.0, bounds[axis + 3] - bounds[axis])
    low = bounds[axis] - margin - origin[axis]
    high = bounds[axis + 3] + margin - origin[axis]
    intersection = IntCurvesFace_ShapeIntersector()
    intersection.Load(solid, tolerance)
    intersection.Perform(gp_Lin(gp_Pnt(*origin), gp_Dir(*direction)), low, high)
    if not intersection.IsDone():
        raise ValueError('STEP section intersection did not converge')
    coordinates = []
    for index in range(1, intersection.NbPnt() + 1):
        coordinate = intersection.WParameter(index)
        if not math.isfinite(coordinate):
            raise ValueError('STEP section returned a non-finite intersection')
        if intersection.Transition(index) == IntCurveSurface_Tangent:
            raise ValueError('Section touches a tangent surface boundary')
        coordinates.append(coordinate)
    crossings = []
    # A seam can report one crossing through both adjacent trimmed faces.
    for coordinate in sorted(coordinates):
        if not crossings or abs(coordinate - crossings[-1]) > tolerance:
            crossings.append(coordinate)
    classifier = BRepClass3d_SolidClassifier(solid)
    intervals = []
    stops = [low, *crossings, high]
    for start, end in zip(stops, stops[1:]):
        point = list(origin)
        point[axis] += (start + end) / 2
        classifier.Perform(gp_Pnt(*point), tolerance)
        state = classifier.State()
        if state == TopAbs_ON:
            raise ValueError('Section lies on a surface boundary')
        if state not in (TopAbs_IN, TopAbs_OUT):
            raise ValueError('STEP section material classification is inconclusive')
        if state == TopAbs_IN:
            if start == low or end == high:
                raise ValueError('STEP section has unbounded material')
            intervals.append((start + origin[axis], end + origin[axis]))
    return tuple(intervals)
