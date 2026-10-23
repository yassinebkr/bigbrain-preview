"""Runtime facts for a maintenance run, never an LLM-authored memory summary."""
from __future__ import annotations


class MaintenanceState:
    def __init__(self, inventory):
        self.inventory = list(inventory)
        self.reads = {}
        self.diagnostics = []
        self.blockers = {}
        self.source_epoch = 0
        self.reproduced = False
        self.environment = None
        self.phase = 'diagnosing'
        self.verification_disposition = None

    def read(self, result, observation_id):
        path, version = result['path'], result['sha256']
        previous = self.reads.get(path)
        if previous and not previous['stale'] and previous['sha256'] != version:
            self.source_epoch += 1  # a fresh read observed an external revision
        if previous is None or previous['sha256'] != version or previous['stale']:
            previous = {'path': path, 'sha256': version, 'total_lines': result['total_lines'],
                        'ranges': [], 'observation_ids': [], 'stale': False}
            self.reads[path] = previous
        count = len(result['content'].splitlines())
        if count:
            ranges = sorted(previous['ranges'] + [[result['start'], result['start'] + count - 1]])
            merged = []
            for start, end in ranges:
                if merged and start <= merged[-1][1] + 1:
                    merged[-1][1] = max(merged[-1][1], end)
                else:
                    merged.append([start, end])
            previous['ranges'] = merged
        previous['observation_ids'].append(observation_id)
        previous['observation_ids'] = previous['observation_ids'][-8:]

    def changed(self, path):
        self.source_epoch += 1
        if path not in self.inventory:
            self.inventory.append(path)
            self.inventory.sort()
        if path in self.reads:
            self.reads[path]['stale'] = True

    def observe(self, kind, action, result, observation_id):
        """Only executed tool results change facts; notebook text has no authority."""
        path, status = action.get('path'), result.get('status')
        key = (kind, path)
        if status == 'tool_error':
            self.blockers[key] = {'action': kind, 'path': path, 'status': status,
                'code': result.get('code'),
                'reason': str(result.get('reason', ''))[:600], 'source_epoch': self.source_epoch,
                'observation_id': observation_id}
            return
        self.blockers.pop(key, None)
        if kind == 'read' and 'sha256' in result:
            self.read(result, observation_id)
        elif kind == 'patch' and status == 'patched':
            self.changed(path)
        elif kind in {'diagnose', 'verify'}:
            if kind == 'verify':
                self.verification_disposition = result.get('verification_disposition')
            if kind == 'diagnose':
                self.reproduced = status in {'passed', 'failed'}
                if self.reproduced:
                    self.blockers = {k: v for k, v in self.blockers.items()
                                     if v.get('code') != 'diagnostic_required'}
            verification = result.get('verification')
            verification = verification if isinstance(verification, dict) else {}
            verdict = status if kind == 'diagnose' else verification.get('verdict', 'unavailable')
            item = {'action': kind, 'status': verdict, 'source_epoch': self.source_epoch,
                    'observation_id': observation_id}
            if result.get('reason') or result.get('error'):
                item['reason'] = str(result.get('reason') or result.get('error'))[:600]
            failed_cases = result.get('failed_cases', [])
            if isinstance(failed_cases, list):
                item['failed_cases'] = [str(case)[:200] for case in failed_cases[:5]]
                item['failed_case_count'] = len(failed_cases)
            environment = result.get('environment')
            if isinstance(environment, dict):
                item['environment'] = {k: environment.get(k) for k in ('python', 'prefix', 'pytest')}
            failures = verification.get('failures', [])
            if isinstance(failures, list):
                item['failed_stages'] = [self._failure(failure) for failure in failures[:5]
                                         if isinstance(failure, dict)]
            self.diagnostics.append(item)
            if verdict != 'passed':
                self.blockers[key] = {**item, 'path': None,
                    'reason': str(result.get('reason') or result.get('error') or verdict)[:600],
                    'patching_blocked': kind == 'diagnose' and not self.reproduced}
        elif kind == 'prepare_environment':
            self.environment = {'status': status, 'observation_id': observation_id,
                                'reason': str(result.get('reason', ''))[:600]}
            if status != 'ready':
                self.blockers[key] = {**self.environment, 'action': kind, 'path': None,
                                      'source_epoch': self.source_epoch, 'patching_blocked': True}
        elif status == 'requires_arbitration':
            self.blockers[key] = {'action': kind, 'path': path, 'status': status,
                'reason': str(result.get('reason', 'Decision required'))[:600],
                'observation_id': observation_id, 'source_epoch': self.source_epoch}

    @staticmethod
    def _failure(failure):
        details = failure.get('details')
        details = details if isinstance(details, dict) else {}
        review = details.get('review')
        review = review if isinstance(review, dict) else {}
        gaps = review.get('missing_evidence')
        gaps = gaps if isinstance(gaps, list) else []
        return {'stage': failure.get('stage'), 'status': failure.get('status'),
                'cause': details.get('cause'), 'next_action': details.get('next_action'),
                'reason': str(details.get('reason', ''))[:400],
                'missing_evidence': [gap if isinstance(gap, dict) else str(gap)[:400] for gap in gaps[:3]]}

    def _reads(self):
        rows = []
        for entry in self.reads.values():
            row = {**entry, 'ranges': [list(r) for r in entry['ranges']]}
            cursor = 1
            if not entry['stale']:
                for start, end in entry['ranges']:
                    if start > cursor:
                        break
                    cursor = max(cursor, end + 1)
            row['next_unread_line'] = cursor if cursor <= entry['total_lines'] else None
            row['complete'] = not entry['stale'] and cursor > entry['total_lines']
            rows.append(row)
        return rows

    def section(self, name, offset=0):
        if type(offset) is not int or offset < 0:
            raise ValueError('State cursor must be a nonnegative integer')
        sections = {'inventory': self.inventory, 'reads': self._reads(),
                    'diagnostics': self.diagnostics, 'blockers': list(self.blockers.values())}
        if name not in sections:
            raise ValueError('State section must be inventory, reads, diagnostics or blockers')
        rows = sections[name]
        return {'section': name, 'items': rows[offset:offset + 20], 'total': len(rows),
                'next_offset': offset + 20 if offset + 20 < len(rows) else None}

    def snapshot(self):
        def stamped(rows):
            return [{**row, 'current_source_revision': row.get('source_epoch') == self.source_epoch}
                    for row in rows]
        return {'authority': 'runtime tool results, not model notebook', 'source_epoch': self.source_epoch,
                'phase': self.phase,
                'verification_disposition': self.verification_disposition,
                'patching_allowed': self.reproduced,
                'patching_rule': 'A real passed/failed diagnostic is required; missing environment is not reproduction',
                'path_rule': 'All tool paths are relative to the bound project; use inventory paths exactly',
                'inventory': self.section('inventory'), 'reads': self.section('reads'),
                'diagnostics': stamped(self.diagnostics[-4:]),
                'diagnostic_count': len(self.diagnostics), 'environment': self.environment,
                'blockers': stamped(list(self.blockers.values())[-10:]),
                'blocker_count': len(self.blockers),
                'paging': 'state_read retrieves older/remaining metadata; diagnostic_read retrieves full observations'}

    def export(self):
        """Complete metadata for durable evidence; prompt snapshots stay paged."""
        return {'summary': self.snapshot(), 'sections': {'inventory': list(self.inventory),
            'reads': self._reads(), 'diagnostics': list(self.diagnostics),
            'blockers': list(self.blockers.values())}}
