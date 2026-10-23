"""Offline validation of the live harness boundaries; no model calls."""
import subprocess
import sys

import pytest

from tools.compare_maintenance_orchestration import ROOT, frozen_sources, orchestration, CONTRACTS


def test_baseline_substitution_is_scoped_and_restores_after_failure():
    from bigbrain import maintenance
    from bigbrain.verification import semantics
    original = maintenance.maintain, semantics._progressive_review
    with pytest.raises(RuntimeError, match='synthetic'):
        with orchestration('before', frozen_sources()):
            assert maintenance.maintain is not original[0]
            assert semantics._progressive_review is not original[1]
            raise RuntimeError('synthetic')
    assert (maintenance.maintain, semantics._progressive_review) == original
    with orchestration('after', frozen_sources()):
        assert (maintenance.maintain, semantics._progressive_review) == original


def test_no_live_flag_refuses_before_provider_initialization():
    result = subprocess.run([sys.executable, str(ROOT / 'tools/compare_maintenance_orchestration.py')],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert '--live required' in result.stderr
    assert 'Evidence directory' not in result.stdout


def test_frozen_acceptance_keeps_cli_regression_and_test_preservation():
    assert len(CONTRACTS) == 3
    assert 'zero and negative' in CONTRACTS[0]
    assert 'CLI arguments and output format' in CONTRACTS[1]
    assert 'Existing tests remain present' in CONTRACTS[2]
