"""Revision-bound line sections measured from the exported binary STL surface."""

import math
import struct
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .cad_contracts import Contract, CriterionObservation, Finite, Identity, Vector


class DimensionBinding(Contract):
    dimension_id: Identity
    quantity: Literal['start', 'end', 'length', 'gap']
    interval: int = Field(ge=0, le=15, strict=True)


class CadSection(Contract):
    """Material intervals along an axis through a point in world millimetres."""

    id: Identity
    label: str = Field(min_length=1, max_length=500)
    axis: Literal[0, 1, 2]
    point_mm: Vector
    intervals_mm: tuple[tuple[Finite, Finite], ...] = Field(max_length=16)
    absolute_tolerance_mm: Finite = Field(default=0.05, gt=0, le=0.1)
    bindings: tuple[DimensionBinding, ...] = Field(default=(), max_length=32)

    @model_validator(mode='after')
    def ordered_intervals(self):
        previous = -math.inf
        for start, end in self.intervals_mm:
            if start >= end or start <= previous:
                raise ValueError('Section intervals must be positive and disjoint')
            previous = end
        for binding in self.bindings:
            self.quantity(binding)
        return self

    def quantity(self, binding):
        index = binding.interval
        if index >= len(self.intervals_mm):
            raise ValueError('Dimension binding references an absent section interval')
        start, end = self.intervals_mm[index]
        if binding.quantity == 'gap':
            if index + 1 >= len(self.intervals_mm):
                raise ValueError('Gap requires a following material interval')
            return self.intervals_mm[index + 1][0] - end
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
        passed = (len(actual) == len(section.intervals_mm)
                  and all(abs(a - e) <= section.absolute_tolerance_mm
                          for observed, expected in zip(actual, section.intervals_mm)
                          for a, e in zip(observed, expected)))
        status = 'passed' if passed else 'failed'
        diagnostic = f'Material intervals (mm): observed {actual}; expected {section.intervals_mm}'
    except ValueError as error:
        actual, status, diagnostic = None, 'inconclusive', str(error)
    observation = CriterionObservation(criterion_id=section.id, label=section.label,
        source_sha256=source_sha256, status=status, evidence_ref=evidence_ref,
        diagnostic=diagnostic, absolute_tolerance=section.absolute_tolerance_mm)
    observation = CriterionObservation.model_validate({**observation.model_dump(),
        'observed_intervals_mm': actual, 'expected_intervals_mm': section.intervals_mm})
    return observation, actual
