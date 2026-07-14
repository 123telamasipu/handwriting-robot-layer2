from src.integration.task_state import can_transition, transition


def test_task_state_transitions():
    assert can_transition("created", "validating")
    assert transition("ready", "running") == "running"
    assert not can_transition("completed", "running")
