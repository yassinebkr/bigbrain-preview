"""Analytic sections qualify curved surfaces, through-lines and boundary ambiguity."""

import math

import pytest

from bigbrain.cad_sections import CadSection, observe_intervals
from bigbrain.cad_step_sections import inspect_step_sections


def export_step(path, shape):
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    writer = STEPControl_Writer()
    assert writer.Transfer(shape, STEPControl_AsIs) == IFSelect_RetDone
    assert writer.Write(str(path)) == IFSelect_RetDone
    return path


def test_curved_pipe_midsection_preserves_exact_radii(tmp_path):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeTorus
    shape = BRepAlgoAPI_Cut(BRepPrimAPI_MakeTorus(260, 145).Shape(),
                           BRepPrimAPI_MakeTorus(260, 105).Shape()).Shape()
    path = export_step(tmp_path / 'curved pipe.step', shape)
    section = CadSection(id='middle', label='Middle wall', axis=2,
        point_mm=(260 / math.sqrt(2), 260 / math.sqrt(2), 0),
        intervals_mm=((-145, -105), (105, 145)), absolute_tolerance_mm=0.05)
    result = inspect_step_sections(path, [section])['middle']
    assert 'error' not in result
    for actual, expected in zip(result['intervals_mm'], section.intervals_mm):
        assert actual == pytest.approx(expected, abs=1e-6)
    observed, _ = observe_intervals(section, result['intervals_mm'],
                                   source_sha256='a' * 64, evidence_ref='sections.json')
    assert observed.status == 'passed'


def test_sections_use_world_coordinates_and_keep_remote_material(tmp_path):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    path = export_step(tmp_path / 'box.step', BRepPrimAPI_MakeBox(10, 20, 30).Shape())
    inside = CadSection(id='inside', label='Inside', axis=2, point_mm=(5, 10, 12))
    outside = CadSection(id='outside', label='Outside', axis=2, point_mm=(50, 10, 12), intervals_mm=())
    local = CadSection(id='local', label='Local empty span', axis=2, point_mm=(5, 10, 12),
                       intervals_mm=(), empty_span_mm=(35, 40))
    result = inspect_step_sections(path, [inside, outside, local])
    assert result['inside']['intervals_mm'][0] == pytest.approx((0, 30), abs=1e-7)
    assert result['outside']['intervals_mm'] == ()
    observed, actual = observe_intervals(local, result['local']['intervals_mm'],
                                        source_sha256='a' * 64, evidence_ref='sections.json')
    assert observed.status == 'passed' and actual == ()
    assert 'full-line intervals' in observed.diagnostic


def test_line_on_surface_is_inconclusive(tmp_path):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    path = export_step(tmp_path / 'boundary.step', BRepPrimAPI_MakeBox(10, 20, 30).Shape())
    section = CadSection(id='boundary', label='Boundary', axis=2, point_mm=(0, 10, 12))
    result = inspect_step_sections(path, [section])['boundary']
    assert 'boundary' in result['error']
    observed, actual = observe_intervals(section, None, error=result['error'],
                                        source_sha256='a' * 64, evidence_ref='sections.json')
    assert observed.status == 'inconclusive' and actual is None


@pytest.mark.parametrize('intervals', [((float('nan'), 5),), ((5, 0),), ((0, 5), (4, 6))])
def test_invalid_provider_intervals_are_inconclusive(intervals):
    section = CadSection(id='raw', label='Raw probe', axis=2, point_mm=(0, 0, 0))
    observed, actual = observe_intervals(section, intervals, source_sha256='a' * 64, evidence_ref='sections.json')
    assert observed.status == 'inconclusive' and actual is None


def test_tangent_line_is_inconclusive(tmp_path):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
    path = export_step(tmp_path / 'sphere.step', BRepPrimAPI_MakeSphere(5).Shape())
    section = CadSection(id='tangent', label='Tangent', axis=2, point_mm=(5, 0, 0))
    result = inspect_step_sections(path, [section])['tangent']
    assert 'error' in result
