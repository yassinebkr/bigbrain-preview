"""Declared intent controls execution; source vocabulary never hosts a server."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bigbrain.brains.python_brain import PythonBrain
from bigbrain.brains.python_execution import interaction_mode
from bigbrain.bus.bus import MessageBus
from bigbrain.verification.evidence import default_repository
from bigbrain.verification.gate import RunGate


def approved_payload(mode='cli', *, legacy=False):
    repo = default_repository()
    spec = RunGate(repo).build_spec(f'Run the declared Python {mode} project', ['main.py'])
    if not legacy:
        spec.metadata['execution'] = {'interaction_mode': mode}
    repo.save_spec(spec)
    spec = repo.approve_spec(spec.design_id, plan_id='execution')
    return {'user_request': spec.user_request,
        'contract_revision': {'design_id': spec.design_id, 'revision': spec.revision},
        'executable': mode != 'library'}


def test_approved_intent_is_used_when_worker_omits_it(tmp_path):
    assert interaction_mode(approved_payload('service')) == 'service'
    assert interaction_mode(approved_payload('library')) == 'library'


@pytest.mark.parametrize('override', ['service', 'browser', 'library', 'anything'])
def test_payload_cannot_change_approved_cli_intent(tmp_path, override):
    with pytest.raises(ValueError, match='approved execution mode'):
        interaction_mode({**approved_payload(), 'interaction_mode': override})


def test_old_approval_cannot_gain_a_service_implicitly(tmp_path):
    payload = approved_payload(legacy=True)
    assert interaction_mode(payload) == 'cli'
    with pytest.raises(ValueError, match='approve again'):
        interaction_mode({**payload, 'interaction_mode': 'service'})


def test_approved_web_deliverable_cannot_be_run_as_python(tmp_path):
    repo = default_repository()
    spec = RunGate(repo).build_spec('Build browser application', ['index.html'])
    spec.metadata['delivery'] = {'deliverable_type': 'web_app', 'executable': True}
    repo.save_spec(spec)
    spec = repo.approve_spec(spec.design_id, plan_id='browser')
    with pytest.raises(ValueError, match='WebAppBrain'):
        interaction_mode({'contract_revision': {'design_id': spec.design_id, 'revision': spec.revision}})


@pytest.mark.parametrize('payload', [
    {'interaction_mode': 'browser'}, {'deliverable_type': 'web_app'},
    {'interaction_mode': 'library', 'executable': True},
    {'interaction_mode': 'service', 'executable': False}])
def test_incompatible_declarations_are_rejected(payload):
    with pytest.raises(ValueError):
        interaction_mode(payload)


@pytest.mark.asyncio
async def test_cli_with_web_words_runs_without_rewriting_or_installing(tmp_path, monkeypatch):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=tmp_path)
    brain._evidence_enabled = False
    directory = tmp_path / 'project'
    directory.mkdir()
    # Includes every old trigger without actually being a server.
    source = '''# from fastapi import FastAPI; from flask import Flask
# from starlette import app; from sanic import Sanic
# import uvicorn; import gunicorn; socketio; websocket; app.listen(
# app.run(host="0.0.0.0", port=8080)
print("offline CLI complete")
'''
    entry = directory / 'main.py'
    entry.write_text(source)
    monkeypatch.setattr(brain, '_setup_project_venv', AsyncMock(return_value=Path(sys.executable)))
    monkeypatch.setattr(brain, '_install_in_venv', AsyncMock(side_effect=AssertionError('No inferred dependencies')))
    try:
        result = await brain._assemble_and_run({'project_name': 'project', 'entry_point': 'main.py',
            'all_files': [{'path': 'main.py'}], 'interaction_mode': 'cli'})
        assert result['success'] and result['stdout'].strip() == 'offline CLI complete'
        assert result['interaction_mode'] == 'cli'
        assert 'preview_url' not in result and entry.read_text() == source
        brain._install_in_venv.assert_not_awaited()
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_declared_service_stops_before_finite_runner_or_any_source_write(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    brain = PythonBrain('python', bus, work_dir=tmp_path)
    brain._setup_project_venv = AsyncMock(side_effect=AssertionError('No guessed service launch'))
    brain._exec_streamed = AsyncMock(side_effect=AssertionError('Service is not a finite CLI'))
    try:
        payload = {**approved_payload('service'), 'interaction_mode': 'service',
            'project_name': 'backend', 'all_files': [{'path': 'main.py'}]}
        result = await brain._assemble_and_run(payload)
        assert result['delivery_status'] == 'incomplete' and not result['verified']
        assert not result['success'] and not result['runnable']
        assert result['verification']['failures'][0]['details']['cause'] == 'environment_blocked'
        assert not (tmp_path / 'backend').exists()
        brain._exec_streamed.assert_not_awaited()
    finally:
        await bus.close()
