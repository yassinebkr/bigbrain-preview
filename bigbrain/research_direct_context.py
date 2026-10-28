"""Immutable observed passages and bounded working context for direct research."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .research_quotes import anchor_quote
from .research_context import rank, words
from .research_allocation import bundles, candidate_queues, interleave


def encoded(value):
    """Serialize wire packets canonically and measure actual UTF-8 bytes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


class WorkingContextOverflow(ValueError):
    """The fixed request and ledger exceed the admitted working context."""


@dataclass(frozen=True)
class Receipt:
    passage_id: str
    source_id: str
    url: str
    capture_sha256: str
    text: str
    kind: str
    context: tuple[str, ...]
    locator: str | None
    clipped: bool
    block_id: str | None
    block_start: int
    block_end: int | None

    @property
    def identity(self):
        return hashlib.sha256(encoded(self.__dict__)).hexdigest()


class ObservedPassages:
    """Retain trusted runtime observations independently of prompt eviction.

    Source capture hashes come from the acquisition boundary. This class checks
    passage ownership against those hashes; it does not recapture remote pages.
    """

    def __init__(self, *, require_exposure=False):
        self.receipts: dict[str, Receipt] = {}
        self.current: dict[str, str] = {}
        self.capture_slots: dict[tuple[str, str], str] = {}
        self.require_exposure = require_exposure
        self.exposed: dict[str, list[tuple[int, int]]] = {}

    def expose(self, packet):
        """Record exact windows submitted to inference, excluding catalog entries.

        Packet construction also occurs for forecasts. Call this method only at
        the inference boundary, after admission selects the actual packet.
        """
        pending = []
        for passage in packet['working_set']['passages']:
            receipt = self.get(passage['id'])
            left, right = passage['view_start'], passage['view_end']
            if (type(left) is not int or type(right) is not int
                    or not 0 <= left < right <= len(receipt.text)
                    or passage['text'] != receipt.text[left:right]):
                raise ValueError('Exposure must match an original passage window')
            pending.append((receipt.identity, (left, right)))
        for identity, window in pending:
            windows = self.exposed.setdefault(identity, [])
            if window not in windows:
                windows.append(window)

    def ingest(self, state):
        sources = {s.id: s for s in state.sources if s.status == 'read' and s.content_sha256}
        current = {}
        # Validate the whole batch before altering the current capture pointers.
        pending = {}
        slots = {}
        for passage in state.passages:
            source = sources.get(passage.source_id)
            if source is None or passage.observation_sha256 != source.content_sha256:
                continue
            receipt = Receipt(passage.id, source.id, source.final_url or source.url,
                source.content_sha256, passage.text, passage.kind, tuple(passage.context), passage.locator,
                passage.clipped, passage.block_id, passage.block_start, passage.block_end)
            previous = self.receipts.get(receipt.identity)
            if previous is not None and previous != receipt:
                raise ValueError('Observed receipt identity collision')
            if passage.id in current and current[passage.id] != receipt.identity:
                raise ValueError('A passage ID identifies multiple current observations')
            slot = (passage.id, receipt.capture_sha256)
            if slot in self.capture_slots and self.capture_slots[slot] != receipt.identity:
                raise ValueError('A captured passage was rewritten under the same identity')
            current[passage.id] = receipt.identity
            pending[receipt.identity] = receipt
            slots[slot] = receipt.identity
        self.receipts.update(pending)
        self.capture_slots.update(slots)
        self.current = current

    def get(self, passage_id):
        try:
            return self.receipts[self.current[passage_id]]
        except KeyError as exc:
            raise ValueError('Passage has no current observed receipt') from exc

    def citation(self, passage_id, capture_sha256, quote, *, receipt_id, start=None, end=None):
        """Check exact evidence identity and quote independently of semantic support."""
        receipt = self.get(passage_id)
        if receipt.capture_sha256 != capture_sha256 or receipt.identity != receipt_id:
            raise ValueError('Citation references a stale observation')
        literal, start, end = anchor_quote(receipt.text, quote, start, end)
        if self.require_exposure and not any(left <= start < end <= right
                for left, right in self.exposed.get(receipt.identity, [])):
            raise ValueError('Citation requires a model-exposed passage window')
        return {'passage_id': passage_id, 'receipt_id': receipt.identity,
                'capture_sha256': capture_sha256, 'quote': literal, 'start': start, 'end': end,
                'citation_integrity': 'verified', 'semantic_assessment': 'model_judgment'}

    def retained_views(self, state):
        """Re-expose verified prior quotations and nearby qualification blocks.

        Views retain their original offsets. A refreshed or missing receipt drops
        its old quotation from this preference list. The full archive stays
        available independently of this bounded continuity allowance.
        """
        views, neighbours, characters = {}, {}, 0
        for finding in state.usage.get('direct_result', {}).get('findings', []):
            for citation in finding.get('citations', []):
                pid = citation.get('passage_id')
                if pid not in self.current or pid in views:
                    continue
                receipt = self.get(pid)
                if (citation.get('receipt_id') != receipt.identity
                        or citation.get('capture_sha256') != receipt.capture_sha256):
                    continue
                try:
                    _, start, end = anchor_quote(receipt.text, citation['quote'],
                                                 citation.get('start'), citation.get('end'))
                except (ValueError, KeyError):
                    continue
                left, right = (0, len(receipt.text)) if len(receipt.text) <= 800 else (
                    max(0, start - 100), min(len(receipt.text), end + 100))
                if characters + right - left > 3200:
                    continue
                views[pid] = (left, right)
                characters += right - left
                # Capture order and heading ownership provide local context.
                # Aliased consultations share the same original block identity.
                same = []
                seen = set()
                for other_id in self.current:
                    other = self.get(other_id)
                    key = (other.block_id, other.text)
                    if (other.source_id == receipt.source_id and other.context == receipt.context
                            and key not in seen):
                        same.append(other_id)
                        seen.add(key)
                position = next((i for i, other_id in enumerate(same)
                                 if self.get(other_id).block_id == receipt.block_id
                                 and self.get(other_id).text == receipt.text), None)
                if position is not None:
                    for index in (position - 1, position + 1):
                        if 0 <= index < len(same):
                            other = self.get(same[index])
                            if other.kind in {'p', 'text', 'plain_text'} and len(other.text) <= 1000:
                                neighbours.setdefault(same[index], (0, len(other.text)))
        for pid, view in list(neighbours.items())[:4]:
            if pid not in views and characters + view[1] <= 4200:
                views[pid] = view
                characters += view[1]
        return views

    def packet(self, state, *, preferred=(), windows=(), byte_limit=12000,
               catalog_source_id=None, catalog_offset=0, compact=False):
        """Fit complete observed passages alongside a compact source ledger.

        Each omitted passage remains identifiable for a targeted read. The
        catalog is paged separately when it cannot fit alongside the working set.
        Selected excerpts disclose whether sibling context remains outside view.
        """
        sources = [{'id': s.id, 'url': s.final_url or s.url, 'status': s.status,
                    **({'capture_sha256': s.content_sha256,
                        'captured_at': s.acquisition.get('captured_at') or s.consulted_at,
                        'selection_incomplete': s.truncated} if s.status == 'read' else {}),
                    **({'error': s.error} if s.error else {})} for s in state.sources]
        packet = {'objective': state.original_request or state.objective,
                  'questions': [{'id': q.id, 'text': q.text} for q in state.questions],
                  'sources': sources, 'passages': [], 'catalog': [],
                  'omitted_passages': len(self.current), 'catalog_omitted': len(self.current),
                  'coverage': 'selected_observations'}
        if state.previous_attempts or state.usage.get('direct_result'):
            packet['remaining_requirements'] = [
                {'question_id': item['question_id'], 'missing_evidence': item.get('missing_evidence', [])}
                for item in state.question_coverage if item.get('status') != 'covered']
            packet['original_request_gaps'] = state.original_request_coverage.get('gaps', [])
            packet['prior_findings'] = [{'id': claim.id, 'question_id': claim.question_id,
                'status': claim.status, 'text': claim.text[:240], 'text_clipped': len(claim.text) > 240}
                for claim in state.claims[:4]]
            packet['prior_findings_omitted'] = max(0, len(state.claims) - 4)
        self.feedback(packet, state, byte_limit, catalog_source_id, catalog_offset)
        if len(encoded(packet)) > byte_limit:
            raise WorkingContextOverflow('Fixed objective and source ledger exceed working context')
        views = self.retained_views(state)
        explicit = []
        for passage_id, start, end in windows:
            receipt = self.get(passage_id)
            if (type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(receipt.text)):
                raise ValueError('Requested view must identify an original character range')
            if passage_id in explicit:
                raise ValueError('One working view per passage can be selected per decision')
            views[passage_id] = (start, end)
            explicit.append(passage_id)
        # Explicit inspection choices remain ahead of automatic continuity.
        views = {**{pid: views[pid] for pid in explicit}, **views}
        newest = list(reversed(self.current))
        candidates = [{'blocks': [{'text': self.get(pid).text}],
                       'context': list(self.get(pid).context)} for pid in newest]
        query = ' '.join([state.original_request or state.objective, *[q.text for q in state.questions]])
        # Source-language read intents are model proposals for retrieval only.
        # The immutable user questions remain the conclusion coverage contract.
        intents = [request.reading_question for observation in state.observations
                   for request in (observation.action.requests if observation.action.tool == 'batch'
                                   else [observation.action]) if request.reading_question]
        query += ' ' + ' '.join(dict.fromkeys(intents))
        # Short navigation labels often repeat all query symbols. Prefer actual
        # explanatory blocks while retaining every block in the local catalog.
        scores = [(position, score * min(1, len(words(self.get(newest[position]).text)) / 20))
                  for position, score in rank(query, candidates)]
        ranked = [newest[position] for position, _ in sorted(scores, key=lambda item: -item[1])]
        # Keep a provenance candidate for each observed source before spending
        # the remaining packet on higher-scoring blocks from a single page.
        first_per_source = {}
        for pid in ranked:
            first_per_source.setdefault(self.get(pid).source_id, pid)
        ids = list(dict.fromkeys([*views, *preferred, *first_per_source.values(), *ranked]))
        unique, seen_content = [], set()
        for pid in ids:
            receipt = self.get(pid)
            start, end = views.get(pid, (0, len(receipt.text)))
            key = (receipt.source_id, receipt.capture_sha256, receipt.context,
                   receipt.text[start:end], start, end, receipt.clipped)
            if key not in seen_content:
                unique.append(pid)
                seen_content.add(key)
        packet['duplicate_passages'] = len(ids) - len(unique)
        ids = unique
        for passage_id in ids:
            self.get(passage_id)
        # Retrieval lanes preserve individual questions and source-bound reading
        # intents. They describe candidate visibility, leaving semantic coverage
        # to the conclusion validator and the source-reading model.
        requirements = [{'id': q.id, 'text': q.text} for q in state.questions]
        source_intents = {}
        from urllib.parse import urldefrag
        for observation in state.observations:
            requests = observation.action.requests if observation.action.tool == 'batch' else [observation.action]
            for request in requests:
                if not request.reading_question:
                    continue
                source_ids = [s.id for s in state.sources if s.id == request.source_id or
                    request.url and urldefrag(request.url)[0] in {urldefrag(s.url)[0], urldefrag(s.final_url or s.url)[0]}]
                for sid in source_ids:
                    # A new read refines the active inspection for this source.
                    # Repeating all previous intents dilutes the requested gap
                    # and keeps admitting the same early-page evidence.
                    key = (request.question_id, sid)
                    source_intents.pop(key, None)
                    source_intents[key] = request.reading_question
        targeted = [{'id': f'{qid}@{sid}', 'source_id': sid, 'text': intent}
                    for (qid, sid), intent in reversed(source_intents.items())]
        # Newly acquired sources need an inspection opportunity before repeated
        # reads from sources already visible in the native conversation. This
        # priority uses exposure receipts, with semantic support left to inference.
        exposed_sources = {self.get(pid).source_id for pid in self.current
                           if self.exposed.get(self.get(pid).identity)}
        targeted.sort(key=lambda lane: lane['source_id'] in exposed_sources)
        requirements = targeted + requirements
        # Canonical source order restores adjacent paragraphs after ranking and
        # deduplication. Missing original block IDs retain their capture order.
        position = {pid: i for i, pid in enumerate(self.current)}
        def source_order(pid):
            receipt = self.get(pid)
            block = receipt.block_id or ''
            index = int(block[1:]) if block.startswith('b') and block[1:].isdigit() else position[pid]
            return receipt.source_id, receipt.capture_sha256, index
        structural = [{'id': pid, 'text': self.get(pid).text, 'source_id': self.get(pid).source_id,
            'capture_sha256': self.get(pid).capture_sha256, 'context': list(self.get(pid).context),
            'kind': self.get(pid).kind}
            for pid in sorted(ids, key=source_order)]
        units = bundles(structural)
        queues = candidate_queues(requirements, units)
        packet['evidence_allocation'] = [{'id': requirement['id'], 'selection': 'candidates_visible'}
                                          for requirement in requirements]
        if len(encoded(packet)) > byte_limit:
            raise WorkingContextOverflow('Question allocation ledger exceeds working context')
        groups = {}
        for passage_id in ids:
            receipt = self.get(passage_id)
            groups.setdefault((receipt.source_id, receipt.context), set()).add(passage_id)
        selected = set()
        # Count fields use fixed upper bounds while fitting, keeping later size
        # corrections from growing the serialized packet beyond its ceiling.
        def item_for(passage_id):
            receipt = self.get(passage_id)
            start, end = views.get(passage_id, (0, len(receipt.text)))
            return {'id': passage_id, 'source_id': receipt.source_id,
                    **({} if compact else {'receipt_id': receipt.identity, 'capture_sha256': receipt.capture_sha256}),
                    'text': receipt.text[start:end], 'headings': list(receipt.context),
                    'view_start': start, 'view_end': end, 'view_complete': start == 0 and end == len(receipt.text),
                    'original_characters': len(receipt.text), 'kind': receipt.kind,
                    'clipped': receipt.clipped, 'sibling_context_omitted': True}
        admitted = []
        def admit(bundle):
            fresh = [pid for pid in bundle if pid not in selected]
            if not fresh:
                return
            start = len(packet['passages'])
            packet['passages'].extend(item_for(pid) for pid in fresh)
            if len(encoded(packet)) > byte_limit:
                del packet['passages'][start:]
            else:
                selected.update(fresh)
                admitted.append(fresh)
        # Explicit windows and verified continuity remain authoritative. Every
        # subsequent structural bundle is admitted atomically so its local
        # qualifications survive byte fitting together with the primary text.
        for pid in dict.fromkeys([*views, *preferred]):
            admit([pid])
        for index in interleave(queues):
            admit([block['id'] for block in units[index]['blocks']])
        # Unmatched observations remain available when spare capacity permits.
        # This fallback uses the same structural admission boundary.
        queued = {i for queue in queues for i in queue}
        for index, unit in enumerate(units):
            if index not in queued:
                admit([block['id'] for block in unit['blocks']])
        packet['omitted_passages'] = len(ids) - len(selected)
        for item in packet['passages']:
            receipt = self.get(item['id'])
            item['sibling_context_omitted'] = bool(groups[(receipt.source_id, receipt.context)] - selected)
        # False is one byte longer than true; retry fitting after final flags.
        while len(encoded(packet)) > byte_limit and packet['passages']:
            removed = admitted.pop()
            packet['passages'] = [p for p in packet['passages'] if p['id'] not in removed]
            selected.difference_update(removed)
            packet['omitted_passages'] += len(removed)
            for item in packet['passages']:
                receipt = self.get(item['id'])
                item['sibling_context_omitted'] = bool(groups[(receipt.source_id, receipt.context)] - selected)
        for row, queue in zip(packet['evidence_allocation'], queues):
            row['selection'] = ('no_match' if not queue else 'candidates_visible' if any(
                all(block['id'] in selected for block in units[index]['blocks']) for index in queue)
                else 'budget_blocked')
        omitted = [self.get(pid) for pid in ids if pid not in selected]
        packet['catalog_omitted'] = len(omitted)
        for receipt in omitted:
            item = {'id': receipt.passage_id, 'source_id': receipt.source_id,
                    'text_bytes': len(receipt.text.encode()), 'receipt_id': receipt.identity,
                    'text_characters': len(receipt.text),
                    'headings': list(receipt.context)}
            packet['catalog'].append(item)
            if len(encoded(packet)) > byte_limit:
                packet['catalog'].pop()
                break
            packet['catalog_omitted'] -= 1
        assert len(encoded(packet)) <= byte_limit
        return packet

    @staticmethod
    def feedback(packet, state, byte_limit, source_id, offset):
        """Reserve bounded action feedback and observed section navigation."""
        if type(offset) is not int or offset < 0:
            raise ValueError('Catalog offset must be a nonnegative integer')
        if source_id is not None and source_id not in {s.id for s in state.sources}:
            raise ValueError('Catalog source must be observed')
        items = []
        for observation in state.observations:
            children = observation.data.get('items', []) if observation.action.tool == 'batch' else []
            items.extend(children)
            if not children or observation.status == 'error':
                items.append(observation.model_dump(mode='json'))
        recent = items[-4:]
        # Recent failures precede successes so recovery instructions survive a
        # tight packet; omitted feedback remains counted explicitly.
        recent.sort(key=lambda item: item['status'] != 'error')
        catalogs = []
        for source in state.sources:
            navigation = source.acquisition.get('navigation', {})
            digest = navigation.get('observation_sha256')
            if digest != source.content_sha256 or not digest:
                continue
            if source_id is not None and source.id != source_id:
                continue
            catalogs.append([{'source_id': source.id, 'capture_sha256': digest,
                'group_id': group['id'], 'headings': group.get('context', []),
                'characters': group.get('characters', 0)} for group in navigation.get('catalog', [])])
        ordered = [catalog[i] for i in range(max(map(len, catalogs), default=0))
                   for catalog in catalogs if i < len(catalog)]
        if offset > len(ordered):
            raise ValueError('Catalog offset exceeds the observed section catalog')
        packet.update(recent_actions=[], recent_actions_omitted=len(recent), navigation=[],
            navigation_omitted=len(ordered)-offset, catalog_source_id=source_id, catalog_offset=offset)
        fixed = len(encoded(packet))
        # Keep auxiliary navigation proportional to the remaining evidence space.
        allowance = min(1600, max(0, byte_limit-fixed)//4, byte_limit//5)
        for item in recent:
            action = item['action']
            entry = {key: action[key] for key in ('tool', 'source_id', 'focus', 'group_ids') if action.get(key)}
            entry.update(status=item['status'], error=str(item['data'].get('error', ''))[:250])
            if action.get('url'):
                entry['url'] = action['url'][:250]
            packet['recent_actions'].append(entry)
            if len(encoded(packet))-fixed > min(1000, allowance):
                packet['recent_actions'].pop()
                break
            packet['recent_actions_omitted'] -= 1
        for entry in ordered[offset:]:
            packet['navigation'].append(entry)
            if len(encoded(packet))-fixed > allowance:
                packet['navigation'].pop()
                break
            packet['navigation_omitted'] -= 1
