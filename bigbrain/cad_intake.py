"""Specialist drawing intake with conversation-owned evidence and revision checks."""

import json
from types import SimpleNamespace

from pydantic import Field, model_validator

from .cad_contracts import Contract
from .cad_drawings import DrawingSource, DrawingSpecification
from .cad_decision_transport import decision_tool_schema, parse_decision_response
from .cad_planning import CadClarification, CadClarificationRequired
from .front.cad_context import design_context, drawing_image_blocks, save_clarification, verified_images
from .front.decision import CadInput, CadRoute, Clarify, Delegate
from .llm.call_trace import trace_call
from .llm.conversation import conversation_scope
from .llm.usage import capture_usage
from .web.sessions import SessionStore


class DrawingIntake(Contract):
    drawing: DrawingSpecification
    question: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode='after')
    def resolved_contract(self):
        if self.question is None:
            self.drawing.require_resolved()
        return self


async def prepare_drawing(provider, payload, bus, source):
    """Interpret sources before contract preparation and preserve clarification authority."""
    session_id = payload.get('session_id')
    context, inventory = design_context(session_id)
    if not inventory:
        return None
    if not getattr(getattr(provider, 'entry', None), 'vision', False):
        raise ValueError('Le modèle CAD sélectionné doit prendre en charge les images.')
    context = context or {}
    session = SessionStore().get(session_id) or {}
    sources = context.get('sources') or inventory
    verified_images(sources)
    drawing_sources = [DrawingSource(attachment_id=item['id'], sha256=item['sha256']) for item in sources]
    images = drawing_image_blocks(SimpleNamespace(sources=drawing_sources), session_id)
    statements = [{'id': message['id'], 'text': message.get('text', '')}
                  for message in session.get('messages', []) if message.get('role') == 'user']
    packet = {'objective': payload['user_request'], 'sources': [s.model_dump(mode='json') for s in drawing_sources],
              'retained_design': context, 'user_statements': statements}
    await bus.broadcast_event(source=source, event_type='cad.intake.started',
        payload={'session_id': session_id, 'task_id': payload.get('_plan_id'),
                 'context_revision': context.get('revision', 0)})
    with conversation_scope(session_id, 'worker:cad_intake'), capture_usage() as records:
        with trace_call(provider, 'cad.intake', correlation={'session_id': session_id}, records=records):
            raw = await provider.chat_complete(messages=[{'role': 'system', 'content':
                'Prepare the CAD drawing dossier from the supplied images and exact user statements. '
                'Retain confirmed dimensions, stable IDs and exact source hashes. Use every useful view. '
                'Record user dimensions with origin=user and the exact message ID and quotation; '
                'dependencies are arithmetic inputs only. Preserve unresolved dimensions and conflicting '
                'annotations as blocking issues. Ask one targeted necessary question in French when '
                'critical geometry or units remain unspecified. Readable annotations take precedence '
                'over perspective. Return the interpreted drawing and question, or null question when '
                'all critical requirements are resolved. Construction requires subsequent contract confirmation.'},
                {'role': 'user', 'content': [{'type': 'text', 'text': json.dumps(packet, ensure_ascii=False)}, *images]}],
                tool_schema=decision_tool_schema(DrawingIntake.model_json_schema()),
                max_tokens=8192, temperature=0.1)
    interpreted = DrawingIntake.model_validate(parse_decision_response(raw))
    # This shared persistence boundary checks quoted user facts, source ownership,
    # critical-dimension retention and the revision captured before inference.
    if interpreted.question:
        decision = Clarify(operation='clarify', reply=interpreted.question, cad=True, drawing=interpreted.drawing)
    else:
        decision = Delegate(operation='delegate', reply='Le dossier CAO est prêt pour le contrat.',
            objective=payload['user_request'], route=CadRoute(brain='cad_brain',
                payload=CadInput(type='model_cad', drawing=interpreted.drawing,
                    document_id=payload.get('document_id'), base_revision=payload.get('base_revision'))))
    last = next((message for message in reversed(session.get('messages', [])) if message.get('role') == 'user'), {})
    updated = save_clarification(session_id, decision, last.get('text', ''), last.get('id'), sources,
                                 expected_revision=context.get('revision', 0))
    if updated is None:
        raise ValueError('La conversation CAO est indisponible pendant la préparation.')
    await bus.broadcast_event(source=source, event_type='cad.context.updated',
        payload={'session_id': session_id, 'context': updated})
    await bus.broadcast_event(source=source, event_type='cad.intake.finished',
        payload={'session_id': session_id, 'context_revision': updated['revision'],
                 'outcome': 'clarification' if interpreted.question else 'resolved'})
    if interpreted.question:
        unresolved = tuple(item.id for item in interpreted.drawing.dimensions if item.origin == 'unresolved')
        issue = next((item for item in interpreted.drawing.issues if item.blocking), None)
        raise CadClarificationRequired(CadClarification(outcome='clarification', question=interpreted.question,
            dimension_ids=issue.dimension_ids if issue else unresolved[:16], reason=issue.reason if issue else 'missing'))
    return interpreted.drawing
