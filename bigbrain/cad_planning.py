"""Typed CAD recipes and measured acceptance criteria for contract proposals."""

import json
import math
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, Field, model_validator, field_validator
from .cad_resources import check_commands

from .cad_contracts import Contract, CriterionObservation, Finite, GeometryObservation, Identity, Vector, MAX_PROPOSED_CHECKS
from .cad_drawings import DrawingSpecification
from .cad_sections import CadSection
from .cad_surfaces import CadCylinder, CadVertex
from .cad_measurements import RequirementMeasurement
from .cad_preflight import measurement_diagnostics, command_diagnostics
from .cad_workflow import CadWorkflow, allowed_cad_command
from .cad_cut_contracts import CutIntent, validate_cut_intents


class CadCommand(Contract):
    command: str = Field(pattern=r'^[a-z][a-z0-9_.]*$', max_length=128)
    params: dict[str, Any]

    @field_validator('command')
    @classmethod
    def scoped_command(cls, value):
        if not allowed_cad_command(value):
            raise ValueError('CAD command lies outside geometry and organization operations')
        return value


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


class CadRecipe(Contract):
    """Model-authored construction commands and proposed measurement targets."""
    title: str = Field(min_length=1, max_length=160)
    commands: Annotated[tuple[CadCommand, ...], AfterValidator(check_commands)] = Field(min_length=1, max_length=96)
    criteria: tuple[CadCriterion, ...] = Field(min_length=1, max_length=16)
    limitations: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = Field(default=(), max_length=6)
    sections: tuple[CadSection, ...] = Field(default=(), max_length=32)
    cylinders: tuple[CadCylinder, ...] = Field(default=(), max_length=16,
        description='Analytic cylinder radius and perpendicular axis coordinates; combine with sections for trimmed extents.')
    max_repairs: int = Field(default=0, strict=True, ge=0, le=2)
    measurements: tuple[RequirementMeasurement, ...] = Field(default=(), max_length=32,
        description='Measurement methods referencing geometry. Targets come exclusively from drawing dimensions.')
    vertices: tuple[CadVertex, ...] = Field(default=(), max_length=16,
        description='Native edge endpoints selected by full world point. Use for exact arc or chamfer endpoints on boundaries.')
    workflow: CadWorkflow | None = None
    cut_intents: tuple[CutIntent, ...] = Field(default=(), max_length=16)


class CadPlan(CadRecipe):
    """Runtime-bound recipe with the authoritative drawing interpretation."""

    drawing: DrawingSpecification | None = None

    @model_validator(mode='after')
    def distinct_criteria(self):
        if self.drawing is not None:
            self.drawing.require_resolved()
        diagnostics = measurement_diagnostics(self)
        identities = [item.id for item in (*self.criteria, *self.sections, *self.cylinders, *self.vertices, *self.measurements)]
        if len(set(identities)) != len(identities):
            diagnostics.append('CAD criterion identifiers must be unique')
        if 'dimensions_mm' not in {item.metric for item in self.criteria}:
            diagnostics.append('CAD plan requires explicit measured dimensions')
        if set(identities) & {'design-quality', 'cut-safety'}:
            diagnostics.append('Design-quality and cut-safety identities belong to runtime checks')
        if len(identities) > MAX_PROPOSED_CHECKS:
            diagnostics.append('CAD verification requires at most 64 checks')
        if len(self.model_dump_json().encode()) > 64_000:
            diagnostics.append('CAD recipe exceeds its byte budget')
        if diagnostics:
            raise ValueError('CAD measurement preflight:\n' + '\n'.join(diagnostics))
        return self

    def contracts(self):
        if self.drawing is not None:
            return ([f'Pièce CAO : {self.title}. Modèle SolidCraft éditable, exports STEP/STL et aperçu versionné.']
                + [f'{item.label} : {item.value:g} {item.unit} — {item.annotation}'
                   for item in self.drawing.dimensions if item.value is not None]
                + [f'Contrôle : {next(d.label for d in self.drawing.dimensions if d.id == item.dimension_id)} ; '
                   f'tolérance {item.absolute_tolerance:g} {"°" if item.operation == "angle" else "mm"}.'
                   for item in self.measurements]
                + [f'Vérification géométrique avant livraison ; jusqu’à {self.max_repairs} réparation(s), budget total 120 secondes.']
                + [item.describe() for item in self.criteria]
                + [f'Limite à prendre en compte : {item}' for item in self.limitations])
        return ([f'Pièce CAO : {self.title}. Solide fermé, document SolidCraft éditable, exports STEP/STL et aperçu versionné.']
                + [f'Vérification avant livraison ; jusqu’à {self.max_repairs} réparation(s) de géométrie dans les critères confirmés, budget total 120 secondes.']
                + [item.describe() for item in self.criteria]
                + [f'{item.label} : surface cylindrique analytique R{item.radius_mm:g} mm, '
                   f'axe XYZ {item.axis}, centre transversal {item.center_mm}; '
                   f'tolérance {item.absolute_tolerance_mm:g} mm. Les sections contrôlent les limites du profil.'
                   for item in self.cylinders]
                + [f'{item.label} : section XYZ axe {item.axis}, point {item.point_mm}, '
                   f'matière attendue {item.intervals_mm} mm (tolérance {item.absolute_tolerance_mm:g} mm)'
                   for item in self.sections]
                + ([f'Cote du dessin {item.id} — {item.label} : {item.value:g} {item.unit} '
                    f'({item.origin}, annotation : {item.annotation})'
                    for item in self.drawing.dimensions if item.value is not None] if self.drawing else [])
                + [f'Limite à prendre en compte : {item}' for item in self.limitations])


