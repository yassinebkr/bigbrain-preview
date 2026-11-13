"""Revision-bound material interval checks and legacy STL section probes."""

import math
import struct
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .cad_contracts import Contract, CriterionObservation, Finite, Identity, Vector


class SectionOperand(Contract):
    section_id: Identity
    quantity: Literal['start', 'end', 'length', 'gap', 'gap_center']
    interval: int = Field(ge=0, le=15, strict=True)


class DimensionBinding(Contract):
    dimension_id: Identity
    quantity: Literal['start', 'end', 'length', 'gap', 'gap_center']
    interval: int = Field(ge=0, le=15, strict=True)
    subtract: SectionOperand | None = None
    angle_denominator: SectionOperand | None = Field(default=None, description=
        'For an angular drawing dimension, the independently checked run length. '
        'The angle in degrees is atan2(the measured rise, this run).')


class CadSection(Contract):
    """Material intervals along an axis through a point in world millimetres."""

    id: Identity
    label: str = Field(min_length=1, max_length=500)
    axis: int = Field(strict=True, ge=0, le=2)
    point_mm: Vector
    intervals_mm: tuple[tuple[Finite, Finite], ...] | None = Field(default=None, max_length=16,
        description='Expected material intervals for a fixed topology check. Omit for a raw probe consumed by requirement measurements.')
    absolute_tolerance_mm: Finite = Field(default=0.05, gt=0, le=0.1)
    bindings: tuple[DimensionBinding, ...] = Field(default=(), max_length=32)
    empty_span_mm: tuple[Finite, Finite] | None = Field(default=None, description=
        'World-axis interval for a local empty-through check, such as one flange thickness. '
        'Requires intervals_mm=[]; full-line material remains in the diagnostic.')

    @model_validator(mode='after')
    def ordered_intervals(self):
        if self.empty_span_mm is not None:
            if self.intervals_mm != () or self.bindings or self.empty_span_mm[0] >= self.empty_span_mm[1]:
                raise ValueError('A local empty span requires an ordered interval, empty targets and no dimension bindings')
        previous = -math.inf
        for start, end in self.intervals_mm or ():
            if start >= end or start <= previous:
                raise ValueError('Section intervals must be positive and disjoint')
            previous = end
        for binding in self.bindings:
            self.quantity(binding)
        return self

    def quantity(self, binding):
        if self.intervals_mm is None:
            raise ValueError('Legacy bindings require explicit section targets; use requirement measurements for raw probes')
        index = binding.interval
        if index >= len(self.intervals_mm):
            raise ValueError('Dimension binding references an absent section interval')
        start, end = self.intervals_mm[index]
        if binding.quantity in {'gap', 'gap_center'}:
            if index + 1 >= len(self.intervals_mm):
                raise ValueError('Gap requires a following material interval')
            following = self.intervals_mm[index + 1][0]
            return following - end if binding.quantity == 'gap' else (following + end) / 2
        return {'start': start, 'end': end, 'length': end - start}[binding.quantity]


def read_triangles(path: Path):
    """Validate the bounded binary STL before measuring its surface."""
    with path.open('rb') as stream:
        header = stream.read(84)
        if len(header) != 84:
            raise ValueError('STL header is incomplete')
        count = struct.unpack_from('<I', header, 80)[0]
        if not 1 <= count <= 250_000 or path.stat().st_size != 84 + 50 * count:
            raise ValueError('STL triangle count or byte size is invalid')
        triangles = []
        for _ in range(count):
            packet = stream.read(50)
            if len(packet) != 50:
                raise ValueError('STL triangle is incomplete')
            numbers = struct.unpack('<12fH', packet)
            vertices = numbers[3:12]
            if not all(math.isfinite(value) for value in vertices):
                raise ValueError('STL contains non-finite coordinates')
            triangles.append((vertices[:3], vertices[3:6], vertices[6:9]))
        return triangles


