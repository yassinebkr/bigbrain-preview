"""System-level offline replay; no real inference or domain-specific runtime rules."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools.run_maintenance_campaign import main, recorded_tokens

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('mode', ['bus', 'disconnect', 'frozen'])
def test_actual_stdio_bus_orchestration_and_transaction(tmp_path, mode):
    disconnect = mode == 'disconnect'
    args = [sys.executable, str(ROOT / 'tools/replay_maintenance_trace.py'), '--case', 'cross-module']
    if mode == 'frozen':
        contract = tmp_path / 'contract.json'
        contract.write_text(json.dumps(['Addition works; unchanged() and existing tests are preserved.']))
        args.extend(['--contract-file', str(contract)])
    else:
        args.append('--bus')
    if disconnect:
        args.append('--disconnect')
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=30,
        env={**os.environ, 'TMPDIR': str(tmp_path), 'BIGBRAIN_CODEX_BINARY': '/must-not-run-real-codex'})
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout.splitlines()[-1])
    assert summary['success'] is (not disconnect)
    assert summary['transaction']['state'] == ('rolled_back' if disconnect else 'committed')
    assert len(summary['worker_threads']) == 1
    assert len(summary['transmitted_event_ids']) == len(set(summary['transmitted_event_ids']))
    evidence = next(tmp_path.glob('bigbrain-maintenance-replay-*/replay-result.json'))
    result = json.loads(evidence.read_text())
    assert result['real_inference_calls'] == 0
    if mode != 'frozen':
        assert 'contracts.proposal' in result['event_names']
        assert ('task.failed' if disconnect else 'task.complete') in result['event_names']
    else:
        assert result['verification']['verdict'] == 'passed'


@pytest.mark.asyncio
@pytest.mark.parametrize('usage_known', [True, False])
async def test_campaign_stops_on_budget_or_unknown_usage_and_isolates_provider_root(tmp_path, monkeypatch, usage_known):
    from bigbrain.llm.usage import get_tracker, UsageRecord
    import dotenv
    import bigbrain.auth.registry as registry
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *a, **k: None)
    monkeypatch.setenv('TMPDIR', str(tmp_path))
    # tempfile may have cached another root in the parent pytest process.
    import tools.run_maintenance_campaign as campaign
    original_mkdtemp = campaign.tempfile.mkdtemp
    monkeypatch.setattr(campaign.tempfile, 'mkdtemp', lambda **kw: original_mkdtemp(dir=tmp_path, **kw))
    class OfflineProvider:
        calls = 0
        closed = False
        def __init__(self):
            self.session_root = Path(os.environ['BIGBRAIN_SESSIONS_DIR'])
        async def complete(self, prompt, **kwargs):
            return await self.chat_complete(messages=[{'role': 'user', 'content': prompt}], **kwargs)
        async def chat_complete(self, **kwargs):
            self.calls += 1
            if usage_known:
                get_tracker().record(UsageRecord(model_id='offline-fixture', provider='offline',
                    input_tokens=3, output_tokens=2, total_tokens=5))
            return json.dumps(['Addition works and existing tests remain unchanged.'])
        async def aclose(self):
            self.closed = True
    providers = []
    def build(key):
        provider = OfflineProvider()
        providers.append(provider)
        return provider
    monkeypatch.setattr(registry, 'build_provider', build)
    await main(SimpleNamespace(model='offline-fixture', native_model='unused', reasoning='low',
        case='cross-module', compare=False, approve_gcode_conflicts=False,
        max_calls=1 if usage_known else 24, max_reported_tokens=100, timeout=30))
    assert providers[0].calls == 1  # worker never reaches the provider
    assert providers[0].closed
    assert providers[0].session_root.is_relative_to(tmp_path)
    result_path = next(tmp_path.glob('bigbrain-maintenance-campaign-*/campaign-result.json'))
    result = json.loads(result_path.read_text())
    ledger = json.loads((result_path.parent / 'calls.json').read_text())
    assert result['all_delivered'] is False
    assert result['reported_tokens'] == (5 if usage_known else 0)
    assert result['unknown_usage_calls'] == ([] if usage_known else [1])
    assert recorded_tokens(ledger) == result['reported_tokens']
    assert ledger[0]['phase'] == 'planning'
    assert result['results'][0]['transaction']['state'] == 'rolled_back'


def test_paid_launcher_requires_explicit_live_opt_in():
    proc = subprocess.run([sys.executable, str(ROOT / 'tools/run_maintenance_campaign.py'),
        '--case', 'cross-module'], capture_output=True, text=True, timeout=10)
    assert proc.returncode != 0
    assert '--live is required' in proc.stderr
