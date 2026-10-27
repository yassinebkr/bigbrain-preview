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


class InspectionBudgetExceeded(ValueError):
    """Required evidence exceeds the requested serialized inspection size."""


def words(text):
    """Tokenize Unicode words, identifiers and camel-case names for local ranking."""
    # CLI options are case-sensitive symbols: -u and -U differ, and -a
    # must retain its dash rather than matching an ordinary prose article.
    option = r"(?<![\w-])--?[A-Za-z][A-Za-z0-9_-]*"
    symbols = ['option:' + match.group() for match in re.finditer(option, text)]
    prose = re.sub(option, ' ', text)
    expanded = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", prose)
    return symbols + re.findall(r"[^\W_]+", expanded.casefold(), re.UNICODE)


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
        fingerprint = json.dumps([section["context"], [(b.get("id"), b.get("kind"), b["text"]) for b in section["blocks"]]],ensure_ascii=False)
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


def contextual_rerank(question, sections, shortlist=8):
    """Rerank a bounded lexical shortlist using observed headings and exact phrases.

    This local comparison candidate is not a semantic model. It neither changes
    source text nor infers reliability from a domain or a vocabulary shortcut.
    """
    initial = rank(question, sections)
    query = set(words(question))
    rescored = []
    for position, score in initial[:shortlist]:
        heading = " ".join(sections[position].get("context", []))
        heading_overlap = len(query.intersection(words(heading))) / max(1, len(query))
        rescored.append((position, score * (1 + heading_overlap)))
    return sorted(rescored, key=lambda item: (-item[1], item[0])) + initial[shortlist:]


def select(question, blocks, observation, *, limit=6000, requested=(), preferred_ids=None, ranking="bm25"):
    """Select curated section blocks or explicitly requested original sections."""
    sections = groups(blocks,observation)
    all_characters = len("\n".join(b["text"] for g in sections for b in g["blocks"]))
    # Main-text extraction supplies decision candidates. Original sections keep
    # their identities and remain fully readable through explicit section IDs.
    candidates = [{**g,"blocks":[b for b in g["blocks"] if preferred_ids is None or b["id"] in preferred_ids]}
                  for g in sections]
    candidate_size = len("\n".join(b["text"] for g in candidates for b in g["blocks"]))
    if ranking not in {"bm25", "contextual"}:
        raise ValueError("Unknown section ranking method")
    ranked = contextual_rerank(question,candidates) if ranking == "contextual" else rank(question,candidates)
    chosen, oversized = set(), []
    method = "local-contextual-shortlist" if ranking == "contextual" else "local-bm25-sections"
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
                # A large neighbour can exceed the packet while the complete
                # matching section still fits. Keep its internal conditions
                # together and expose adjacent omissions in the scope ledger.
                tentative = chosen | {anchor}
                cost = len("\n".join(b["text"] for i in sorted(tentative) for b in candidates[i]["blocks"]))
                if cost <= limit and candidates[anchor]["blocks"]:
                    chosen = tentative
                else:
                    oversized.append(sections[anchor]["id"])
    chosen_sections = sections if requested else candidates
    partial = [sections[i]["id"] for i in sorted(chosen) if len(chosen_sections[i]["blocks"]) < len(sections[i]["blocks"])]
    selected = [dict(b,clipped=False,block_start=0,block_end=len(b["text"]))
                for i in sorted(chosen) for b in chosen_sections[i]["blocks"]]
    size = len("\n".join(b["text"] for b in selected))
    needs_context = not selected or size > limit
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
    if acquisition.get('navigation'):
        navigation = acquisition['navigation']
        view['navigation'] = {'observation_sha256':navigation['observation_sha256'],
            'sections':[[item['id'], item['context'][-1][:100] if item['context'] else 'Document preamble']
                        for item in navigation['catalog'][:48]],
            'omitted_groups':navigation.get('omitted_groups',0)+max(0,len(navigation['catalog'])-48)}
    if acquisition.get("title"):
        view["observed_title"] = acquisition["title"]
    view["acquisition"] = {k:acquisition[k] for k in ("status","mode","captured_at","limitations","engine") if k in acquisition}
    selection = acquisition.get("selection")
    if selection:
        view["selection"] = {k:selection[k] for k in ("status","method","coverage","observation_sha256","group_count","selected_group_ids","omitted_group_ids","omitted_group_count","partial_group_ids","catalog","catalog_truncated") if k in selection}
        omitted = set(selection.get("omitted_group_ids",[])) | set(selection.get("partial_group_ids",[]))
        view["selection"]["catalog"] = [g for g in selection.get("catalog",[]) if g["id"] in omitted]
        if view.get('navigation'):
            view['selection'].pop('catalog', None)
            view['selection'].pop('omitted_group_ids', None)
    if include_links:
        view["links"] = source.links
    else:
        view["observed_link_count"] = len(source.links)
    return view


