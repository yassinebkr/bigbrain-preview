"""Research transition safety and complement termination."""
import pytest

from bigbrain.research_stages import StageController


def test_single_complement_and_unique_settlement():
    controller = StageController()
    for stage in ("collect", "freeze", "draft", "control", "collect_complement",
                  "freeze_new_revision", "revise", "control"):
        controller.advance(stage, reason="Scripted evidence journey")
    with pytest.raises(ValueError, match="allowance exhausted"):
        controller.advance("collect_complement", reason="Another gap")
    controller.settle("partial", reason="Remaining evidence gap")
    with pytest.raises(ValueError, match="Invalid research transition"):
        controller.settle("complete", reason="Late result")
    assert controller.outcome == "partial"


def test_complement_reserves_its_entire_closing_path():
    controller = StageController(stage="control")
    with pytest.raises(ValueError, match="closing envelope"):
        controller.advance("collect_complement", reason="Missing version", closing_fits=False)
    assert not controller.complement_used
    assert controller.stage == "control"


@pytest.mark.parametrize("stage", ["scope", "collect", "freeze", "draft", "control",
                                  "collect_complement", "freeze_new_revision", "revise"])
def test_every_active_stage_can_settle_after_interruption(stage):
    controller = StageController(stage=stage)
    controller.settle("interrupted", reason="Restored interrupted attempt")
    assert controller.stage == "settle"
