"""Confirmed CAD definitions, construction recipes and candidate inspections."""

import json
from typing import Literal

from pydantic import AfterValidator, Field
from typing import Annotated
from .cad_resources import check_commands

from .cad_contracts import Contract
from .cad_drawings import DrawingSpecification
from .cad_planning import CadCommand, CadRecipe, command_diagnostics, validate_cad_proposal
from .cad_workflow import CadWorkflow
from .cad_cut_contracts import CutIntent, validate_cut_intents


class CadDefinition(Contract):
    title: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=20000)
    drawing: DrawingSpecification
    max_repairs: int = Field(default=2, strict=True, ge=0, le=2)
    execution_seconds: int = Field(default=600, strict=True, ge=1, le=600)

    def contracts(self):
        self.drawing.require_resolved()
        return [f'Pièce CAO : {self.title}. Nouveau modèle éditable, exports STEP/STL et aperçu versionné.',
            f'Périmètre : {self.objective}',
            *[f'{item.label} : {item.value:g} {item.unit} — {item.annotation}'
              for item in self.drawing.dimensions if item.value is not None],
            'Vérifier les cotes et les détails locaux, les perçages débouchants et les ouvertures demandées. '
            'Chaque cote critique doit disposer d’une mesure issue du candidat construit.',
            'Chaque découpe conserve son intention liée au dessin. Les dépassements des outils doivent '
            'être vérifiés avant exécution pour préserver les parois, détails voisins et autres corps.',
            'Précision de validation nominale : au plus 0,05 mm pour les longueurs et 0,1° pour les angles. '
            'La certification des tolérances et des ajustements de fabrication reste hors du livrable.',
            f'Construction et inspection séparées ; jusqu’à {self.max_repairs} réparations dans un budget de '
            f'{self.execution_seconds} secondes. Une vérification incomplète empêche la livraison.']


class CadConstruction(Contract):
    title: str = Field(min_length=1, max_length=160)
    commands: Annotated[tuple[CadCommand, ...], AfterValidator(check_commands)] = Field(min_length=1, max_length=96)
    max_repairs: int = Field(default=2, strict=True, ge=0, le=2)
    workflow: CadWorkflow
    cut_intents: tuple[CutIntent, ...] = Field(default=(), max_length=16)


class CadReferenceRequest(Contract):
    operation: Literal['request_command_reference']
    commands: tuple[str, ...] = Field(default=(), max_length=16)
    skills: tuple[str, ...] = Field(default=(), max_length=3)


def reproduced_defect_is_repairable(plan, checks):
    """Allow repair when inconclusive requirements depend on reproduced failures."""
    failed = {item.criterion_id for item in checks if item.status == 'failed'}
    if not failed:
        return False
    methods = {item.id: item for item in plan.measurements}
    for observation in checks:
        if observation.status != 'inconclusive':
            continue
        method = methods.get(observation.criterion_id)
        if method is None:
            return False
        operands = (method.first, method.second, method.rise_origin, method.run_origin)
        if not any(operand and operand.reference in failed for operand in operands):
            return False
    return True


def parse_object(raw):
    raw = raw.strip()
    if raw.startswith('```') and raw.endswith('```'):
        raw = '\n'.join(raw.splitlines()[1:-1])
    return json.loads(raw)


