"""Drawing requirements measured from revision-bound native observations."""

import math
from typing import Literal

from pydantic import Field, model_validator

from .cad_contracts import Contract, CriterionObservation, Identity, Finite


class MeasurementOperand(Contract):
    source: Literal['envelope', 'section', 'cylinder', 'vertex']
    reference: Identity | None = None
    quantity: Literal['start', 'end', 'length', 'gap', 'gap_center', 'radius', 'diameter', 'coordinate']
    axis: int | None = Field(default=None, strict=True, ge=0, le=2)
    interval: int = Field(default=0, strict=True, ge=0, le=15)

    @model_validator(mode='after')
    def shape(self):
        if self.source == 'envelope':
            if self.reference is not None or self.axis is None or self.quantity not in {'start', 'end', 'length'}:
                raise ValueError('Envelope operand requires an axis and start/end/length')
        elif self.reference is None:
            raise ValueError('Measurement operand requires a source reference')
        elif self.source == 'section' and (self.axis is not None or self.quantity not in {'start', 'end', 'length', 'gap', 'gap_center'}):
            raise ValueError('Section operand takes its axis from the referenced section')
        elif self.source == 'cylinder' and (self.quantity not in {'radius', 'diameter', 'coordinate'} or
                (self.quantity == 'coordinate') != (self.axis is not None)):
            raise ValueError('Cylinder operand requires radius, diameter or a perpendicular coordinate')
        elif self.source == 'vertex' and (self.quantity != 'coordinate' or self.axis is None):
            raise ValueError('Vertex operand requires a world coordinate axis')
        return self


class RequirementMeasurement(Contract):
    """A measurement method whose target comes from the drawing requirement."""

    id: Identity
    dimension_id: Identity
    operation: Literal['value', 'difference', 'angle'] = 'value'
    first: MeasurementOperand
    second: MeasurementOperand | None = None
    absolute_tolerance: Finite = Field(default=0.001, gt=0, le=0.1)
    rise_origin: MeasurementOperand | None = None
    run_origin: MeasurementOperand | None = None

    @model_validator(mode='after')
    def arity(self):
        if (self.operation == 'value') != (self.second is None):
            raise ValueError('Difference and angle require two operands; value requires one')
        if self.operation != 'angle' and (self.rise_origin or self.run_origin):
            raise ValueError('Rise/run origins belong to angular measurements')
        return self

    def validate_sources(self, plan):
        dimensions = {item.id: item for item in plan.drawing.dimensions} if plan.drawing else {}
        dimension = dimensions.get(self.dimension_id)
        if dimension is None:
            raise ValueError(f'Unknown drawing requirement {self.dimension_id}')
        if (dimension.unit == 'degree') != (self.operation == 'angle'):
            raise ValueError('Angular requirements require an angle measurement')
        descriptors = [operand_descriptor(item, plan) for item in (self.first, self.second) if item]
        if self.operation == 'difference':
            if self.first == self.second:
                raise ValueError('Difference requires distinct observations')
            if descriptors[0] != descriptors[1]:
                raise ValueError('Difference requires lengths or coordinates on the same world axis')
        if self.operation == 'angle':
            for index, origin in enumerate((self.rise_origin, self.run_origin)):
                if origin is not None:
                    if descriptors[index] != operand_descriptor(origin, plan) or descriptors[index][0] != 'coordinate':
                        raise ValueError('Angular rise/run origins require matching coordinate axes')
                    descriptors[index] = ('length', descriptors[index][1])
            if any(kind != 'length' or axis is None for kind, axis in descriptors) or descriptors[0][1] == descriptors[1][1]:
                raise ValueError('Angle requires lengths measured on perpendicular axes')

    def observe(self, plan, geometry, sections, cylinders, *, evidence_ref):
        dimension = next(item for item in plan.drawing.dimensions if item.id == self.dimension_id)
        expected = dimension.value * (25.4 if dimension.unit == 'inch' else 1)
        try:
            first = operand_value(self.first, plan, geometry, sections, cylinders)
            if self.operation == 'value':
                value = first
            else:
                second = operand_value(self.second, plan, geometry, sections, cylinders)
                if self.operation == 'angle':
                    if self.rise_origin:
                        first -= operand_value(self.rise_origin, plan, geometry, sections, cylinders)
                    if self.run_origin:
                        second -= operand_value(self.run_origin, plan, geometry, sections, cylinders)
                    if first <= 0 or second <= 0:
                        raise ValueError('Angle requires positive measured rise and run')
                    value = math.degrees(math.atan2(first, second))
                else:
                    value = first - second
            tolerance = self.absolute_tolerance
            status = 'passed' if abs(value - expected) <= tolerance else 'failed'
            observed = (value,)
            diagnostic = f'{dimension.label}: observed {value:g}; expected {expected:g}'
        except (KeyError, ValueError, IndexError, TypeError) as error:
            observed, status, tolerance = None, 'inconclusive', 0
            diagnostic = f'{dimension.label}: {error}'
        return CriterionObservation(criterion_id=self.id, label=dimension.label,
            metric='angle_degree' if dimension.unit == 'degree' else 'length_mm',
            source_sha256=geometry.source_sha256, evidence_ref=evidence_ref,
            observed=observed, expected=(expected,), status=status,
            absolute_tolerance=tolerance, relative_tolerance=0, diagnostic=diagnostic)


