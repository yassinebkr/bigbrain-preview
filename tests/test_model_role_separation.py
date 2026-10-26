"""Front/research runtime assignments and reload isolation, without inference."""
from types import SimpleNamespace

from bigbrain.system import BigBrainSystem
from bigbrain.web import model_roles
from bigbrain.auth import registry


def system_with_holders():
    system = BigBrainSystem.__new__(BigBrainSystem)
    system.llm_provider = object()
    system.front_brain = SimpleNamespace(llm_provider=system.llm_provider)
    system.orchestrator = SimpleNamespace(llm_provider=system.llm_provider)
    system.voice_brain = SimpleNamespace(llm_provider=system.llm_provider)
    system.verification = None
    system.brains = {name: SimpleNamespace(llm_provider=system.llm_provider)
                     for name in ('researcher', 'python_brain_0', 'web_app_brain_0')}
    return system


def test_codex_role_models_and_low_effort_do_not_inherit_global_override(monkeypatch):
    from bigbrain.llm.codex_provider import CodexProvider
    monkeypatch.setenv('BIGBRAIN_CODEX_EFFORT', 'high')
    for key, model in [('codex-sol-6.1', 'gpt-6.1-sol'), ('codex-luna-6', 'gpt-6-luna')]:
        provider = CodexProvider(key)
        assert provider.default_model == model
        assert provider.reasoning_effort == 'low'
        provider._inference_directory.cleanup()


def test_explicit_assignments_build_distinct_role_providers(monkeypatch):
    model_roles.set_role('front', 'codex-sol-6.1')
    model_roles.set_role('research', 'codex-luna-6')
    monkeypatch.setattr(registry, 'build_provider', lambda key: SimpleNamespace(key=key))
    system = system_with_holders()
    front = system._provider_for_role('front')
    research = system._provider_for_role('research')
    assert front.key == 'codex-sol-6.1' and research.key == 'codex-luna-6'
    assert front is system._provider_for_role('front')
    assert research is system._provider_for_role('research')
    assert front is not research
    assert system._provider_for_role('unassigned') is system.llm_provider


def test_provider_reload_retains_role_models_and_legacy_other_workers(monkeypatch):
    model_roles.set_role('front', 'codex-sol-6.1')
    model_roles.set_role('research', 'codex-luna-6')
    monkeypatch.setattr(registry, 'build_provider', lambda key: SimpleNamespace(key=key))
    system = system_with_holders()
    fallback = object()
    monkeypatch.setattr(system, '_create_llm_provider', lambda: fallback)
    system.reload_llm_provider()
    assert system.front_brain.llm_provider.key == 'codex-sol-6.1'
    assert system.brains['researcher'].llm_provider.key == 'codex-luna-6'
    assert system.brains['python_brain_0'].llm_provider is fallback
    assert system.brains['web_app_brain_0'].llm_provider is fallback
    research = system.brains['researcher'].llm_provider
    system.apply_model_role('front', 'codex-sol-6.1')
    assert system.brains['researcher'].llm_provider is research


async def test_role_endpoint_updates_runtime_holder(monkeypatch):
    from bigbrain.web import server as module
    from unittest.mock import AsyncMock
    from bigbrain.bus.bus import MessageBus
    calls = []
    monkeypatch.setattr(module, 'MODEL_ROLE_CHANGE_HOOK', lambda role, key: calls.append((role, key)))
    bus = MessageBus(auth=None)
    server = module.WebServer(bus=bus)
    request = SimpleNamespace(json=AsyncMock(return_value={'role': 'research', 'key': 'codex-luna-6'}))
    response = await server._handle_model_role_set(request)
    assert response.status == 200
    assert calls == [('research', 'codex-luna-6')]
    assert model_roles.current_lineup()['research']['key'] == 'codex-luna-6'
    await bus.close()
