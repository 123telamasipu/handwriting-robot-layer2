"""任务状态机的最小实现，后续接入设备事件和持久化。"""

TERMINAL_STATES = {"completed", "failed", "cancelled"}

ALLOWED_TRANSITIONS = {
    "created": {"validating", "cancelled"},
    "validating": {"ready", "failed", "cancelled"},
    "ready": {"running", "cancelled"},
    "running": {"paused", "completed", "failed", "cancelled"},
    "paused": {"running", "cancelled", "failed"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


def can_transition(current: str, target: str) -> bool:
    """返回状态迁移是否合法。"""
    return target in ALLOWED_TRANSITIONS.get(current, set())


def transition(current: str, target: str) -> str:
    """执行一次状态迁移，不合法时抛出 ValueError。"""
    if not can_transition(current, target):
        raise ValueError(f"invalid task transition: {current} -> {target}")
    return target
