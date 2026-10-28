"""Validate direct research conclusions against observed citation receipts."""
from typing import Literal

from pydantic import Field, model_validator

from .research import Claim, Contract
from .research_assessment import (AssessmentReport, CitationAssessment, ClaimAssessment,
                                  QuestionAssessment, SourceAssessment, apply_assessment)


class DirectCitation(Contract):
    passage_id: str
    receipt_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    quote: str = Field(min_length=8, max_length=2000)
    start: int | None = Field(default=None, ge=0, strict=True)
    end: int | None = Field(default=None, ge=1, strict=True)
    relation: Literal['supports', 'contradicts', 'context']
    direct: bool = False
    applicability: Literal['applicable', 'different_scope', 'unknown'] = 'applicable'
    applicability_basis: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode='after')
    def scoped_evidence(self):
        if self.applicability != 'applicable' and not self.applicability_basis:
            raise ValueError('Uncertain or different scope requires an explicit explanation')
        if self.applicability == 'different_scope' and self.relation != 'context':
            raise ValueError('Different-scope evidence must remain contextual to this finding')
        return self


class DirectFinding(Contract):
    id: str = Field(min_length=1, max_length=80)
    question_id: str
    text: str = Field(min_length=1, max_length=1500)
    semantic_support: Literal['supported', 'refuted', 'unresolved']
    reasoning: Literal['direct', 'qualified_inference'] = 'direct'
    citations: list[DirectCitation] = Field(min_length=1, max_length=8)
    scope: Literal['general', 'attributed_experience'] = 'general'
    scope_detail: str = Field(min_length=1, max_length=500)
    limitations: list[str] = Field(default_factory=list, max_length=8)


class DirectCoverage(Contract):
    question_id: str
    finding_ids: list[str] = Field(default_factory=list, max_length=12)
    gaps: list[str] = Field(default_factory=list, max_length=6)


class DirectConclusion(Contract):
    findings: list[DirectFinding] = Field(default_factory=list, max_length=12)
    questions: list[DirectCoverage] = Field(min_length=1, max_length=6)
    sources: list[SourceAssessment] = Field(default_factory=list, max_length=10)


