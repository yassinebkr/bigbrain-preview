"""Revision-bound analytic cylinder radius and axis observations."""

import math
from typing import Annotated

from pydantic import Field, model_validator

from .cad_contracts import Contract, CriterionObservation, Finite, Identity, Vector


class CadCylinder(Contract):
    id: Identity
    label: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=160)
    axis: int = Field(strict=True, ge=0, le=2, description='World axis of the cylinder: X=0, Y=1, Z=2')
    center_mm: Vector
    radius_mm: Finite = Field(gt=0)
    absolute_tolerance_mm: Finite = Field(default=0.001, gt=0, le=0.1)
    radius_binding: Identity | None = Field(default=None, description=
        'Drawing dimension ID of kind radius or diameter. Radius binds radius_mm; '
        'diameter binds exactly 2 * radius_mm. Unit conversion is applied by the runtime.')
    center_bindings: dict[Identity, Annotated[int, Field(strict=True, ge=0, le=2)]] = Field(default_factory=dict, max_length=2)

    @model_validator(mode='after')
    def perpendicular_center(self):
        if self.axis in self.center_bindings.values():
            raise ValueError('Cylinder origin along its own axis is not a measurable center coordinate')
        return self

    def target(self):
        return (self.radius_mm, *(self.center_mm[i] for i in range(3) if i != self.axis))

    def observe(self, topology, *, source_sha256, evidence_ref):
        """Match actual analytic faces; retain all face data in separate evidence."""
        if topology.get('body') != self.body:
            raise ValueError('Analytic topology belongs to another body')
        candidates, approximations, uncertain = [], [], False
        for face in topology.get('faces', []):
            cylinder = face.get('cylinder')
            if not isinstance(cylinder, dict):
                continue
            try:
                axis = tuple(float(value) for value in cylinder['axis'])
                origin = tuple(float(value) for value in cylinder['origin'])
                radius = float(cylinder['radius'])
                if len(axis) != 3 or len(origin) != 3 or radius <= 0 or not all(
                        math.isfinite(value) for value in (*axis, *origin, radius)):
                    raise ValueError('Invalid cylinder observation')
                norm = math.sqrt(sum(value * value for value in axis))
                if not math.isclose(norm, 1, abs_tol=1e-6):
                    raise ValueError('Invalid cylinder axis')
                if any(abs(axis[i]) > 1e-6 for i in range(3) if i != self.axis):
                    continue
                values = (radius, *(origin[i] for i in range(3) if i != self.axis))
                if face.get('exact') is True:
                    candidates.append(values)
                else:
                    approximations.append(values)
                    uncertain = True
            except (KeyError, TypeError, ValueError):
                uncertain = True
        expected = self.target()
        nearest = min(candidates, key=lambda values: sum((a-b)**2 for a,b in zip(values, expected))) if candidates else None
        passed = nearest is not None and all(abs(a-b) <= self.absolute_tolerance_mm for a,b in zip(nearest, expected))
        approximate_match = any(all(abs(a-b) <= self.absolute_tolerance_mm for a,b in zip(values, expected))
                                for values in approximations)
        status = 'passed' if passed else 'inconclusive' if approximate_match or (uncertain and nearest is None) else 'failed'
        diagnostic = (f'{self.label}: matching approximate surface requires independent measurement'
                      if approximate_match and not passed else
                      f'{self.label}: analytic radius and perpendicular axis coordinates; status {status}')
        if approximate_match and not passed:
            nearest = None  # An unrelated exact coaxial face is not the measured target.
        return CriterionObservation(criterion_id=self.id, source_sha256=source_sha256,
            evidence_ref=evidence_ref, status=status, label=self.label,
            metric='cylindrical_surface_mm', observed=nearest, expected=expected,
            absolute_tolerance=self.absolute_tolerance_mm, relative_tolerance=0,
            diagnostic=diagnostic)


class CadVertex(Contract):
    """A native edge endpoint selected by its full world coordinate."""

    id: Identity
    label: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=160)
    point_mm: Vector
    absolute_tolerance_mm: Finite = Field(default=0.001, gt=0, le=0.1)

    def observe(self, topology, *, source_sha256, evidence_ref):
        if topology.get('body') != self.body:
            raise ValueError('Vertex topology belongs to another body')
        candidates, uncertain = [], False
        for edge in topology.get('edges', []):
            for key in ('start', 'end'):
                try:
                    point = tuple(float(value) for value in edge[key])
                    if len(point) != 3 or not all(math.isfinite(value) for value in point):
                        raise ValueError('Invalid native vertex')
                    candidates.append(point)
                except (KeyError, TypeError, ValueError):
                    uncertain = True
        nearest = min(candidates, key=lambda point: sum((a-b)**2 for a,b in zip(point, self.point_mm))) if candidates else None
        passed = nearest is not None and all(abs(a-b) <= self.absolute_tolerance_mm for a,b in zip(nearest, self.point_mm))
        status = 'passed' if passed else 'inconclusive' if uncertain and nearest is None else 'failed'
        return CriterionObservation(criterion_id=self.id, source_sha256=source_sha256,
            evidence_ref=evidence_ref, status=status, label=self.label, metric='point_mm',
            observed=nearest, expected=self.point_mm, absolute_tolerance=self.absolute_tolerance_mm,
            relative_tolerance=0, diagnostic=f'{self.label}: native endpoint; status {status}')
