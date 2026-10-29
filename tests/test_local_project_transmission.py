"""Source consent binds file versions to the configured provider recipient."""

from types import SimpleNamespace
import pytest

from bigbrain.local_projects import ProjectAccessError, ProjectRegistry
from bigbrain.local_project_transmission import prepare_source_consent, provider_recipient, validate_source_consent


def fixture(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'main.py').write_text('print(42)\n')
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    project = registry.attach(source, ('read', 'transmit'))
    provider = SimpleNamespace(entry=SimpleNamespace(provider='openai_compat', base_url='https://provider.invalid/v1'))
    consent = prepare_source_consent(registry, project['id'], 1, provider_recipient(provider))
    return source, registry, project, provider, consent


def test_changed_provider_or_source_requires_renewal(tmp_path):
    source, registry, project, provider, consent = fixture(tmp_path)
    assert validate_source_consent(registry, project['id'], 1, consent, provider) == consent
    provider.entry.base_url = 'https://different.invalid/v1'
    with pytest.raises(ProjectAccessError, match='approval differs'):
        validate_source_consent(registry, project['id'], 1, consent, provider)
    provider.entry.base_url = 'https://provider.invalid/v1'
    (source / 'new.py').write_text('print(43)\n')
    with pytest.raises(ProjectAccessError, match='inventory changed'):
        validate_source_consent(registry, project['id'], 1, consent, provider)


def test_secret_content_is_excluded_from_approval_sources(tmp_path):
    source, registry, project, provider, _ = fixture(tmp_path)
    (source / 'config.py').write_text('api_key = "synthetic-sensitive-value"\n')
    consent = prepare_source_consent(registry, project['id'], 1, provider_recipient(provider))
    assert set(consent['source_versions']) == {'main.py'}
    assert consent['excluded_paths'] == ['config.py']


def test_retained_versions_stay_outside_sources_and_normal_file_access(tmp_path):
    import hashlib
    from bigbrain.local_project_patches import apply_patch_set
    from bigbrain.local_projects import ProjectFiles
    source, registry, project, provider, _ = fixture(tmp_path)
    project = registry.change(project['id'], 1, rights=('read', 'write', 'transmit'))
    apply_patch_set(registry, project['id'], project['revision'], [{
        'path': 'main.py', 'sha256': hashlib.sha256(b'print(42)\n').hexdigest(),
        'content': 'print(43)\n'}])
    consent = prepare_source_consent(registry, project['id'], project['revision'], provider_recipient(provider))
    assert set(consent['source_versions']) == {'main.py'}
    files = ProjectFiles(registry, project['id'], project['revision'])
    assert [entry['name'] for entry in files.list()] == ['main.py']
    with pytest.raises(ProjectAccessError, match='Excluded'):
        files.read('.bigbrain-recovery/.owner.json')
    assert (source / '.bigbrain-recovery').is_dir()


def test_revocation_and_recipient_credentials_are_rejected(tmp_path):
    _, registry, project, provider, consent = fixture(tmp_path)
    registry.change(project['id'], 1, state='revoked')
    with pytest.raises(ProjectAccessError):
        validate_source_consent(registry, project['id'], 1, consent, provider)
    provider.entry.base_url = 'https://user:password@provider.invalid/v1'
    with pytest.raises(ProjectAccessError, match='credential-free'):
        provider_recipient(provider)
