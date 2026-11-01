"""Typed CAD recipes and measured acceptance criteria for contract proposals."""

import json
import math
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .cad_contracts import Contract, CriterionObservation, Finite, GeometryObservation, Identity
from .cad_drawings import DrawingSpecification
from .cad_sections import CadSection


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
    dimension_bindings: dict[Identity, Annotated[int, Field(strict=True, ge=0, le=2)]] = Field(default_factory=dict, max_length=3)

    @model_validator(mode='after')
    def measurable_shape(self):
        if self.dimension_bindings and self.metric != 'dimensions_mm':
            raise ValueError('Global drawing bindings require envelope dimensions')
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
    drawing: DrawingSpecification | None = None
    sections: tuple[CadSection, ...] = Field(default=(), max_length=16)
    max_repairs: int = Field(default=0, strict=True, ge=0, le=2)

    @model_validator(mode='after')
    def distinct_criteria(self):
        if self.drawing is not None:
            self.drawing.require_resolved()
            dimensions = {item.id: item for item in self.drawing.dimensions}
            covered = set()

            def bind(identity, value):
                dimension = dimensions.get(identity)
                if dimension is None or dimension.value is None or dimension.unit == 'degree':
                    raise ValueError('Drawing measurement requires a resolved linear dimension')
                expected = dimension.value * (25.4 if dimension.unit == 'inch' else 1)
                if not math.isclose(value, expected, abs_tol=1e-8, rel_tol=1e-10):
                    raise ValueError(f'Measurement target differs from drawing dimension {identity}')
                covered.add(identity)

            for criterion in self.criteria:
                for identity, index in criterion.dimension_bindings.items():
                    bind(identity, criterion.expected[index])
            for section in self.sections:
                for binding in section.bindings:
                    value = section.quantity(binding)
                    if binding.subtract is not None:
                        target = next((item for item in self.sections if item.id == binding.subtract.section_id), None)
                        if target is None:
                            raise ValueError('Dimension difference references an unknown measured section')
                        if (target.id == section.id and binding.quantity == binding.subtract.quantity
                                and binding.interval == binding.subtract.interval):
                            raise ValueError('Dimension difference requires distinct measurements')
                        value -= target.quantity(binding.subtract)
                    bind(binding.dimension_id, value)
            missing = [item.id for item in self.drawing.dimensions if item.critical and item.id not in covered]
            if missing:
                raise ValueError('Every critical drawing dimension requires a geometric measurement binding: ' + ', '.join(missing))
        identities = [item.id for item in (*self.criteria, *self.sections)]
        if len(set(identities)) != len(identities):
            raise ValueError('CAD criterion identifiers must be unique')
        if 'dimensions_mm' not in {item.metric for item in self.criteria}:
            raise ValueError('CAD plan requires explicit measured dimensions')
        if len(self.model_dump_json().encode()) > 64_000:
            raise ValueError('CAD recipe exceeds its byte budget')
        return self

    def contracts(self):
        return ([f'Pièce CAO : {self.title}. Solide fermé, document SolidCraft éditable, exports STEP/STL et aperçu versionné.']
                + [f'Vérification avant livraison ; jusqu’à {self.max_repairs} réparation(s) de géométrie dans les critères confirmés, budget total 120 secondes.']
                + [item.describe() for item in self.criteria]
                + [f'{item.label} : section XYZ axe {item.axis}, point {item.point_mm}, '
                   f'matière attendue {item.intervals_mm} mm (tolérance {item.absolute_tolerance_mm:g} mm)'
                   for item in self.sections]
                + ([f'Cote du dessin {item.id} — {item.label} : {item.value:g} {item.unit} '
                    f'({item.origin}, annotation : {item.annotation})'
                    for item in self.drawing.dimensions if item.value is not None] if self.drawing else [])
                + [f'Limite à prendre en compte : {item}' for item in self.limitations])


class CadRepair(Contract):
    commands: tuple[CadCommand, ...] = Field(min_length=1, max_length=32)


