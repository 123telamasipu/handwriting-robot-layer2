"""设备任务管理入口；具体串口协议由系统集成与设备负责人共同实现。"""


class DeviceTaskManager:
    """将排版后的轨迹提交给设备适配器。"""

    def __init__(self, adapter=None):
        self.adapter = adapter

    def submit(self, strokes):
        if self.adapter is None:
            raise RuntimeError("device adapter is not configured")
        return self.adapter.send(strokes)