def operand_descriptor(operand, plan):
    """Check source identity, quantity and coordinate compatibility before execution."""
    if operand.source == 'envelope':
        return ('length' if operand.quantity == 'length' else 'coordinate', operand.axis)
    if operand.source == 'section':
        section = next((item for item in plan.sections if item.id == operand.reference), None)
        if section is None:
            raise ValueError(f'Unknown measured section {operand.reference}')
        if section.intervals_mm is not None:
            section.quantity(operand)
        return ('length' if operand.quantity in {'length', 'gap'} else 'coordinate', section.axis)
    if operand.source == 'vertex':
        if not any(item.id == operand.reference for item in plan.vertices):
            raise ValueError(f'Unknown native vertex {operand.reference}')
        return ('coordinate', operand.axis)
    cylinder = next((item for item in plan.cylinders if item.id == operand.reference), None)
    if cylinder is None:
        raise ValueError(f'Unknown analytic cylinder {operand.reference}')
    if operand.quantity == 'coordinate' and operand.axis == cylinder.axis:
        raise ValueError('Cylinder axis coordinate is indeterminate')
    return ('coordinate', operand.axis) if operand.quantity == 'coordinate' else ('length', None)


def operand_value(operand, plan, geometry, sections, cylinders):
    if operand.source == 'envelope':
        low, high = geometry.bounds_min_mm[operand.axis], geometry.bounds_max_mm[operand.axis]
        return {'start': low, 'end': high, 'length': high - low}[operand.quantity]
    if operand.source == 'section':
        actual = sections[operand.reference]
        if actual is None:
            raise ValueError('Section observation is inconclusive')
        index = operand.interval
        low, high = actual[index]
        if operand.quantity in {'gap', 'gap_center'}:
            following = actual[index + 1][0]
            return following - high if operand.quantity == 'gap' else (following + high) / 2
        return {'start': low, 'end': high, 'length': high - low}[operand.quantity]
    observation = cylinders[operand.reference]
    if observation.observed is None or observation.status == 'inconclusive':
        raise ValueError('Analytic face observation is inconclusive')
    if operand.quantity in {'radius', 'diameter'}:
        return observation.observed[0] * (2 if operand.quantity == 'diameter' else 1)
    if operand.source == 'vertex':
        return observation.observed[operand.axis]
    cylinder = next(item for item in plan.cylinders if item.id == operand.reference)
    return observation.observed[1 + [axis for axis in range(3) if axis != cylinder.axis].index(operand.axis)]