class CadRepair(Contract):
    commands: Annotated[tuple[CadCommand, ...], AfterValidator(check_commands)] = Field(min_length=1, max_length=96)
    cut_intents: tuple[CutIntent, ...] | None = Field(default=None, max_length=16)


class CadSamplingAdjustment(Contract):
    points: dict[Identity, Vector] = Field(min_length=1, max_length=16)


async def refine_cad_sampling(provider, plan, observations, *, model=None):
    """Move inconclusive line probes while preserving every acceptance target."""
    eligible = {item.criterion_id for item in observations if item.status == 'inconclusive'}
    eligible &= {item.id for item in plan.sections}
    if not eligible:
        raise ValueError('Sampling refinement requires an inconclusive section observation')
    raw = await provider.chat_complete(messages=[{'role': 'system', 'content':
        'Select stable interior line-probe points for these inconclusive CAD sections. '
        'Return JSON matching ' + json.dumps(CadSamplingAdjustment.model_json_schema()) +
        '. Only listed inconclusive section IDs may move. Every axis, interval target, '
        'requirement, tolerance and geometry command remains fixed. Use a nearby interior '
        'point that measures the same feature; report no guessed acceptance values.'},
        {'role': 'user', 'content': json.dumps({'plan': plan.model_dump(mode='json'),
            'eligible_sections': sorted(eligible),
            'observations': [item.model_dump(mode='json') for item in observations]}, ensure_ascii=False)}],
        model=model or 'default', stream=False, max_tokens=2000, temperature=0.1)
    raw = raw.strip()
    if raw.startswith('```') and raw.endswith('```'):
        raw = '\n'.join(raw.splitlines()[1:-1])
    update = CadSamplingAdjustment.model_validate_json(raw)
    if not set(update.points) <= eligible:
        raise ValueError('Sampling refinement references a section outside its inconclusive scope')
    sections = []
    for section in plan.sections:
        point = update.points.get(section.id)
        if point is not None:
            # A local probe correction cannot jump to another feature or body.
            if any(abs(a-b) > 0.01 for a, b in zip(point, section.point_mm)):
                raise ValueError('Sampling refinement exceeds the 0.01 mm local adjustment limit')
            section = section.model_copy(update={'point_mm': point})
        sections.append(section.model_dump())
    return CadPlan.model_validate({**plan.model_dump(), 'sections': sections})


class CadClarification(Contract):
    outcome: Literal['clarification']
    question: str = Field(min_length=1, max_length=1000)
    dimension_ids: tuple[Identity, ...] = Field(default=(), max_length=16)
    reason: Literal['illegible', 'missing', 'conflicting', 'unsupported', 'units']


class CadClarificationRequired(ValueError):
    """A specialist question that suspends construction before confirmation."""
    def __init__(self, clarification):
        self.clarification = clarification
        super().__init__(clarification.question)


async def draft_cad_repair(provider, plan, checks, *, model=None, command_diagnostic=None, candidate_context=None):
    """Propose a fresh candidate recipe against the unchanged measured contract."""
    if provider is None:
        raise ValueError('CAD repair requires a configured model')
    response = await provider.chat_complete(messages=[{'role': 'system', 'content':
        'Repair the reproduced CAD geometry defect using SolidCraft 0.28.0 geometry commands. '
        'Return a complete replacement recipe applied to the original document, including '
        'all required original features. Preserve drawing requirements and measured targets. '
        'Preserve the world coordinate frame used by the recorded verification procedures. '
        'Use actual sketch planes, bounds and face observations to locate each operation. '
        'The engine requires numeric radius/diameter for sketch.circle.center; use numeric '
        'values or use a supported driving dimension afterward. Primitive solid operations '
        'and parameters.change accept expressions according to their own command contracts. '
        'Return JSON matching: ' + json.dumps(CadRepair.model_json_schema())},
        {'role': 'user', 'content': json.dumps({'confirmed_plan': plan.model_dump(mode='json'),
            'observations': [item.model_dump(mode='json') for item in checks],
            'command_diagnostic': command_diagnostic, 'candidate_context': candidate_context}, ensure_ascii=False)}],
        model=model or 'default', stream=False, max_tokens=8192, temperature=0.1)
    response = response.strip()
    if response.startswith('```') and response.endswith('```'):
        response = '\n'.join(response.splitlines()[1:-1])
    repair = CadRepair.model_validate_json(response)
    intents = repair.cut_intents if repair.cut_intents is not None else plan.cut_intents
    validate_cut_intents(repair.commands, intents, plan.drawing)
    return CadPlan.model_validate({**plan.model_dump(), 'commands': [item.model_dump() for item in repair.commands],
                                   'cut_intents': [item.model_dump() for item in intents]})


