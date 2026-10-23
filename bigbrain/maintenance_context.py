"""Versioned maintenance context; persistent providers receive event suffixes."""
import json
from copy import deepcopy


class MaintenanceContext:
    def __init__(self):
        self.events = []
        self.batches = []
        self.cursor = 0
        self.state = None

    def append(self, observation):
        self.events.append(deepcopy({'event_id': len(self.events) + 1, **observation}))

    def messages(self, system, context, *, persistent=False):
        if not persistent:
            return [{'role': 'system', 'content': system},
                    {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}]
        # Supply the same initial prefix on each call. The provider's durable
        # accepted-message cursor appends only unseen events, including retries.
        if not hasattr(self, 'initial'):
            self.initial = deepcopy({k: v for k, v in context.items() if k != 'observations'})
        state = context['runtime_state']
        if self.state is not None:
            changes = {k: v for k, v in state.items() if self.state.get(k) != v}
            pending = self.events[self.cursor:]
            if pending or changes:
                self.batches.append(deepcopy({'events': pending, 'state_changes': changes,
                                     'remaining_actions': context['remaining_actions']}))
        else:
            self.batches.append(deepcopy({'events': list(self.events)}))
        self.cursor, self.state = len(self.events), deepcopy(state)
        messages = [{'role': 'system', 'content': system},
                    {'role': 'user', 'content': json.dumps({'protocol': 'maintenance-events/1',
                        'initial': self.initial}, ensure_ascii=False)}]
        messages[0]['content'] += (
            '\nmaintenance-events/1: initial binds the approved contract and run. '
            'Later batches contain new numbered events and state_changes replacing '
            'the named top-level runtime fields. Older source epochs are historical; '
            'an authoritative checkpoint supersedes them. Retrieve missing details '
            'with state_read or diagnostic_read; never infer successful checks.')
        messages.extend({'role': 'user', 'content': json.dumps(batch, ensure_ascii=False)}
                        for batch in self.batches)
        return messages
