"""Model assignments follow isolated, persisted settings throughout the lifecycle.

Mixed provider configurations exercise assembly, reassignment and reconnection.
Provider calls are replaced at the transport boundary. The production settings
file stays outside the test fixtures.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bigbrain.auth import registry
from bigbrain.llm import model_registry
from bigbrain.system import BigBrainSystem
from bigbrain.web import model_roles


@pytest.fixture(params=[0, 1, 2], ids=['lineup-a', 'lineup-b', 'lineup-c'])
def configured_roles(request, monkeypatch):
    """Rotate distinct provider/model pairs across every role's saved setting."""
    entries = {
        f'test-role-{index}': model_registry.ModelEntry(
            key=f'test-role-{index}', display_name=f'Test model {index}',
            provider=provider, model_id=f'test-model-{index}', api_key_env='TEST_MODEL_KEY',
        )
        for index, provider in enumerate(('codex', 'openai_compat', 'anthropic_oauth'))
    }
    monkeypatch.setattr(model_registry, '_REGISTRY', {**model_registry._REGISTRY, **entries})
    keys = list(entries)
    selections = {role: keys[(index + request.param) % len(keys)]
                  for index, role in enumerate(model_roles.ROLES)}
    for role, key in selections.items():
        model_roles.set_role(role, key)
    assert model_roles._persisted() == selections
    monkeypatch.setattr(registry, 'build_provider', lambda key: SimpleNamespace(
        registry_key=key, entry=model_registry.get_model(key),
    ))
    return keys


def system_with_holders():
    """Retain a distinguishable fallback to detect accidental provider reuse."""
    system = BigBrainSystem.__new__(BigBrainSystem)
    system.llm_provider = object()
    system.front_brain = SimpleNamespace(llm_provider=system.llm_provider)
    system.orchestrator = SimpleNamespace(llm_provider=system.llm_provider)
    system.voice_brain = SimpleNamespace(llm_provider=system.llm_provider)
    system.verification = None
    system.brains = {
        name: SimpleNamespace(llm_provider=system.llm_provider)
        for name in ('researcher', 'python_brain_0', 'web_app_brain_0', 'cad_brain')
    }
    return system


def assert_runtime_matches_settings(system):
    """Compare every live holder against the independently read saved lineup."""
    choices = model_roles._persisted()
    for role, holders in system.runtime_model_roles().items():
        expected = model_registry.get_model(choices[role])
        for holder in holders:
            assert holder['registry_key'] == choices[role]
            assert holder['model_id'] == expected.model_id
            assert holder['provider'] == expected.provider


def test_registered_codex_models_follow_their_registry_defaults(monkeypatch):
    from bigbrain.llm.codex_provider import CodexProvider
    monkeypatch.setenv('BIGBRAIN_CODEX_EFFORT', 'high')
    for key, entry in model_registry._REGISTRY.items():
        if entry.provider != 'codex':
            continue
        provider = CodexProvider(key)
        try:
            selected = model_registry.get_model(key)
            assert provider.default_model == selected.model_id
            assert provider.reasoning_effort == (selected.reasoning_effort_default or 'high')
        finally:
            provider._inference_directory.cleanup()


def test_role_resolution_uses_each_saved_setting(configured_roles):
    system = system_with_holders()
    for role in model_roles.ROLES:
        provider = system._provider_for_role(role)
        assert provider.registry_key == model_roles.configured_key(role)
        assert system._provider_for_role(role) is provider
    assert system._provider_for_role('unassigned') is system.llm_provider


def test_reload_restores_each_role_and_clears_stale_model_overrides(configured_roles, monkeypatch):
    from bigbrain.verification.pipeline import VerificationPipeline
    from bigbrain.verification.v3_cross_check import CrossProviderVerifier
    system = system_with_holders()
    system.orchestrator.planner_model = 'previous-provider-model'
    system.brains['cad_brain'].model = 'previous-provider-model'
    system.brains['web_app_brain_0'].model = 'previous-provider-model'
    system.verification = VerificationPipeline()
    verifier = CrossProviderVerifier(system.llm_provider, model='previous-provider-model')
    system.verification.add_verifier(verifier)
    monkeypatch.setattr(system, '_create_llm_provider', object)
    system.reload_llm_provider()
    assert_runtime_matches_settings(system)
    assert system.orchestrator.planner_model is None
    assert system.brains['cad_brain'].model is None
    assert verifier.model is None
    expected_web = model_registry.get_model(model_roles.configured_key('web'))
    assert os.environ['BIGBRAIN_WEB_MODEL'] == expected_web.model_id


