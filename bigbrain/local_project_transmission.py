"""Provider identity and versioned source consent for attached project work."""

import hashlib
from urllib.parse import urlsplit

from .local_projects import ProjectAccessError, ProjectFiles
from .project_inspection import EXTENSIONS, SENSITIVE_TEXT


def provider_recipient(provider):
    """Identify the configured transport destination independently of credentials."""
    entry = getattr(provider, 'entry', None)
    if entry is None:
        raise ProjectAccessError('Provider source recipient is unavailable')
    if entry.provider == 'codex':
        return {'provider': 'codex', 'endpoint': 'OpenAI ChatGPT subscription'}
    if entry.provider == 'openai_compat':
        endpoint = urlsplit(entry.base_url)
        if (endpoint.scheme != 'https' or not endpoint.hostname or endpoint.username
                or endpoint.password or endpoint.query or endpoint.fragment):
            raise ProjectAccessError('Source transmission requires a credential-free HTTPS endpoint')
        return {'provider': entry.provider, 'endpoint': entry.base_url.rstrip('/')}
    raise ProjectAccessError('Provider source consent requires a supported transport identity')


def prepare_source_consent(registry, project_id, revision, recipient):
    """List source revisions for the approval proposal while retaining content locally."""
    files = ProjectFiles(registry, project_id, revision)
    versions, excluded = {}, []
    total, visited = 0, 0

    def inspect(directory=''):
        nonlocal total, visited
        from pathlib import Path
        if len(Path(directory).parts) > 32:
            raise ProjectAccessError('Source consent exceeds directory depth limit')
        for entry in files.list(directory):
            visited += 1
            if visited > 2000:
                raise ProjectAccessError('Source consent exceeds inventory limit')
            if entry['type'] == 'folder':
                inspect(entry['path'])
                continue
            if Path(entry['name']).suffix.lower() not in EXTENSIONS:
                excluded.append(entry['path'])
                continue
            if len(versions) >= 64:
                raise ProjectAccessError('Source consent exceeds 64 files; select a narrower project')
            data = files.read(entry['path'], 48_000)
            text = data.decode('utf-8')
            if '\x00' in text or SENSITIVE_TEXT.search(text):
                excluded.append(entry['path'])
                continue
            total += len(data)
            if total > 128_000:
                raise ProjectAccessError('Source consent exceeds 128000 bytes; select a narrower project')
            versions[entry['path']] = hashlib.sha256(data).hexdigest()

    inspect()
    if not versions:
        raise ProjectAccessError('Project has no eligible sources for specialist inspection')
    return {'project_id': project_id, 'revision': revision, 'recipient': dict(recipient),
            'source_versions': versions, 'excluded_paths': excluded, 'source_bytes': total}


def validate_source_consent(registry, project_id, revision, consent, provider):
    """Refuse changed recipients, grants, inventories or source versions."""
    with registry.access(project_id, revision, 'transmit'):
        pass
    recipient = provider_recipient(provider)
    if (not isinstance(consent, dict) or consent.get('project_id') != project_id
            or consent.get('revision') != revision or consent.get('recipient') != recipient):
        raise ProjectAccessError('Source transmission approval differs from the current project or provider')
    current = prepare_source_consent(registry, project_id, revision, recipient)
    if current != consent:
        raise ProjectAccessError('Project source inventory changed; renew the source transmission approval')
    return current