async def draft_cad_plan(provider, objective, *, context=None, model=None, drawing=None, command_reference=None, images=None, require_workflow=False):
    """Generate the bounded recipe before the user confirms its measured scope."""
    if provider is None:
        raise ValueError('CAD planning requires a configured model')
    schema = CadRecipe.model_json_schema()
    if require_workflow:
        schema.setdefault('required', []).append('workflow')
        schema['properties']['workflow'] = {'$ref': '#/$defs/CadWorkflow'}
    # Existing contracts retain legacy bindings for replay. Fresh proposals
    # use requirement methods and actual observations throughout.
    schema['$defs']['CadSection']['properties'].pop('bindings', None)
    schema['$defs'].pop('DimensionBinding', None)
    schema['$defs'].pop('SectionOperand', None)
    prompt = (
        'Plan a small mechanical CAD part using SolidCraft 0.28.0 headless, mm units. '
        'Return one JSON object matching this recipe schema: ' + json.dumps(schema)
        + '\nIf a faithful recipe requires clarification, return this alternative schema instead: '
        + json.dumps(CadClarification.model_json_schema())
        + '\nExplain the uncertain feature as a question. Reference existing dimension IDs when relevant. '
        'A clarification contains no construction commands or acceptance criteria. '
        'Include workflow design intent: named driving parameters, native expressions and dependencies; '
        'sketch and feature purposes, body names, and complete group membership. '
        'Use constrained sketches with dimensional drivers and datum references. '
        'Explain intentional remaining degrees of freedom and primitive-only construction. '
        'The runtime imports workflow parameters atomically, checks solver state and saved groups. '
        + '\nUse parameter expressions when dimensions may change. Available primitives: '
        'parameters.change {name,expression}; solid.box {length,width,height,corner?,body_name?,operation?,targets?}; '
        'solid.cylinder {radius,height,base?,body_name?,operation?,targets?}. Operation: new, join, cut, intersect. '
        'A cut needs targets with the existing body name. Use dimensions_mm in world XYZ. '
        'Create new parameters individually with name/expression. The changes map updates '
        'existing parameters only. Keep the recipe within 64 commands; use a concise set '
        'of driving parameters and numeric constants where appropriate. '
        'The command_reference contains installed engine documentation for sketches, '
        'extrusions, rounded profiles, chamfers and fillets. Use their exact parameters. '
        'Keep numeric criteria faithful to the request. Add a volume target when an independent '
        'expected volume is established by the request or a documented derivation. '
        'For complex parts use local feature measurements and closed-body checks; the engine '
        'always records actual volume. An invented aggregate volume cannot substitute for feature checks. '
        'For drawing requirements prefer measurements: specify dimension_id and source operands; '
        'the runtime reads actual candidate geometry and compares to the immutable drawing value. '
        'Use operation difference for depths and coordinate offsets on the same axis. '
        'Use operation angle for perpendicular rise/run, with rise_origin and run_origin if '
        'coordinate differences are needed. Declare absolute_tolerance in mm or degrees. '
        'Use a cylinder diameter operand directly for diameter requirements. '
        'Fixed section targets remain independently checked topology samples. '
        'Prefer raw sections with intervals_mm omitted when a requirement '
        'measurement consumes the probe. The runtime obtains actual intervals and derives '
        'diameter, depth or position against the drawing requirement. This avoids guessed '
        'interval arithmetic. Keep intervals_mm=[] for required empty through-lines. '
        'Provide dedicated empty through-lines for all required through-holes and openings. '
        'Up to 32 sections are available within the total 64-check limit. All required features '
        'must have checks; a limitation cannot remove a requested geometric verification. '
        'An offset probe is a sample, and cannot stand in for an exact endpoint coordinate. '
        'For exact endpoints on a surface boundary use vertices: body, full point_mm, '
        'absolute_tolerance_mm. These read actual start/end coordinates from native body_topology edges. '
        'A measurement operand source vertex, reference vertex ID, quantity coordinate and axis '
        'reads an actual endpoint coordinate. Combine with analytic cylinders to check arc radius '
        'and endpoint positions independently. Native endpoint access is already available. '
        'For drawings, cover every critical dimension with a measurements method or '
        'dimensions_mm.dimension_bindings (dimension ID to XYZ index). Section intervals '
        'describe material along a full world-axis line through point_mm. A hole gives a gap; '
        'a recess changes intervals at its interior. Use several probes to check position, '
        'size and depth. Bind sampled measurements using the measurements field. '
        'The runtime computes coordinate differences and atan2(rise, run) in degrees. '
        'Every method retains its own explicit tolerance. '
        'Analytic cylinder checks are available in cylinders: actual native face radius and axis. '
        'Use radius_binding for a radius or diameter dimension: the runtime compares radius_mm '
        'for radius and exactly 2*radius_mm for diameter. Use center_bindings for coordinates perpendicular '
        'to its world axis. The coordinate along the axis is not a measurable cylinder-center coordinate. '
        'Use additional material sections for truncated arc endpoints, material side and axial extent. '
        'Choose supported bindings from this schema autonomously. Questions about the command or '
        'validation protocol are runtime capability concerns; user clarification addresses uncertain geometry. '
        'Expected values are millimetres, converted from inch when necessary. '
        'Describe criterion labels/title in the user language. The title names the part concisely and remains valid '
        'after completion; proposal/approval status is displayed separately by the runtime. List verification limitations explicitly. '
        'Use the supplied resolved drawing specification as the dimensional authority. '
        'The runtime owns the drawing specification. Output only the recipe; keep every dimension ID exactly '
        'as supplied. Bindings may reference only the supplied dimension IDs. Additional geometric samples '
        'can use empty bindings. Preserve user clarification values and their converted units. '
        'Preserve every feature and dimension; declare unsupported geometry before execution. '
        'Uncertain dimensions, wall-thickness guarantees and arbitrary topology validation require clarification. '
        'For an existing document, edit its parameters or geometry and preserve unrelated geometry. '
        'Every operation runs on a private document candidate after the contract is confirmed. '
        'Tools, external file access and shell execution belong to the runtime. Output JSON only.'
    )
    content = json.dumps({'objective': objective, 'existing_document': context,
            'drawing': drawing.model_dump(mode='json') if drawing else None,
            'command_reference': command_reference}, ensure_ascii=False)
    messages = [{'role': 'system', 'content': prompt},
        {'role': 'user', 'content': ([{'type': 'text', 'text': content}, *images] if images else content)}]
    # One correction consumes the same enclosing planning deadline and provider
    # budget. It receives the complete diagnostic from the rejected proposal.
    for attempt in range(2):
        raw = await provider.chat_complete(messages=messages,
            model=model or 'default', stream=False, max_tokens=8192, temperature=0.1)
        try:
            plan = validate_cad_proposal(raw, drawing=drawing, existing_document=context is not None)
            if require_workflow and plan.workflow is None:
                raise ValueError('Fresh CAD proposals require parametric workflow design intent')
            return plan
        except CadClarificationRequired:
            raise
        except ValueError as error:
            if attempt:
                raise
            messages = [*messages, {'role': 'assistant', 'content': raw},
                {'role': 'user', 'content': 'Correct the complete proposal using these preflight diagnostics. '
                 'Preserve every drawing requirement, feature and tolerance. Return the complete corrected JSON.\n'
                 + str(error)[:12000]}]