def material_intervals(triangles, section: CadSection):
    """Intersect a full axis line; inconsistent crossings remain inconclusive."""
    axis = section.axis
    u, v = [index for index in range(3) if index != axis]
    pu, pv = section.point_mm[u], section.point_mm[v]
    hits = []
    for a, b, c in triangles:
        bu, bv = b[u] - a[u], b[v] - a[v]
        cu, cv = c[u] - a[u], c[v] - a[v]
        denominator = bu * cv - bv * cu
        if abs(denominator) < 1e-12:
            # A line lying on a surface has no stable inside/outside result.
            # Detect it in the degenerate perpendicular projection.
            for first, second in ((a, b), (b, c), (c, a)):
                du, dv = second[u] - first[u], second[v] - first[v]
                length2 = du * du + dv * dv
                fraction = ((pu - first[u]) * du + (pv - first[v]) * dv) / length2 if length2 else 0
                if (0 <= fraction <= 1 and
                        math.hypot(pu - first[u] - fraction * du,
                                   pv - first[v] - fraction * dv) < 1e-8):
                    raise ValueError('Section lies on a surface boundary')
            continue
        du, dv = pu - a[u], pv - a[v]
        beta = (du * cv - dv * cu) / denominator
        gamma = (bu * dv - bv * du) / denominator
        if beta >= -1e-9 and gamma >= -1e-9 and beta + gamma <= 1 + 1e-9:
            coordinate = a[axis] + beta * (b[axis] - a[axis]) + gamma * (c[axis] - a[axis])
            hits.append((coordinate, 1 if denominator > 0 else -1))
    # Shared triangle edges can report the same crossing multiple times.
    # Opposing signs at a single coordinate indicate a tangent or ambiguous line.
    crossings = []
    for coordinate, sign in sorted(hits):
        if crossings and abs(coordinate - crossings[-1][0]) < 1e-5:
            if sign != crossings[-1][1]:
                raise ValueError('Section touches an ambiguous surface boundary')
        else:
            crossings.append((coordinate, sign))
    if len(crossings) % 2 or any(a[1] == b[1] for a, b in zip(crossings, crossings[1:])):
        raise ValueError('Section surface crossings are inconsistent')
    return tuple((crossings[index][0], crossings[index + 1][0])
                 for index in range(0, len(crossings), 2))


def observe_section(section, triangles, *, source_sha256, evidence_ref):
    try:
        actual = material_intervals(triangles, section)
    except ValueError as error:
        return observe_intervals(section, None, source_sha256=source_sha256,
                                 evidence_ref=evidence_ref, error=str(error))
    return observe_intervals(section, actual, source_sha256=source_sha256, evidence_ref=evidence_ref)


def observe_intervals(section, actual, *, source_sha256, evidence_ref, error=None):
    """Apply identical acceptance rules to intervals from each measurement provider."""
    try:
        if error is not None:
            raise ValueError(error)
        actual = tuple(tuple(pair) for pair in actual)
        if (any(len(pair) != 2 or not all(math.isfinite(value) for value in pair)
                or pair[0] >= pair[1] for pair in actual)
                or any(first[1] > second[0] for first, second in zip(actual, actual[1:]))):
            raise ValueError('CAD section provider returned invalid material intervals')
        full_line = actual
        if section.empty_span_mm is not None:
            low, high = section.empty_span_mm
            actual = tuple((max(start, low), min(end, high)) for start, end in actual
                           if max(start, low) < min(end, high))
        passed = (section.intervals_mm is None or (len(actual) == len(section.intervals_mm)
                  and all(abs(a - e) <= section.absolute_tolerance_mm
                          for observed, expected in zip(actual, section.intervals_mm)
                          for a, e in zip(observed, expected))))
        status = 'passed' if passed else 'failed'
        diagnostic = f'Material intervals (mm): observed {actual}; expected {section.intervals_mm}'
        if section.empty_span_mm is not None:
            diagnostic += f'; local empty span {section.empty_span_mm}; full-line intervals {full_line}'
    except ValueError as error:
        actual, status, diagnostic = None, 'inconclusive', str(error)
    observation = CriterionObservation(criterion_id=section.id, label=section.label,
        source_sha256=source_sha256, status=status, evidence_ref=evidence_ref,
        diagnostic=diagnostic, absolute_tolerance=section.absolute_tolerance_mm)
    observation = CriterionObservation.model_validate({**observation.model_dump(),
        'observed_intervals_mm': actual, 'expected_intervals_mm': section.intervals_mm})
    return observation, actual