def validate_conclusion(conclusion, state, receipts, *, review_required=False, review_completed=False):
    """Derive coverage and expose the actual verification layers.

    Exact citation checks are deterministic. Relevance, entailment, completeness
    and source suitability remain attributed model judgments. Review flags are
    supplied by the runtime after the separate review path has actually settled.
    """
    receipts.ingest(state)
    conclusion = conclusion.model_copy(deep=True)
    expected_questions = {q.id for q in state.questions}
    question_ids = [q.question_id for q in conclusion.questions]
    if len(question_ids) != len(set(question_ids)) or set(question_ids) != expected_questions:
        raise ValueError('Conclusion must account for every fixed question exactly once')
    findings = {f.id: f for f in conclusion.findings}
    if len(findings) != len(conclusion.findings):
        raise ValueError('Finding IDs must be unique')
    source_ids = [s.source_id for s in conclusion.sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError('Source judgments must be unique')
    observed_sources = {receipts.get(pid).source_id for pid in receipts.current}
    if set(source_ids) - observed_sources:
        raise ValueError('Source judgments require genuinely read sources')
    for source in conclusion.sources:
        provenance = receipts.get(source.provenance_passage_id)
        if provenance.source_id != source.source_id:
            raise ValueError('Source provenance belongs to another source')
        try:
            receipts.citation(provenance.passage_id, provenance.capture_sha256,
                source.provenance_quote or provenance.text, receipt_id=provenance.identity)
        except ValueError as exc:
            raise ValueError(f'Source provenance quotation was not observed: {exc}') from exc
        if source.independent_quote:
            # Method evidence can live in another passage of the same source.
            # Its literal occurrence must also have crossed the exposure boundary.
            for pid in receipts.current:
                receipt = receipts.get(pid)
                if receipt.source_id != source.source_id:
                    continue
                try:
                    receipts.citation(pid, receipt.capture_sha256,
                        source.independent_quote, receipt_id=receipt.identity)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError('Independent method quotation requires model-exposed evidence')
    cited_sources, validated = set(), []
    for finding in conclusion.findings:
        if finding.question_id not in expected_questions:
            raise ValueError('Finding refers to an unknown question')
        citations = []
        for citation in finding.citations:
            receipt = receipts.get(citation.passage_id)
            citations.append({**receipts.citation(citation.passage_id, receipt.capture_sha256,
                citation.quote, receipt_id=citation.receipt_id,
                start=citation.start, end=citation.end), 'relation': citation.relation,
                'applicability': citation.applicability,
                'applicability_basis': citation.applicability_basis})
            cited_sources.add(receipt.source_id)
        required_relation = {'supported': 'supports', 'refuted': 'contradicts'}.get(finding.semantic_support)
        if required_relation and not any(c.relation == required_relation for c in finding.citations):
            raise ValueError('Finding judgment lacks a citation with its declared relation')
        validated.append({**finding.model_dump(mode='json'), 'citations': citations})
    if cited_sources - set(source_ids):
        raise ValueError('Every cited source needs an explicit suitability judgment')
    assigned = set()
    complete = bool(findings)
    for question in conclusion.questions:
        if len(question.finding_ids) != len(set(question.finding_ids)):
            raise ValueError('Coverage repeats a finding')
        for finding_id in question.finding_ids:
            if finding_id not in findings or findings[finding_id].question_id != question.question_id:
                raise ValueError('Coverage references an unknown or unrelated finding')
        assigned.update(question.finding_ids)
        if not question.finding_ids and not question.gaps:
            raise ValueError('Unanswered questions require an explicit gap')
        complete &= bool(question.finding_ids) and not question.gaps
    if assigned != set(findings):
        raise ValueError('Every finding must belong to its question coverage')
    # Apply the existing source-role and shared-origin policy locally to the
    # single synthesis. Its semantic inputs are attributable to that model;
    # this deterministic pass never creates an independent review event.
    evidence_state = state.model_copy(deep=True)
    # The evidence assessor receives the explicitly judged subset. The acquired
    # source inventory remains intact on the runtime state and in the result.
    evidence_state.sources = [s for s in evidence_state.sources if s.id in source_ids]
    evidence_state.passages = [p for p in evidence_state.passages
                              if p.id in receipts.current and p.source_id in source_ids]
    evidence_state.claims = [Claim(id=f.id, question_id=f.question_id, text=f.text,
        basis=f.scope_detail, scope=f.scope, limitations=f.limitations) for f in conclusion.findings]
    report = AssessmentReport(sources=conclusion.sources,
        claims=[ClaimAssessment(claim_id=f.id, relevant=True, rationale=f.scope_detail,
            missing_evidence=[c.applicability_basis for c in f.citations if c.applicability == 'unknown'],
            considered_source_ids=[s.id for s in evidence_state.sources if s.status == 'read'],
            citations=[CitationAssessment(passage_id=c.passage_id, quote=c.quote,
                relation=c.relation, direct=c.direct, start=c.start, end=c.end,
                explanation=f.scope_detail) for c in f.citations])
            for f in conclusion.findings],
        questions=[QuestionAssessment(question_id=q.question_id,
            complete=bool(q.finding_ids) and not q.gaps, claim_ids=q.finding_ids,
            missing_evidence=q.gaps, rationale='Coverage proposed by direct synthesis')
            for q in conclusion.questions])
    if conclusion.findings or conclusion.sources:
        assessed, audits = apply_assessment(evidence_state, report)
    else:
        assessed, audits = [], []
        evidence_state.answer_status = 'partial'
    derived = {f.id: f for f in assessed}
    for item in validated:
        item['proposed_semantic_support'] = item['semantic_support']
        # Literal quotation and source suitability checks preserve uncertainty
        # explicitly retained by the synthesis that interpreted the passages.
        item['semantic_support'] = ('unverified' if item['semantic_support'] == 'unresolved'
                                    else derived[item['id']].status)
        item['limitations'] = list(dict.fromkeys(item['limitations'] + derived[item['id']].limitations))
    complete &= evidence_state.answer_status == 'complete'
    complete &= all(f.semantic_support != 'unresolved' for f in findings.values())
    complete &= all(c.applicability != 'unknown' for f in findings.values() for c in f.citations)
    complete &= all(s.suitability == 'suitable' for s in conclusion.sources if s.source_id in cited_sources)
    complete &= not review_required or review_completed
    # Carry derived deficits into the next attempt, even when the model omitted
    # a gap while proposing a complete answer. Preserve the proposed findings.
    for question in conclusion.questions:
        deficits = [f"Finding {fid} remains {next(item['semantic_support'] for item in validated if item['id'] == fid)}"
                    for fid in question.finding_ids
                    if next(item['semantic_support'] for item in validated if item['id'] == fid)
                    not in {'supported', 'refuted'}]
        question.gaps = list(dict.fromkeys([*question.gaps, *deficits]))
        coverage = next((item for item in evidence_state.question_coverage
                         if item['question_id'] == question.question_id), None)
        if coverage is not None:
            coverage['missing_evidence'] = list(dict.fromkeys([*coverage['missing_evidence'], *question.gaps]))
    return {'outcome': 'complete' if complete else 'partial',
            'findings': validated, 'questions': [q.model_dump(mode='json') for q in conclusion.questions],
            'sources': [s.model_dump(mode='json') for s in conclusion.sources],
            'source_inventory': [{'source_id': source.id, 'acquisition_status': source.status,
                'capture_sha256': source.content_sha256,
                'exposed': any(receipts.exposed.get(receipts.get(pid).identity)
                               for pid in receipts.current if receipts.get(pid).source_id == source.id),
                'assessment': 'evaluated' if source.id in source_ids else 'unassessed'}
                for source in state.sources],
            'evidence_audits': audits,
            'question_coverage': evidence_state.question_coverage,
            'citation_integrity': 'verified' if validated else 'no_citations',
            'semantic_assessment': 'model_judgment',
            'independent_review': 'completed' if review_completed else 'required' if review_required else 'skipped'}