@pytest.mark.parametrize('role', model_roles.ROLES)
def test_reassignment_applies_the_new_setting_only_to_its_role(configured_roles, role):
    system = system_with_holders()
    before = {name: system._provider_for_role(name) for name in model_roles.ROLES}
    previous_key = model_roles.configured_key(role)
    replacement = next(key for key in configured_roles if key != previous_key)
    model_roles.set_role(role, replacement, apply=system.apply_model_role)
    assert system._provider_for_role(role).registry_key == model_roles.configured_key(role)
    for holder in system._holders_for_model_role(role):
        assert holder.llm_provider is system._provider_for_role(role)
    for other in model_roles.ROLES:
        if other != role:
            assert system._provider_for_role(other) is before[other]


def test_failed_selection_restores_settings_and_environment(configured_roles):
    role = 'subagent'
    previous = model_roles.configured_key(role)
    previous_env = os.environ['BIGBRAIN_SUBAGENT_MODEL']
    replacement = next(key for key in configured_roles if key != previous)

    def fail(selected_role, key):
        raise ValueError('provider unavailable')

    with pytest.raises(ValueError, match='provider unavailable'):
        model_roles.set_role(role, replacement, apply=fail)
    assert model_roles.configured_key(role) == previous
    assert os.environ['BIGBRAIN_SUBAGENT_MODEL'] == previous_env


def test_reconnection_adopts_settings_changed_after_assembly(configured_roles, monkeypatch):
    system = system_with_holders()
    monkeypatch.setattr(system, '_create_llm_provider', object)
    system.reload_llm_provider()
    before = {role: system._provider_for_role(role) for role in model_roles.ROLES}
    for role in model_roles.ROLES:
        replacement = next(key for key in configured_roles if key != model_roles.configured_key(role))
        model_roles.set_role(role, replacement)
    system.reload_llm_provider()
    assert_runtime_matches_settings(system)
    for role in model_roles.ROLES:
        assert system._provider_for_role(role) is not before[role]


def test_failed_reconnection_preserves_running_providers(configured_roles, monkeypatch):
    system = system_with_holders()
    original = system.llm_provider
    monkeypatch.setattr(system, '_create_llm_provider', object)

    def fail(key):
        raise ValueError('selected provider unavailable')

    monkeypatch.setattr(registry, 'build_provider', fail)
    with pytest.raises(ValueError, match='selected provider unavailable'):
        system.reload_llm_provider()
    assert system.llm_provider is original
    assert all(holder.llm_provider is original for role in model_roles.ROLES
               for holder in system._holders_for_model_role(role))


async def test_normal_worker_assembly_uses_saved_role_providers(configured_roles, monkeypatch):
    from bigbrain.bus.bus import MessageBus
    from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator
    from bigbrain.brains.cad_brain import CadBrain
    monkeypatch.setenv('BIGBRAIN_PYTHON_POOL', '1')
    monkeypatch.setenv('BIGBRAIN_WEB_POOL', '1')
    system = BigBrainSystem(workspace='default')
    system.llm_provider = object()
    system.bus = MessageBus(auth=None)
    system.orchestrator = WorkspaceOrchestrator('default', system.bus, llm_provider=system._provider_for_role('planner'))
    try:
        await system._create_brains()
        assert isinstance(system.brains['cad_brain'], CadBrain)
        assert_runtime_matches_settings(system)
    finally:
        await system.bus.close()


async def test_role_api_applies_and_reports_the_selected_setting(configured_roles, monkeypatch):
    from bigbrain.web import server as module
    from bigbrain.bus.bus import MessageBus
    system = system_with_holders()
    monkeypatch.setattr(module, 'MODEL_ROLE_CHANGE_HOOK', system.apply_model_role)
    monkeypatch.setattr(module, 'MODEL_ROLE_STATUS_HOOK', system.runtime_model_roles)
    bus = MessageBus(auth=None)
    server = module.WebServer(bus=bus)
    role = 'subagent'
    replacement = next(key for key in configured_roles if key != model_roles.configured_key(role))
    request = SimpleNamespace(json=AsyncMock(return_value={'role': role, 'key': replacement}))
    try:
        response = await server._handle_model_role_set(request)
        assert response.status == 200
        response = await server._handle_model_roles(None)
        selected = json.loads(response.body)['roles'][role]
        assert selected['key'] == model_roles.configured_key(role)
        assert all(holder['registry_key'] == selected['key'] for holder in selected['runtime'])
    finally:
        await bus.close()


def test_unassigned_roles_display_the_automatic_provider(monkeypatch):
    automatic = next(key for key, entry in model_registry._REGISTRY.items() if entry.provider == 'openai_compat')
    monkeypatch.setattr(registry, 'select_registry_key', lambda: automatic)
    for role in model_roles.ROLES:
        monkeypatch.delenv(f'BIGBRAIN_{role.upper()}_MODEL_KEY', raising=False)
    assert all(value['key'] == automatic for value in model_roles.current_lineup().values())
