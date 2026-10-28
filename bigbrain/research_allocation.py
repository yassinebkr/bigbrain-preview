"""Structural evidence bundles and balanced candidate queues for research reads."""
from __future__ import annotations

from .research_context import rank, words


def bundles(items, *, character_limit=1800):
    """Keep contiguous section blocks together within a bounded candidate unit.

    Inputs retain source order and immutable passage IDs. A large block stays
    whole so a later explicit character-window read can expose it safely.
    Section identity includes source and capture to prevent cross-page blending.
    """
    result, current, identity, characters = [], [], None, 0
    for item in items:
        key = (item.get('source_id'), item.get('capture_sha256'), tuple(item.get('context', [])))
        size = len(item['text']) + 1
        if current and (key != identity or characters + size > character_limit):
            result.append({'context': list(identity[2]), 'blocks': current})
            current, characters = [], 0
        identity = key
        current.append(item)
        characters += size
    if current:
        result.append({'context': list(identity[2]), 'blocks': current})
    return result


def candidate_queues(requirements, units, *, granularity='block'):
    """Rank independently per observed requirement and retain source ownership.

    The queues express retrieval relevance. Semantic support is assessed after
    reading. Each requirement can optionally bind a source-language reading
    intent to its observed source; other sources remain separate candidates.
    """
    if granularity not in {'block', 'section'}:
        raise ValueError('Unknown research candidate granularity')
    queues = []
    for requirement in requirements:
        eligible = [i for i, unit in enumerate(units) if not requirement.get('source_id')
                    or unit['blocks'][0].get('source_id') == requirement['source_id']]
        if granularity == 'section':
            queues.append([eligible[i] for i, score in rank(requirement['text'], [units[i] for i in eligible])
                           if score > 0])
            continue
        # A section's repeated labels can overwhelm a short definition. Score
        # its strongest substantive block, then admit that block's whole bundle.
        blocks = [(i, b) for i in eligible for b in units[i]['blocks']]
        scored = rank(requirement['text'], [{'blocks': [b]} for _, b in blocks])
        has_body = any(b.get('kind') in {'p', 'dt', 'code', 'li', 'table_row', 'plain_text'} for _, b in blocks)
        best = {}
        for position, value in scored:
            index, block = blocks[position]
            if has_body and block.get('kind') not in {'p', 'dt', 'code', 'li', 'table_row', 'plain_text'}:
                continue
            value *= min(1, len(words(block['text'])) / 20)
            if value > 0:
                best[index] = max(best.get(index, 0), value)
        weighted = list(best.items())
        queues.append([i for i, _ in sorted(weighted, key=lambda item: -item[1])])
    return queues


def interleave(queues):
    """Visit one candidate per requirement before considering its next choice."""
    seen = set()
    for depth in range(max(map(len, queues), default=0)):
        for queue in queues:
            if depth < len(queue) and queue[depth] not in seen:
                seen.add(queue[depth])
                yield queue[depth]
