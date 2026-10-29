"""Model requests bound to an approved source inventory and recipient."""

import asyncio

from .local_projects import ProjectAccessError
from .local_project_transmission import validate_source_consent


class SourceBoundProvider:
    """Enforce project-specific source approval for maintenance model calls."""

    def __init__(self, provider, registry, project_id, revision, approved_spec):
        if approved_spec.metadata.get('approval', {}).get('decision') != 'approved':
            raise ProjectAccessError('Source transmission requires an approved proposal')
        consent = approved_spec.metadata.get('source_transmission')
        validate_source_consent(registry, project_id, revision, consent, provider)
        self.provider, self.registry = provider, registry
        self.project_id, self.revision, self.consent = project_id, revision, consent

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def check(self):
        validate_source_consent(self.registry, self.project_id, self.revision,
                                self.consent, self.provider)

    async def chat_complete(self, **kwargs):
        if kwargs.get('stream'):
            raise ProjectAccessError('Attached source calls require a bounded complete response')
        self.check()
        task = asyncio.create_task(self.provider.chat_complete(**kwargs))
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=0.1)
                with self.registry.access(self.project_id, self.revision, 'transmit'):
                    pass
            self.check()
            return await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def complete(self, prompt, **kwargs):
        return await self.chat_complete(messages=[{'role': 'user', 'content': prompt}], **kwargs)