async def draft_cad_repair(provider, plan, checks, *, model=None, command_diagnostic=None):
    """Propose a fresh candidate recipe against the unchanged measured contract."""
    if provider is None:
        raise ValueError('CAD repair requires a configured model')
    response = await provider.chat_complete(messages=[{'role': 'system', 'content':
        'Repair the reproduced CAD geometry defect using SolidCraft 0.28.0 geometry commands. '
        'Return a complete replacement recipe applied to the original document, including '
        'all required original features. Preserve drawing requirements and measured targets. '
        'The engine requires numeric radius/diameter for sketch.circle.center; use numeric '
        'values or use a supported driving dimension afterward. Primitive solid operations '
        'and parameters.change accept expressions according to their own command contracts. '
        'Return JSON matching: ' + json.dumps(CadRepair.model_json_schema())},
        {'role': 'user', 'content': json.dumps({'confirmed_plan': plan.model_dump(mode='json'),
            'observations': [item.model_dump(mode='json') for item in checks],
            'command_diagnostic': command_diagnostic}, ensure_ascii=False)}],
        model=model or 'default', stream=False, max_tokens=4000, temperature=0.1)
    response = response.strip()
    if response.startswith('```') and response.endswith('```'):
        response = '\n'.join(response.splitlines()[1:-1])
    repair = CadRepair.model_validate_json(response)
    return CadPlan.model_validate({**plan.model_dump(), 'commands': [item.model_dump() for item in repair.commands]})


async def draft_cad_plan(provider, objective, *, context=None, model=None, drawing=None, command_reference=None):
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
        'The command_reference contains installed engine documentation for sketches, '
        'extrusions, rounded profiles, chamfers and fillets. Use their exact parameters. '
        'Keep numeric criteria faithful to the request; measure volume where it verifies requested material removal. '
        'For drawings, bind every critical dimension to dimensions_mm.dimension_bindings '
        '(dimension ID to XYZ index) or sections.bindings (dimension ID, interval index, '
        'start/end/length/gap/gap_center quantity). Section intervals describe material along a full '
        'world-axis line through point_mm. A hole gives a gap; a recess changes intervals '
        'at its interior. Use several sections to check position, size and depth. '
        'For a dimension obtained by subtracting measured quantities (such as step rise '
        '= total height minus base thickness), add binding.subtract with section_id, '
        'quantity and interval of the other section. Both sections are checked independently. '
        'Expected values are millimetres, converted from inch when necessary. '
        'Describe criterion labels/title in the user language. List verification limitations explicitly. '
        'Use the supplied resolved drawing specification as the dimensional authority. '
        'Preserve every feature and dimension; declare unsupported geometry before execution. '
        'Uncertain dimensions, wall-thickness guarantees and arbitrary topology validation require clarification. '
        'For an existing document, edit its parameters or geometry and preserve unrelated geometry. '
        'Every operation runs on a private document candidate after the contract is confirmed. '
        'Tools, external file access and shell execution belong to the runtime. Output JSON only.'
    )
    raw = await provider.chat_complete(messages=[{'role': 'system', 'content': prompt},
        {'role': 'user', 'content': json.dumps({'objective': objective, 'existing_document': context,
            'drawing': drawing.model_dump(mode='json') if drawing else None,
            'command_reference': command_reference}, ensure_ascii=False)}],
        model=model or 'default', stream=False, max_tokens=4000, temperature=0.1)
    raw = raw.strip()
    if raw.startswith('```') and raw.endswith('```'):
        raw = '\n'.join(raw.splitlines()[1:-1])
    plan = CadPlan.model_validate_json(raw)
    # Bind the source interpretation supplied by the runtime. Model output
    # cannot replace its dimensions while drafting the recipe.
    if drawing is not None:
        return CadPlan.model_validate({**plan.model_dump(), 'drawing': drawing.model_dump(), 'max_repairs': 2})
    if plan.drawing is not None:
        raise ValueError('CAD planner invented a drawing without source interpretation')
    return CadPlan.model_validate({**plan.model_dump(), 'max_repairs': 2})
