# 写字机二层开发（Handwriting Robot Layer 2）

面向大创项目的写字机二层控制与系统集成仓库。本仓库负责统一输入输出格式、任务状态机、设备通信、模块集成、测试和结题材料。

## 项目目标

- 接收上层下发的书写任务（文本、轨迹或文件）
- 将任务转化为统一的设备指令
- 通过状态机管理任务生命周期
- 与下位机稳定通信并反馈执行状态
- 为算法、控制、界面等模块提供清晰接口

## 目录结构

```text
docs/          设计文档、协议和周测记录
src/           二层程序源码
tests/         自动化测试
examples/      输入输出样例
.github/       Issue 与 Pull Request 模板
```

## 快速开始

1. 克隆仓库并新建个人功能分支：`git switch -c feat/功能名称`
2. 按 `docs/data-format.md` 对接模块，按 `docs/communication-protocol.md` 对接设备
3. 提交前运行测试，并通过 Pull Request 合并到 `main`

## 协作规则

- `main` 始终保持可运行，禁止直接提交
- 功能分支：`feat/*`；修复分支：`fix/*`；文档分支：`docs/*`
- 一个 Pull Request 聚焦一项任务，至少由一名其他成员审阅
- 任务、缺陷和每周测试问题统一使用 GitHub Issues 跟踪
- 提交信息建议使用：`feat:`、`fix:`、`docs:`、`test:`、`refactor:`

详细约定见 [CONTRIBUTING.md](CONTRIBUTING.md)，负责人工作清单见 [docs/project-lead-checklist.md](docs/project-lead-checklist.md)。

## 当前阶段

仓库处于项目初始化阶段。接口中的字段和设备命令均为第一版草案，应在首次联调会上确认后冻结版本。

## 许可证

本项目采用 MIT License，便于团队成员协作、展示和后续复用。