async def draft_construction(provider, definition, reference, images, *, model=None, diagnostic=None, previous=None,
                             diagnostic_history=()):
    packet = {'definition': definition.model_dump(mode='json'), 'command_reference': reference,
              'available_commands': sorted(getattr(reference, 'catalog', {})),
              'available_skills': getattr(reference, 'skills', ()),
              'retrieved_reference': reference.retrieved() if hasattr(reference, 'retrieved') else None,
              'previous_recipe': previous.model_dump(mode='json') if previous else None,
              'diagnostic': diagnostic, 'diagnostic_history': list(diagnostic_history)}
    messages = [{'role': 'system', 'content':
        'Create the complete editable CAD geometry for this confirmed definition using SolidCraft 0.28.0, mm. '
        'Return JSON matching ' + json.dumps(CadConstruction.model_json_schema()) +
        '. When a needed command signature is absent, first return ' + json.dumps(CadReferenceRequest.model_json_schema()) +
        '. Choose command IDs from available_commands and request related signatures together. '
        'Request bundled native guides through skills when workflow guidance is needed. '
        'Native references explain tool usage; the confirmed definition and measured acceptance '
        'requirements remain authoritative. Pixel comparisons cannot establish drawing dimensions. '
        'Use the installed tools for sweeps, revolutions, lofts, shells, patterns or other appropriate '
        'operations. A reference request performs no geometry mutation. Never substitute a placeholder '
        'sketch for a missing command signature. '
        '. Focus on construction. Verification is assembled separately from actual native observations. '
        'Declare the workflow: named parameters with native expressions, canonical mm/deg units, '
        'source_dimension IDs for requirements, and dependencies for derived values; named sketch '
        'and feature intents, body names and group membership. '
        'Every sketch is also a timeline feature: include its name in workflow.features '
        'and in its group.features as well as group.sketches. The runtime imports parameters '
        'and arranges these groups. Every feature and sketch needs a clear purpose and name. '
        'Prefer dimensioned sketches using sketch.draw.dimensioned with locate:true and driving '
        'dimensions referencing declared parameters. Check native solver state. Avoid blanket '
        'curve fixation and redundant constraints; explain intentional remaining degrees of freedom. '
        'Build profiles in order: geometry, independent geometric relationships, functional driving '
        'dimensions, then sketch.finish before extrusion. Account for constraints created by drawing '
        'helpers; add each independent relationship once. Use reference dimensions for derived '
        'annotations. Coordinate expressions alone do not replace functional driving dimensions. '
        'Use datum planes and parameter-based offsets so feature references survive parameter edits. '
        'Use editable feature history. A primitive-only construction needs its explicit rationale. '
        'Preserve every feature, dimension, user answer and chosen profile. Use exact command_reference '
        'parameters. Put user parameters in workflow.parameters; the runtime imports them atomically. '
        'Keep geometry within 64 commands. Circle diameter/radius in sketch.circle.center '
        'requires a number. Primitive solids and sketch point coordinates support their documented '
        'expressions. Use explicit body names and targets for cuts. All operations run on a private candidate. '
        'Every removal command requires a cut_intent referencing its command_index, explicit targets, '
        'drawing feature_id and dimension_ids. Declare opening/stop planes with unit outward normals. '
        'The cut_intents inventory covers commands with operation cut/subtract/difference and '
        'solid.hole. Native solid.fillet and solid.chamfer are finishing features recorded in the '
        'workflow and independently checked through their confirmed radius/distance requirements. '
        'Plane origin coordinates can use declared native length parameter expressions. Opening planes '
        'must lie on the actual exterior material before cutting. Each tool extension beyond an opening '
        'must intersect no existing material, including other bodies. '
        'For an already open hole, anchor the opening plane on the surrounding material in that same '
        'plane rather than the empty hole center. '
        'An opening may declare alignment_tolerance_mm up to the confirmed 0.05 mm length tolerance '
        'when native Boolean healing shifts its planar face. The runtime resolves the measured plane '
        'within that tolerance, checks its outward orientation and still checks all extension collisions. '
        'Blind cuts require a stop plane. '
        'Use explicit solid cutters (pipe, cylinder, extrusion, sweep, revolution or loft) rather than '
        'solid.hole until its implicit cutter can be independently certified. For hollow pipe/flange '
        'contact failures, consider exterior union before a continuous bore cut, with the bore cutter '
        'extended only beyond verified openings; retain the original part dimensions and all details. '
        'For a rejected fillet/chamfer, actual_operand_geometry in the diagnostic contains the '
        'measured intermediate operand. Choose edges from this geometry and preserve the intended '
        'local feature; a smooth tangent seam cannot receive a corner fillet. Reuse retrieved_reference '
        'before requesting additional signatures. '
        'Preserve the observed failure history across repairs. Resolve each applicable prior rejection '
        'and retain successful corrections while fixing the latest failure. '
        'If an explicit cone cut times out, use the supplied actual operand topology to consider '
        'a native solid.chamfer on the intended mouth edge, preserving its confirmed C dimension. '
        'If correcting a command failure, return the complete recipe against the same definition.'},
        {'role': 'user', 'content': [{'type': 'text', 'text': json.dumps(packet, ensure_ascii=False)}, *images]}]
    # Reference and construction corrections have separate single-use slots.
    # Both remain inside the shared worker deadline and campaign allowance.
    corrections, reference_requests = {'reference': 0, 'construction': 0}, 0
    for attempt in range(5):
        raw = await provider.chat_complete(messages=messages, model=model or 'default',
            stream=False, max_tokens=16384, temperature=0.1)
        response = None
        try:
            response = parse_object(raw)
            if isinstance(response, dict) and response.get('operation') == 'request_command_reference':
                request = CadReferenceRequest.model_validate(response)
                if reference_requests >= 2 or not hasattr(reference, 'selected'):
                    raise ValueError('CAD command-reference request budget or catalog is unavailable')
                if not request.commands and not request.skills:
                    raise ValueError('CAD reference request requires commands or skills')
                signatures = await reference.describe(request.commands, request.skills)
                reference_requests += 1
                messages = [*messages, {'role': 'assistant', 'content': raw},
                    {'role': 'user', 'content': json.dumps(signatures, ensure_ascii=False)}]
                continue
            construction = CadConstruction.model_validate(response)
            validate_cut_intents(construction.commands, construction.cut_intents, definition.drawing)
            errors = command_diagnostics(construction.commands, existing_document=bool(construction.workflow.parameters))
            if errors:
                raise ValueError('CAD construction preflight: ' + '; '.join(errors))
            if construction.max_repairs > definition.max_repairs:
                raise ValueError('Construction repair ceiling exceeds the confirmed definition')
            return construction
        except ValueError as error:
            phase = ('reference' if isinstance(response, dict)
                     and response.get('operation') == 'request_command_reference' else 'construction')
            if corrections[phase]:
                raise
            corrections[phase] += 1
            messages = [*messages, {'role': 'assistant', 'content': raw},
                {'role': 'user', 'content': 'Correct the complete construction using this diagnostic. '
                 'Keep every confirmed dimension, assumption and acceptance obligation.\n' + str(error)[:12000]}]
    raise ValueError('CAD construction did not complete within its reference and correction allowance')


