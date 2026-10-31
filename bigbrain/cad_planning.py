"""Typed CAD recipes and measured acceptance criteria for contract proposals."""

import json
import math
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .cad_contracts import Contract, CriterionObservation, Finite, GeometryObservation, Identity


class CadCommand(Contract):
    command: str = Field(pattern=r'^(?:solid\.|sketch\.|pattern\.|construction\.|parameters\.change$)[a-z0-9_.]*$')
    params: dict[str, Any]


class CadCriterion(Contract):
    id: Identity
    label: str = Field(min_length=1, max_length=500)
    metric: Literal['dimensions_mm', 'volume_mm3', 'body_count', 'closed_solid']
    expected: tuple[Finite, ...] = Field(min_length=1, max_length=3)
    absolute_tolerance: Finite = Field(default=0.001, ge=0, le=0.1)
    relative_tolerance: Finite = Field(default=0.00001, ge=0, le=0.0001)

    @model_validator(mode='after')
    def measurable_shape(self):
        if len(self.expected) != (3 if self.metric == 'dimensions_mm' else 1):
            raise ValueError('CAD criterion expected-value shape differs from its metric')
        if any(value <= 0 for value in self.expected):
            raise ValueError('CAD closed-part criteria require positive targets')
        if self.metric == 'closed_solid' and self.expected != (1,):
            raise ValueError('Closed-solid criterion requires a closed result')
        if self.metric == 'body_count' and not self.expected[0].is_integer():
            raise ValueError('Body count must be integral')
        return self

    def describe(self):
        expected = ' × '.join(f'{value:g}' for value in self.expected)
        units = {'dimensions_mm': ' mm', 'volume_mm3': ' mm³', 'body_count': ' corps', 'closed_solid': ''}[self.metric]
        tolerance = (f' (tolérance {self.absolute_tolerance:g}{units} ou {self.relative_tolerance * 100:g} %)'
                     if self.metric in {'dimensions_mm', 'volume_mm3'} else '')
        return f'{self.label} : {"solide fermé" if self.metric == "closed_solid" else expected + units}{tolerance}'

    def observe(self, geometry: GeometryObservation):
        values = {
            'dimensions_mm': tuple(high - low for low, high in zip(geometry.bounds_min_mm, geometry.bounds_max_mm)),
            'volume_mm3': (geometry.volume_mm3,), 'body_count': (geometry.body_count,),
            'closed_solid': (int(geometry.closed_solid),),
        }[self.metric]
        if self.metric in {'body_count', 'closed_solid'}:
            passed = values == self.expected
        else:
            passed = all(math.isclose(actual, expected, rel_tol=self.relative_tolerance,
                                      abs_tol=self.absolute_tolerance)
                         for actual, expected in zip(values, self.expected))
        return CriterionObservation(criterion_id=self.id, source_sha256=geometry.source_sha256,
            status='passed' if passed else 'failed', evidence_ref=geometry.evidence_ref,
            label=self.label, metric=self.metric, observed=values, expected=self.expected,
            absolute_tolerance=self.absolute_tolerance, relative_tolerance=self.relative_tolerance,
            diagnostic=f'{self.label}: observed {values}; expected {self.expected}')


class CadPlan(Contract):
    title: str = Field(min_length=1, max_length=160)
    commands: tuple[CadCommand, ...] = Field(min_length=1, max_length=32)
    criteria: tuple[CadCriterion, ...] = Field(min_length=1, max_length=16)
    limitations: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = Field(default=(), max_length=6)

    @model_validator(mode='after')
    def distinct_criteria(self):
        if len({item.id for item in self.criteria}) != len(self.criteria):
            raise ValueError('CAD criterion identifiers must be unique')
        if 'dimensions_mm' not in {item.metric for item in self.criteria}:
            raise ValueError('CAD plan requires explicit measured dimensions')
        if len(self.model_dump_json().encode()) > 64_000:
            raise ValueError('CAD recipe exceeds its byte budget')
        return self

    def contracts(self):
        return ([f'Pièce CAO : {self.title}. Solide fermé, document SolidCraft éditable, exports STEP/STL et aperçu versionné.']
                + [item.describe() for item in self.criteria]
                + [f'Limite à prendre en compte : {item}' for item in self.limitations])


async def draft_cad_plan(provider, objective, *, context=None, model=None):
    """Generate the bounded recipe before the user confirms its measured scope."""
    if provider is None:
        raise ValueError('CAD planning requires a configured model')
    prompt = (
        'Plan a small mechanical CAD part using SolidCraft 0.28.0 headless, mm units. '
        'Return one JSON object matching this schema: ' + json.dumps(CadPlan.model_json_schema())
        + '\nUse parameter expressions when dimensions may change. Available primitives: '
        'parameters.change {name,expression}; solid.box {length,width,height,corner?,body_name?,operation?,targets?}; '
        'solid.cylinder {radius,height,base?,body_name?,operation?,targets?}. Operation: new, join, cut, intersect. '
        'A cut needs targets with the existing body name. Use dimensions_mm in world XYZ. '
        'Keep numeric criteria faithful to the request; measure volume where it verifies requested material removal. '
        'Describe criterion labels/title in the user language. List verification limitations explicitly. '
        'Photos, uncertain dimensions, wall-thickness guarantees and arbitrary topology validation require clarification. '
        'For an existing document, edit its parameters or geometry and preserve unrelated geometry. '
        'Every operation runs on a private document candidate after the contract is confirmed. '
        'Tools, external file access and shell execution belong to the runtime. Output JSON only.'
    )
    raw = await provider.chat_complete(messages=[{'role': 'system', 'content': prompt},
        {'role': 'user', 'content': json.dumps({'objective': objective, 'existing_document': context}, ensure_ascii=False)}],
        model=model or 'default', stream=False, max_tokens=4000, temperature=0.1)
    raw = raw.strip()
    if raw.startswith('```') and raw.endswith('```'):
        raw = '\n'.join(raw.splitlines()[1:-1])
    return CadPlan.model_validate_json(raw)
