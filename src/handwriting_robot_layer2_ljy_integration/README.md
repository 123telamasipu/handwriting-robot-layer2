# 成员1：系统集成与主程序

这里是项目的主控模块，负责把成员2、3、4、5的结果组合成可执行设备任务。

## 子模块

```text
config.py          项目配置与接口版本
task_state.py      任务状态机
page_task.py       页面任务组织与坐标变换
trajectory_export.py  SVG/G-code/统一轨迹导出入口
device_task.py     设备任务队列与通信适配入口
```

## 依赖边界

- 接收成员2和成员3输出的 `StrokeDocument`
- 接收成员4生成的页面布局参数
- 调用成员5提供的设备适配和标定参数
- 不在这里复制笔迹算法、图形算法或界面代码

每个入口目前是第一版骨架，正式实现前先确认 `docs/stroke-interface.md`。