def policy_view(state, *, byte_limit=18000):
    """Prepare decision context while retaining claim citations and access state."""
    pinned = {e.passage_id for c in state.claims for e in c.evidence}
    passages = [p for p in state.passages if not p.review_only or p.id in pinned]
    view = {"objective":state.objective, "delivery_mode":state.delivery_mode, "scope_locked":state.scope_locked,
            "review_reason":state.review_reason, "questions":[q.model_dump(mode="json") for q in state.questions],
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
    # Bound navigation/history independently from evidence. No observed text is
    # rewritten or clipped to make a prompt fit; omitted passages remain stored.
    for source in view["sources"]:
        if "discovery_snippet" in source:
            source["discovery_snippet"] = source["discovery_snippet"][:150]
        selection = source.get("selection", {})
        if "catalog" in selection:
            selection["catalog_omitted"] = max(0, len(selection["catalog"]) - 8)
            selection["catalog"] = selection["catalog"][:8]
    view["observations_omitted"] = max(0, len(view["observations"]) - 8)
    view["observations"] = view["observations"][-8:]
    def size():
        return len(json.dumps(view, ensure_ascii=False, separators=(",", ":")).encode())
    if size() <= byte_limit:
        return view
    # Preserve complete heading packets so a qualifier is not separated from
    # its claim. Pinned citations always win; oversized packets fail explicitly.
    packets = {}
    for passage in passages:
        key = (passage.source_id, passage.observation_sha256, tuple(passage.context))
        packets.setdefault(key, []).append(passage)
    chosen = [p for packet in packets.values() if any(p.id in pinned for p in packet) for p in packet]
    selected_ids = {p.id for p in chosen}
    view.update(passage_view(chosen))
    view["context_scope"]["decision_omitted_passage_ids"] = [p.id for p in passages if p.id not in selected_ids]
    if size() > byte_limit:
        raise InspectionBudgetExceeded("Decision context cannot fit required citations/metadata; refine research scope")
    candidates = [(key, packet) for key, packet in packets.items() if not any(p.id in selected_ids for p in packet)]
    sections = [{"blocks": [{"text": p.text} for p in packet]} for _, packet in candidates]
    objective = " ".join(q.text + " " + q.evidence_needed for q in state.questions)
    # Literal focuses express the policy's retrieval intent in the source's
    # language. Preserve that signal when the user's question uses another one.
    focuses = {}
    for observation in state.observations + state.pending_observations:
        items = observation.data.get('items', []) if observation.action.tool == 'batch' else [observation.model_dump()]
        for item in items:
            focus = item['action'].get('focus')
            source_id = (item['data'].get('source') or {}).get('id') or item['action'].get('source_id')
            if item['status'] == 'ok' and focus and source_id:
                focuses.setdefault(source_id, []).append(focus)
    ordering = rank(objective, sections)
    first_by_source = []
    for source in state.sources:
        positions = [i for i, (key, _) in enumerate(candidates) if key[0] == source.id]
        if positions:
            local = rank(objective + ' ' + ' '.join(focuses.get(source.id, [])),
                         [sections[i] for i in positions])
            local.sort(key=lambda item: (
                -int(any(focus.casefold() in ' '.join(candidates[positions[item[0]]][0][2]).casefold()
                         for focus in focuses.get(source.id, []))), -item[1], item[0]))
            first_by_source.append((positions[local[0][0]], local[0][1]))
    # Give each consulted source a complete packet before filling spare space.
    # Repeated vocabulary in one page must not displace every other source.
    first_ids = {i for i, _ in first_by_source}
    ordering = first_by_source + [item for item in ordering if item[0] not in first_ids]
    for position, _ in ordering:
        packet = candidates[position][1]
        previous = list(chosen)
        chosen.extend(packet)
        ids = {p.id for p in chosen}
        view.update(passage_view(chosen))
        view["context_scope"]["decision_omitted_passage_ids"] = [p.id for p in passages if p.id not in ids]
        if size() > byte_limit:
            chosen = previous
    selected_ids = {p.id for p in chosen}
    view.update(passage_view(chosen))
    view["context_scope"]["decision_omitted_passage_ids"] = [p.id for p in passages if p.id not in selected_ids]
    return view


def review_view(state, *, byte_limit=None):
    """Build a bounded review from original sections, with an explicit scope ledger."""
    adaptive = byte_limit is None
    byte_limit = 12000 if adaptive else byte_limit
    from .research import Passage
    from .research_acquisition import repository
    def matches(passage, block):
        # Capture identity is checked by the caller. Modern observations retain
        # exact block coordinates; legacy observations require heading identity.
        if passage.block_id is not None:
            end = passage.block_end if passage.block_end is not None else passage.block_start + len(passage.text)
            return (passage.block_id == block['id']
                    and 0 <= passage.block_start <= end <= len(block['text'])
                    and block['text'][passage.block_start:end] == passage.text)
        return (tuple(passage.context) == tuple(block.get('context', []))
                and passage.text in block['text'])
    cited = {e.passage_id for c in state.claims for e in c.evidence}
    # Preserve the consulted evidence, including qualifications outside the
    # draft's citation links. The original section index supplies independent
    # context and counterevidence below.
    packets = [p for p in state.passages if not p.review_only or p.id in cited]
    sources, indexes, ledger = [], {}, {}
    for source in (s for s in state.sources if s.status == "read"):
        item = compact_source(source, include_links=True)
        item.pop("selection", None)
        item.pop("navigation", None)
        item["observed_link_count"] = len(source.links)
        item["links"] = source.links[:8]
        item["links_omitted"] = max(0, len(source.links)-8)
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
    # Uncited consultations still need alignment to the original observation.
    # Policy-only metadata cannot become independent source evidence.
    known_sources = {source['id'] for source in sources}
    packets = [p for p in packets if p.id in cited or p.source_id in known_sources and (
        p.source_id not in indexes or p.observation_sha256 == indexes[p.source_id][0].content_sha256
        and any(matches(p, block) for section in indexes[p.source_id][1] for block in section['blocks']))]
    base = {"objective":state.objective,"questions":[q.model_dump(mode="json") for q in state.questions],
            "sources":sources,
            "claims":[c.model_dump(mode="json") for c in state.claims],
            "review_scope":"Inspect included original sections and exact citations. Omitted sections have not been reviewed; collection and source limitations still apply. A scoped finding does not establish page-wide absence or exhaustive coverage."}

    def view(items):
        return {**base, **passage_view(items), "inspection":{"byte_limit":byte_limit, "sources":ledger}}

    def fits(items, *, required=False):
        nonlocal byte_limit
        needed = len(json.dumps(view(items),ensure_ascii=False,separators=(",", ":")).encode()) + 64
        if adaptive and required and byte_limit < needed <= 24000:
            byte_limit = min(24000, ((needed + 1023)//1024)*1024)
        return needed <= byte_limit

    if not fits(packets, required=True):
        raise InspectionBudgetExceeded("Independent inspection limit exceeded by required citations or source metadata; refine the research scope")
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
                    context=block.get("context",[]),observation_sha256=source.content_sha256,review_only=True,
                    block_id=block['id'],block_start=0,block_end=len(block['text'])))
                signatures.add(key)
        entry = ledger[sid]
        entry["selected_groups"].append(section["id"])
        entry["omitted_groups"] -= 1
        if not fits(packets+additions, required=required):
            entry["selected_groups"].pop()
            entry["omitted_groups"] += 1
            if required:
                raise InspectionBudgetExceeded("Independent inspection limit exceeded by a required original section; refine the research scope")
            return False
        packets += additions
        selected.add((sid,index))
        return True

    question_queries = [q.text + " " + q.evidence_needed for q in state.questions]
    queries = question_queries + [c.text for c in state.claims]
    candidates = []
    for sid, (_, sections) in indexes.items():
        if not sections:
            raise ValueError("Independent inspection has no original sections for a read source")
        # Restore consulted entries in full, then inspect additional sections
        # independently. A source with no retained excerpts still gets a section.
        ranking = rank(" ".join(question_queries) or state.objective, sections)
        mandatory = set()
        for passage in (p for p in packets if p.id in cited and p.source_id == sid):
            if not any(matches(passage, b) for section in sections for b in section["blocks"]):
                raise ValueError("Cited passage cannot be restored from its original observation")
        for i, section in enumerate(sections):
            if any(p.source_id == sid and any(matches(p, b) for b in section["blocks"])
                   for p in packets):
                mandatory.add(i)
        if not mandatory:
            mandatory.add(ranking[0][0])
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
        raise InspectionBudgetExceeded("Independent inspection metadata exceeds the inspection limit")
    known = {p.id for p in state.passages}
    return result, [p for p in packets if p.id not in known]