def validate_cad_proposal(raw, *, drawing=None, existing_document=False):
    """Validate a retained proposal using the runtime-owned interpretation."""
    raw = raw.strip()
    if raw.startswith('```') and raw.endswith('```'):
        raw = '\n'.join(raw.splitlines()[1:-1])
    proposed = json.loads(raw)
    if proposed.get('outcome') == 'clarification':
        clarification = CadClarification.model_validate(proposed)
        known = {item.id for item in drawing.dimensions} if drawing else set()
        if set(clarification.dimension_ids) - known:
            raise ValueError('CAD clarification references unknown drawing dimensions')
        raise CadClarificationRequired(clarification)
    if proposed.get('drawing') is not None:
        raise ValueError('CAD planner invented a drawing outside the runtime-bound interpretation')
    proposed.pop('drawing', None)
    recipe = CadRecipe.model_validate(proposed)
    # Bind the source interpretation supplied by the runtime. Model output
    # cannot replace its dimensions while drafting the recipe.
    errors = command_diagnostics(recipe.commands, existing_document=existing_document)
    try:
        plan = CadPlan.model_validate({**recipe.model_dump(),
            'drawing': drawing.model_dump() if drawing else None, 'max_repairs': 2})
    except ValueError as error:
        errors.append(str(error))
    if errors:
        raise ValueError('CAD proposal preflight:\n' + '\n'.join(errors))
    return plan
