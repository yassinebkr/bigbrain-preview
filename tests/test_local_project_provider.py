"""Provider calls stop when approved source authority changes."""

import asyncio
from types import SimpleNamespace
import pytest

from bigbrain.local_projects import ProjectAccessError, ProjectRegistry
from bigbrain.local_project_provider import SourceBoundProvider
from bigbrain.local_project_transmission import prepare_source_consent, provider_recipient


class RecordedProvider:
    """Deterministic protocol fixture with zero network activity."""
    entry = SimpleNamespace(provider='openai_compat', base_url='https://provider.invalid/v1')

    def __init__(self):
        self.calls = []
        self.started = asyncio.Event()
        self.finished = asyncio.Event()

    async def chat_complete(self, **kwargs):
        self.calls.append(kwargs)
        self.started.set()
        try:
            await asyncio.sleep(30)
        finally:
            self.finished.set()


def setup(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'main.py').write_text('print(42)\n')
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    project = registry.attach(root, ('read', 'transmit'))
    provider = RecordedProvider()
    consent = prepare_source_consent(registry, project['id'], 1, provider_recipient(provider))
    proposal = SimpleNamespace(metadata={'approval': {'decision': 'approved'}, 'source_transmission': consent})
    return root, registry, project, provider, proposal


@pytest.mark.asyncio
async def test_revocation_cancels_the_model_request(tmp_path):
    _, registry, project, provider, proposal = setup(tmp_path)
    guarded = SourceBoundProvider(provider, registry, project['id'], 1, proposal)
    task = asyncio.create_task(guarded.chat_complete(messages=[{'role': 'user', 'content': 'fixture'}], stream=False))
    await asyncio.wait_for(provider.started.wait(), 1)
    registry.change(project['id'], 1, state='revoked')
    with pytest.raises(ProjectAccessError):
        await asyncio.wait_for(task, 1)
    assert provider.finished.is_set()


@pytest.mark.asyncio
async def test_source_change_prevents_another_request(tmp_path):
    root, registry, project, provider, proposal = setup(tmp_path)
    guarded = SourceBoundProvider(provider, registry, project['id'], 1, proposal)
    (root / 'main.py').write_text('print(43)\n')
    with pytest.raises(ProjectAccessError, match='inventory changed'):
        await guarded.chat_complete(messages=[{'role': 'user', 'content': 'fixture'}], stream=False)
    assert provider.calls == []
