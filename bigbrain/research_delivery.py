"""Compact user-facing delivery from runtime-reviewed research evidence."""


def partial_message(state):
    """Expose reviewed findings and remaining scope within a small chat response."""
    return research_message(state)


def research_message(state):
    """Deliver findings with their URLs and qualifications directly to the chat."""
    completed = state.status == 'completed'
    documentary = state.delivery_mode == "documentary" and not state.review_reason
    lines = (["Synthèse documentaire sourcée · sans revue indépendante." if documentary
              else "Recherche terminée."] if completed else ["Recherche incomplète."])
    passages = {p.id:p for p in state.passages}
    sources = {s.id:s for s in state.sources if s.status == "read"}
    for claim in state.claims:
        if (claim.status not in {"supported", "refuted"} and not (documentary and claim.status == "unverified")) or len(claim.text) > 900:
            continue
        urls = list(dict.fromkeys(sources[passages[e.passage_id].source_id].url
            for e in claim.evidence if e.passage_id in passages
            and passages[e.passage_id].source_id in sources))
        if not urls:
            continue
        label = "Documenté · sans revue indépendante" if documentary and claim.status == "unverified" else "Établi" if claim.status == "supported" else "Réfuté"
        line = f"{label} : {claim.text}\n" + " · ".join(f"[Source]({url})" for url in urls[:2])
        if claim.limitations:
            line += '\nRéserves : ' + '; '.join(claim.limitations)
        if sum(map(len, lines)) + len(line) > (6000 if completed else 2400):
            break
        lines.append(line)
    gaps = [str(g) for q in state.question_coverage if q.get("status") != "covered"
            for g in q.get("missing_evidence", [])]
    if state.observations and state.observations[-1].action.tool == 'conclude':
        gaps.extend(state.observations[-1].action.remaining_gaps)
    for gap in list(dict.fromkeys(gaps))[:2]:
        if len(gap) <= 350:
            lines.append("À établir : " + gap)
    lines.append("Les passages consultés sont disponibles dans l’Atelier." if completed
                 else "Les preuves et les points restants sont conservés dans l’Atelier.")
    return "\n\n".join(lines)