async def inspect_candidate(provider, definition, construction, observations, *, model=None, stop_on_error=False):
    """Choose checks from actual geometry while retaining independent requirements."""
    schema = CadRecipe.model_json_schema()
    schema['properties'].pop('commands')
    schema['required'].remove('commands')
    schema['properties'].pop('workflow')
    schema['properties'].pop('max_repairs')
    schema['properties'].pop('cut_intents', None)
    schema['$defs']['CadSection']['properties'].pop('bindings', None)
    schema['$defs'].pop('DimensionBinding', None)
    schema['$defs'].pop('SectionOperand', None)
    packet = {'definition': definition.model_dump(mode='json'), 'construction': construction.model_dump(mode='json'),
              'candidate_observations': observations}
    content = json.dumps(packet, ensure_ascii=False)
    if len(content.encode()) > 256000:
        raise ValueError('CAD inspection evidence exceeds its 256 KB packet limit')
    messages = [{'role': 'system', 'content':
        'Prepare verification of this actual CAD candidate against the confirmed drawing definition. '
        'Return JSON matching ' + json.dumps(schema) + '. Use the supplied actual body names, native '
        'edge endpoints, cylindrical faces and bounds to select measurements. All expected dimensions '
        'come from the confirmed definition even when the candidate is defective. Cover every critical '
        'dimension using measurements, envelope bindings or analytic cylinder bindings. '
        'Use raw sections with intervals_mm omitted for derived measurements. Use intervals_mm=[] '
        'for required empty through-lines and explicit intervals only for independently established '
        'topology checks. For a local through-hole use empty_span_mm with the two independently '
        'established flange faces; remote material on the same axis line remains preserved. '
        'Multiple holes create multiple ordered gaps; choose the correct gap interval. '
        'Use vertices for endpoints on boundaries, cylinders for analytic radii/axes. '
        'Requirement targets are read by the runtime. Differences require coordinate operands on '
        'the same axis. Angles use perpendicular rise/run with optional rise_origin and run_origin. '
        'Avoid copying observed defects into targets. Preserve every requested opening, depth and feature. '
        'There are 32 sections and at most 64 model-authored checks across all arrays. The runtime '
        'reserves two additional slots for design-quality and cut-safety. Tolerances must remain within 0.05 mm '
        'or 0.1 degree for requirement measurements; choose precision consistent with the measurement '
        'method. Manufacturing fits remain explicitly unqualified. Construction commands are already '
        'recorded; this inspection selects checks for their captured revision.'},
        {'role': 'user', 'content': content}]
    for attempt in range(2):
        raw = await provider.chat_complete(messages=messages, model=model or 'default', stream=False,
                                           max_tokens=8192, temperature=0.1)
        try:
            proposed = parse_object(raw)
            if any(key in proposed for key in ('commands', 'drawing', 'workflow', 'max_repairs', 'cut_intents')):
                raise ValueError('Inspection output must contain verification fields exclusively')
            plan = validate_cad_proposal(json.dumps({**proposed, 'title': construction.title,
                'workflow': construction.workflow.model_dump(mode='json'),
                'max_repairs': construction.max_repairs,
                'cut_intents': [item.model_dump(mode='json') for item in construction.cut_intents],
                'commands': [item.model_dump(mode='json') for item in construction.commands]}),
                drawing=definition.drawing, existing_document=bool(construction.workflow.parameters))
            for method in plan.measurements:
                dimension = next(item for item in definition.drawing.dimensions if item.id == method.dimension_id)
                if method.absolute_tolerance > (0.1 if dimension.unit == 'degree' else 0.05):
                    raise ValueError(f'Measurement tolerance exceeds confirmed precision: {method.id}')
            return plan
        except ValueError as error:
            if attempt or stop_on_error:
                raise
            messages = [*messages, {'role': 'assistant', 'content': raw},
                        {'role': 'user', 'content': 'Correct this inspection using all diagnostics; preserve '
                         'the confirmed requirements and precision.\n' + str(error)[:12000]}]
