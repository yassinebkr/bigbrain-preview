"""Documentary delivery with runtime-validated observation references."""


def finish_documentary(state, action, claims):
    """Settle a cited synthesis while preserving its independent-review status."""
    passages = {p.id: p for p in state.passages}
    sources = {s.id: s for s in state.sources}
    questions = {q.id for q in state.questions}
    gaps = list(action.remaining_gaps)
    for claim in claims:
        if claim.question_id not in questions:
            raise ValueError("Documentary claim references an unknown question")
        if not any(link.relation == "supports" for link in claim.evidence):
            raise ValueError("Documentary claims require observed supporting passages")
        for link in claim.evidence:
            passage = passages.get(link.passage_id)
            source = sources.get(passage.source_id) if passage else None
            if (passage is None or source is None or source.status != "read"
                    or not passage.text.strip() or not passage.observation_sha256
                    or passage.observation_sha256 != source.content_sha256):
                raise ValueError("Documentary citation requires a current read observation")
    covered = {claim.question_id for claim in claims}
    gaps.extend(q.text for q in state.questions if q.id not in covered)
    state.claims = [claim.model_copy(update={"status": "unverified"}) for claim in claims]
    state.assessments = []
    state.assessment_error = None
    state.answer_status = "unassessed"
    state.question_coverage = []
    state.status = "partial" if gaps or not claims else "completed"
    state.reason = "Synthèse documentaire sourcée · revue indépendante non effectuée."
    if gaps:
        state.reason += " Points restants : " + "; ".join(gaps)[:1200]
