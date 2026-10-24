"""Question-based section selection and compact research prompt views.

Groups source blocks by their heading context, ranks groups locally and retains
adjacent sections. Selection records expose omitted groups for further reading.
Review views assemble the original observed blocks independently of this ranker.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re


def words(text):
    """Tokenize Unicode words, identifiers and camel-case names for local ranking."""
    expanded = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return re.findall(r"[^\W_]+", expanded.casefold(), re.UNICODE)


def groups(blocks, observation):
    """Build atomic sections and collapse exact repeats within one observation."""
    sections = []
    for block in blocks:
        context = tuple(block.get("context", []))
        heading = re.fullmatch(r"h[1-6]", block.get("kind", ""))
        if not sections or heading or context != sections[-1]["context"]:
            sections.append({"context": context, "blocks": []})
        sections[-1]["blocks"].append(block)
    result, seen = [], {}
    for section in sections:
        fingerprint = json.dumps([section["context"], [(b.get("kind"), b["text"]) for b in section["blocks"]]],ensure_ascii=False)
        if fingerprint in seen:
            seen[fingerprint]["duplicate_sections"] += 1
            continue
        group = {"id": "g" + hashlib.sha256((observation+fingerprint).encode()).hexdigest()[:20],
                 "context": list(section["context"]), "blocks": section["blocks"], "duplicate_sections": 0}
        group["characters"] = len("\n".join(b["text"] for b in group["blocks"]))
        seen[fingerprint] = group
        result.append(group)
    return result


def rank(question, sections):
    """Compute local BM25-style retrieval scores for question terms."""
    query = set(words(question))
    documents = [Counter(words(" ".join(b["text"] for b in g["blocks"]))) for g in sections]
    lengths = [sum(d.values()) for d in documents]
    average = sum(lengths)/max(1,len(lengths)) or 1
    frequencies = Counter(term for d in documents for term in d)
    scored = []
    for i, document in enumerate(documents):
        value = 0
        for term in query.intersection(document):
            inverse = math.log(1+(len(documents)-frequencies[term]+.5)/(frequencies[term]+.5))
            frequency = document[term]
            value += inverse * frequency * 2.2/(frequency+1.2*(.25+.75*lengths[i]/average))
        scored.append((i,value))
    return sorted(scored,key=lambda item:(-item[1],item[0]))


def select(question, blocks, observation, *, limit=6000, requested=(), preferred_ids=None):
    """Select curated section blocks or explicitly requested original sections."""
    sections = groups(blocks,observation)
    all_characters = len("\n".join(b["text"] for g in sections for b in g["blocks"]))
    # Main-text extraction supplies decision candidates. Original sections keep
    # their identities and remain fully readable through explicit section IDs.
    candidates = [{**g,"blocks":[b for b in g["blocks"] if preferred_ids is None or b["id"] in preferred_ids]}
                  for g in sections]
    candidate_size = len("\n".join(b["text"] for g in candidates for b in g["blocks"]))
    ranked = rank(question,candidates)
    chosen, oversized = set(), []
    method = "local-bm25-sections"
    if requested:
        known = {g["id"]:i for i,g in enumerate(sections)}
        if any(gid not in known for gid in requested):
            raise ValueError("Requested section does not belong to this observation")
        chosen = {known[gid] for gid in requested}
        method = "explicit-section-ids"
    elif candidate_size <= min(limit,2200):
        chosen = {i for i,g in enumerate(candidates) if g["blocks"]}
        method = "complete-small-observation"
    else:
        # Adjacent sections supply local conditions and scope. Complete sections
        # remain atomic even if a shorter excerpt would obtain a higher score.
        anchors = [i for i,score in ranked if score > 0][:2]
        for anchor in anchors:
            package = {i for i in range(max(0,anchor-1),min(len(sections),anchor+2)) if candidates[i]["blocks"]}
            tentative = chosen | package
            cost = len("\n".join(b["text"] for i in sorted(tentative) for b in candidates[i]["blocks"]))
            if cost <= limit:
                chosen = tentative
            else:
                oversized.append(sections[anchor]["id"])
    chosen_sections = sections if requested else candidates
    partial = [sections[i]["id"] for i in sorted(chosen) if len(chosen_sections[i]["blocks"]) < len(sections[i]["blocks"])]
    selected = [dict(b,clipped=False,block_start=0,block_end=len(b["text"]))
                for i in sorted(chosen) for b in chosen_sections[i]["blocks"]]
    size = len("\n".join(b["text"] for b in selected))
    needs_context = not selected or size > limit or bool(oversized)
    if size > limit:
        selected, chosen, size = [],set(),0
    catalog = [{"id":g["id"],"context":g["context"],"characters":g["characters"]} for g in sections]
    selection = {"schema_version":"1.0", "method":method, "question_sha256":hashlib.sha256(question.encode()).hexdigest(),
                 "observation_sha256":observation, "status":"needs_context" if needs_context else "selected",
                 "selected_group_ids":[sections[i]["id"] for i in sorted(chosen)],
                 "partial_group_ids":partial,
                 "omitted_group_ids":[g["id"] for i,g in enumerate(sections) if i not in chosen],
                 "group_count":len(sections), "catalog":catalog,
                 "characters_available":all_characters, "characters_selected":size, "character_limit":limit,
                 "duplicate_sections":sum(g["duplicate_sections"] for g in sections), "oversized_group_ids":oversized,
                 "coverage":"complete" if len(chosen)==len(sections) and not partial else "partial"}
    return selected,selection


def compact_passage(passage):
    data = passage.model_dump(mode="json")
    return {k:v for k,v in data.items() if k in {"id","source_id","text","kind","context","clipped","observation_sha256"}
            and v not in (None,[],False)}


def passage_view(passages):
    """Share observation and heading metadata while preserving every citation ID."""
    contexts, lookup, items = [], {}, []
    for passage in passages:
        key = (passage.source_id, passage.observation_sha256, tuple(passage.context))
        if key not in lookup:
            lookup[key] = len(contexts)
            contexts.append({"source_id":key[0], "observation_sha256":key[1], "context":list(key[2])})
        item = {"id":passage.id, "text":passage.text, "kind":passage.kind, "context_ref":lookup[key]}
        if passage.clipped:
            item["clipped"] = True
        items.append(item)
    return {"passage_contexts":contexts, "passages":items}


def compact_source(source, *, include_links=False):
    view = {k:v for k,v in source.model_dump(mode="json").items() if k in {
        "id","url","final_url","title","status","author","published_at","updated_at","source_kind","error","truncated"}
        and v not in (None,"",False)}
    if source.status == "discovered":
        view["discovery_snippet"] = source.snippet
    acquisition = source.acquisition
    if acquisition.get("title"):
        view["observed_title"] = acquisition["title"]
    view["acquisition"] = {k:acquisition[k] for k in ("status","mode","captured_at","limitations","engine") if k in acquisition}
    selection = acquisition.get("selection")
    if selection:
        view["selection"] = {k:selection[k] for k in ("status","method","coverage","observation_sha256","group_count","selected_group_ids","omitted_group_ids","omitted_group_count","partial_group_ids","catalog","catalog_truncated") if k in selection}
        omitted = set(selection.get("omitted_group_ids",[])) | set(selection.get("partial_group_ids",[]))
        view["selection"]["catalog"] = [g for g in selection.get("catalog",[]) if g["id"] in omitted]
    if include_links:
        view["links"] = source.links
    else:
        view["observed_link_count"] = len(source.links)
    return view


def policy_view(state):
    """Prepare decision context while retaining claim citations and access state."""
    pinned = {e.passage_id for c in state.claims for e in c.evidence}
    passages = [p for p in state.passages if not p.review_only or p.id in pinned]
    return {"objective":state.objective, "questions":[q.model_dump(mode="json") for q in state.questions],
            "sources":[compact_source(s) for s in state.sources],
            **passage_view(passages),
            "claims":[c.model_dump(mode="json") for c in state.claims],
            "assessments":[{k:a[k] for k in ("claim_id","status","rationale","missing_evidence","origin_groups") if k in a}
                           for a in state.assessments],
            "assessment_error":state.assessment_error,
            "observations":[{"index":o.index,"tool":o.action.tool,"source_id":o.action.source_id,
                             "mode":o.action.mode,"focus":o.action.focus,"status":o.status,"error":o.data.get("error")}
                            for o in state.observations],
            "context_scope":{"review_only_passages_omitted":sum(p.review_only and p.id not in pinned for p in state.passages),
                             "partial_source_ids":[s.id for s in state.sources if s.acquisition.get("selection",{}).get("coverage")=="partial"]}}


def review_view(state, *, byte_limit=12000):
    """Build a bounded review from original sections, with an explicit scope ledger."""
    from .research import Passage
    from .research_acquisition import repository
    cited = {e.passage_id for c in state.claims for e in c.evidence}
    # Citation IDs already presented to the policy remain stable. Uncited policy
    # excerpts do not determine which original sections the reviewer inspects.
    packets = [p for p in state.passages if p.id in cited]
    sources, indexes, ledger = [], {}, {}
    for source in (s for s in state.sources if s.status == "read"):
        item = compact_source(source, include_links=True)
        item.pop("selection", None)
        item["observed_link_count"] = len(source.links)
        item["links"] = source.links[:24]
        item["links_omitted"] = max(0, len(source.links)-24)
        sources.append(item)
        ref = source.acquisition.get("blocks_artifact")
        if not ref:
            # Legacy readers have no independent block index. Their observed
            # passages remain available, with this weaker coverage stated.
            originals = [p for p in state.passages if p.source_id == source.id]
            packets.extend(p for p in originals if p.id not in cited)
            ledger[source.id] = {"coverage":"provided_passages_only", "selected_groups":[], "omitted_groups":0}
            continue
        raw = repository().get_artifact(ref["sha256"])
        if raw is None or hashlib.sha256(raw).hexdigest()!=ref["sha256"]:
            raise ValueError("Original source blocks are unavailable for independent review")
        document = json.loads(raw)
        originals = document.get("original_blocks") or document["blocks"]
        indexes[source.id] = (source, groups(originals,source.content_sha256))
        ledger[source.id] = {"coverage":"bounded_original_sections", "observation_sha256":source.content_sha256,
                             "selected_groups":[], "omitted_groups":len(indexes[source.id][1])}
    base = {"objective":state.objective,"questions":[q.model_dump(mode="json") for q in state.questions],
            "sources":sources,
            "claims":[c.model_dump(mode="json") for c in state.claims],
            "review_scope":"Inspect included original sections and exact citations. Omitted sections have not been reviewed; collection and source limitations still apply. A scoped finding does not establish page-wide absence or exhaustive coverage."}

    def view(items):
        return {**base, **passage_view(items), "inspection":{"byte_limit":byte_limit, "sources":ledger}}

    def fits(items):
        return len(json.dumps(view(items),ensure_ascii=False,separators=(",", ":")).encode()) + 64 <= byte_limit

    if not fits(packets):
        raise ValueError("Independent inspection limit exceeded by required citations or source metadata; refine the research scope")
    selected = set()

    def add(sid, index, *, required=False):
        nonlocal packets
        if (sid,index) in selected:
            return True
        source, sections = indexes[sid]
        section = sections[index]
        signatures = {(p.source_id,p.observation_sha256,p.text,tuple(p.context)) for p in packets}
        additions = []
        for block in section["blocks"]:
            key = (sid,source.content_sha256,block["text"],tuple(block.get("context",[])))
            if key not in signatures:
                additions.append(Passage(id=f"{sid}:review:{source.content_sha256[:12]}:{block['id']}",
                    source_id=sid,text=block["text"],kind=block["kind"],locator=block["locator"],
                    context=block.get("context",[]),observation_sha256=source.content_sha256,review_only=True))
                signatures.add(key)
        entry = ledger[sid]
        entry["selected_groups"].append(section["id"])
        entry["omitted_groups"] -= 1
        if not fits(packets+additions):
            entry["selected_groups"].pop()
            entry["omitted_groups"] += 1
            if required:
                raise ValueError("Independent inspection limit exceeded by a required original section; refine the research scope")
            return False
        packets += additions
        selected.add((sid,index))
        return True

    queries = [q.text + " " + q.evidence_needed for q in state.questions] + [c.text for c in state.claims]
    candidates = []
    for sid, (_, sections) in indexes.items():
        if not sections:
            raise ValueError("Independent inspection has no original sections for a read source")
        # Every read source contributes at least one independently ranked entry.
        # Cited entries are restored in full so their conditions cannot be cut.
        ranking = rank(" ".join(queries) or state.objective, sections)
        mandatory = {ranking[0][0]}
        for passage in (p for p in packets if p.id in cited and p.source_id == sid):
            if not any(passage.text in b["text"] for section in sections for b in section["blocks"]):
                raise ValueError("Cited passage cannot be restored from its original observation")
        for i, section in enumerate(sections):
            if any(p.source_id == sid and any(p.text in b["text"] for b in section["blocks"])
                   for p in packets if p.id in cited):
                mandatory.add(i)
        for i in sorted(mandatory):
            add(sid,i,required=True)
        # Search the complete index afresh per question and claim. Keep small
        # observations complete; long pages contribute relevant entries and
        # adjacent scope, rather than filling spare room with unrelated text.
        anchors = []
        for query in queries or [state.objective]:
            anchors.extend(i for i, score in rank(query,sections)[:2] if score > 0)
        small = sum(g["characters"] for g in sections) <= 8000
        order = list(dict.fromkeys(anchors + [j for i in sorted(mandatory | set(anchors))
            for j in (i-1,i+1) if 0 <= j < len(sections)] + (list(range(len(sections))) if small else [])))
        candidates.append((sid,order))
    # Round-robin optional sections prevents the first long source consuming
    # all remaining inspection space before another source's counterevidence.
    for offset in range(max((len(order) for _,order in candidates),default=0)):
        for sid,order in candidates:
            if offset < len(order):
                add(sid,order[offset])
    for entry in ledger.values():
        if entry["coverage"] == "bounded_original_sections" and not entry["omitted_groups"]:
            entry["coverage"] = "complete_original_sections"
    result = view(packets)
    result["inspection"]["serialized_bytes"] = 0
    for _ in range(3):
        result["inspection"]["serialized_bytes"] = len(json.dumps(result,ensure_ascii=False,separators=(",", ":")).encode())
    if result["inspection"]["serialized_bytes"] > byte_limit:
        raise ValueError("Independent inspection metadata exceeds the inspection limit")
    known = {p.id for p in state.passages}
    return result, [p for p in packets if p.id not in known]
