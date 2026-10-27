"""Targeted evidence packets and deterministic complement preflight.

The original request remains immutable. Recovery collection sees the remaining
questions, proposed acquisitions and their local evidence rather than prior
drafts, complete source catalogs and independent-control audit transcripts.
"""
from __future__ import annotations

import json

from .research import Action
from .research_context import InspectionBudgetExceeded


class ComplementRejected(ValueError):
    """A control proposal requires correction before recovery acquisition."""

    def __init__(self, errors):
        super().__init__('Targeted complement requires a valid acquisition of additional evidence')
        self.diagnostic = {'contract':'ResearchComplement', 'code':'complement_preflight', 'errors':errors}


def target_diagnostics(state, requests):
    """Check executable selectors and already-inspected capture identities."""
    sources = {source.id:source for source in state.sources}
    inspection = (state.dossier or {}).get('packet', {}).get('inspection', {}).get('sources', {})
    errors = []
    for index, request in enumerate(requests):
        try:
            Action.model_validate(request.model_dump())
        except ValueError as exc:
            errors.append({'type':'invalid_target', 'field':f'targets[{index}]', 'message':str(exc)[:700]})
        source = sources.get(request.source_id)
        if request.tool == 'open' and source is None:
            errors.append({'type':'unknown_source', 'field':f'targets[{index}]',
                           'message':'The requested source has not been observed'})
        inspected = inspection.get(request.source_id, {})
        if (request.tool == 'open' and request.group_ids and not request.refresh
                and request.mode == 'http'
                and request.observation_sha256 == inspected.get('observation_sha256')
                and set(request.group_ids).issubset(inspected.get('selected_groups', []))):
            errors.append({'type':'already_inspected', 'field':f'targets[{index}]',
                           'message':'All requested sections of this capture are already in the frozen dossier'})
    return errors


def complement_packet(state, control, remaining, *, byte_limit=5000):
    """Assemble complete target-local passages within an explicit byte envelope.

    Invalid proposals remain visible in diagnostics. The caller must reject them
    before inference or acquisition; packet construction never rewrites actions.
    """
    targets = control.complement
    questions = {request.question_id for request in targets}
    unknown = questions - {question.id for question in state.questions}
    if unknown:
        raise ComplementRejected([{'type':'unknown_question', 'field':'targets',
                                   'message':'Target question is outside the fixed research scope'}])
    source_ids = {request.source_id for request in targets if request.source_id}
    sources, passages = [], []
    for source in state.sources:
        if source.id not in source_ids:
            continue
        sources.append({'id':source.id, 'url':source.url, 'status':source.status,
                        'content_sha256':source.content_sha256, 'error':source.error})
        selected = set()
        for target in (request for request in targets if request.source_id == source.id):
            catalog = source.acquisition.get('navigation', {}).get('catalog', [])
            contexts = [item['context'] for item in catalog if item['id'] in target.group_ids]
            for passage in state.passages:
                if passage.source_id != source.id or passage.observation_sha256 != source.content_sha256:
                    continue
                if target.group_ids:
                    # Navigation stores a bounded heading suffix; passages
                    # retain the full hierarchy from the original observation.
                    relevant = any((passage.context[-len(context):] == context if context
                                    else not passage.context) for context in contexts)
                elif target.focus:
                    relevant = target.focus.casefold() in (' '.join(passage.context) + ' ' + passage.text).casefold()
                else:
                    relevant = False
                if relevant:
                    selected.add(passage.id)
        passages.extend({'id':p.id, 'source_id':p.source_id, 'text':p.text,
                         'context':p.context, 'observation_sha256':p.observation_sha256}
                        for p in state.passages if p.id in selected)
    gaps = list(dict.fromkeys(control.original_request_gaps + [gap for question in control.questions
        if question.question_id in questions for gap in question.missing_evidence]))
    packet = {'state': {'original_request':state.original_request or state.objective,
        'questions':[q.model_dump(mode='json') for q in state.questions if q.id in questions],
        'sources':sources, 'passages':passages, 'claims':[]},
        'control_gaps':gaps, 'targets':[r.model_dump(mode='json', exclude_defaults=True) for r in targets],
        'target_diagnostics':target_diagnostics(state, targets),
        'evidence_scope':'Target-local passages only; the frozen dossier retains all prior evidence.',
        'remaining':remaining}
    if len(json.dumps(packet, ensure_ascii=False, separators=(',', ':')).encode()) > byte_limit:
        raise InspectionBudgetExceeded('Target-local evidence exceeds the complement packet envelope')
    return packet
