# 写字机器人二层开发团队 Git 与 GitHub 使用手册

项目地址：<https://github.com/123telamasipu/handwriting-robot-layer2>

## 一、基本原则

- `main` 是稳定主分支，禁止直接提交。
- 每个人只在自己的功能分支开发，完成后通过 Pull Request 合并。
- 开始工作前先同步 `main`；提交前检查改动；冲突时不要覆盖别人代码。
- 代码、测试、模块说明和 `日志.md` 一起维护。

## 二、第一次准备

安装 Git 后设置身份：

```bash
git config --global user.name "你的GitHub姓名"
git config --global user.email "你的GitHub邮箱"
git config --global init.defaultBranch main
```

在仓库页面点击 **Fork**，复制到自己的账号，然后执行：

```bash
git clone 你的Fork地址
cd handwriting-robot-layer2
git remote -v
```

## 三、每天开始工作：完整操作顺序

### 3.1 开始前：确认环境和自己的任务

1. 打开终端，进入项目目录：`cd D:\handwriting-robot-layer2`。
2. 确认电脑联网、GitHub 登录正常，并确认自己今天要完成的 Issue 或任务。
3. 查看当前状态：`git status`。如果有未提交的修改，先保存或联系成员1，不要直接覆盖。

### 3.2 开始前：同步最新项目

```bash
git switch main
git pull origin main
```

这两条命令的作用是：切换到稳定主分支，并把其他成员已经合并的最新内容拉到本地。每次开始工作都要做，避免基于旧版本开发。

### 3.3 开始开发：创建自己的分支

```bash
git switch -c feat/成员缩写-功能名称
```

例如：`feat/wl-handwriting-scan`、`feat/nrx-line-detection`。分支创建成功后，今天的代码只在这个分支中修改，不直接写 `main`。

### 3.4 开发过程中：边做边检查

只修改自己负责的目录，定期执行 `git status` 和 `git diff`，确认没有误改其他成员文件。接口、目录或数据格式需要变化时，先在 Issue 中说明。

### 3.5 完成后：本地测试和整理日志

完成代码后先运行对应测试，再更新自己模块的 `日志.md`，填写日期、完成内容、测试结果、问题和下一步计划。确认没有密码、Token、隐私资料、大视频和临时文件。

### 3.6 最后上传：提交并推送分支

```bash
git status
git add 需要提交的文件
git commit -m "feat: 简短说明改动"
git push -u origin feat/成员缩写-功能名称
```

`git add` 只添加自己检查过的文件；`commit` 是在本地保存一个版本；`push` 才是把分支上传到自己的 GitHub Fork。上传后检查 GitHub 页面是否能看到该分支和最新提交。

### 3.7 上传后：创建 Pull Request

在自己的 Fork 页面点击 **Compare & pull request**，填写完成内容、测试方法、测试结果、影响范围和剩余问题，指定成员1（ljy）审核。成员1审核通过并合并后，其他成员才能在下一次 `git pull origin main` 中获得你的代码。

## 四、修改和检查

只修改自己的模块、相关测试、接口文档和日志。检查改动：

```bash
git status
git diff
```

不得提交密码、Token、隐私资料、未经脱敏图片、视频、缓存和临时文件。

## 五、提交代码

```bash
git add 需要提交的文件
git commit -m "feat: 简短说明改动"
git push -u origin feat/成员缩写-功能名称
```

提交类型建议：`feat` 新功能、`fix` 修复、`docs` 文档、`test` 测试、`refactor` 重构。提交前确认没有误改其他模块、测试可运行、接口符合 `docs/stroke-interface.md`、日志已更新。

## 六、提交 Pull Request

在自己的 Fork 页面点击 **Compare & pull request**。标题写模块和功能，正文说明完成内容、测试方法、测试结果、影响模块和待解决问题。指定成员1（ljy）审核，不要自行合并。

## 七、同步和冲突处理

```bash
git switch main
git pull origin main
git switch feat/你的分支
git merge main
```

冲突时打开文件，保留正确内容并删除 `<<<<<<<`、`=======`、`>>>>>>>` 标记，然后执行：

```bash
git add 已解决的文件
git commit -m "fix: 解决合并冲突"
git push
```

不确定时停止操作并联系成员1，不要使用强制推送覆盖远程分支。

## 八、日志和进度汇报

在自己模块的 `日志.md` 中填写日期、今日完成、测试结果、遇到的问题、需要协助和明日计划；每周依据日志在 Issue 或团队群汇报。

## 九、常用撤销操作

撤销尚未提交的单个文件：`git restore 文件名`。

取消暂存但保留修改：`git restore --staged 文件名`。

已经推送的提交不要擅自改历史；需要修改时先联系成员1。

## 十、安全注意事项

- 不把密码和个人 Token 写进代码或日志。
- 不执行来源不明的脚本和命令。
- 不使用 `git push --force`，除非成员1明确安排。
- 不直接删除或重命名其他成员模块。
- 大文件和原始实验数据放在约定共享位置，仓库只保留脱敏样例。

## 十一、常见问题

- `git` 不是命令：安装 Git 并重启终端。
- Push 被拒绝：确认推送的是自己的 Fork，并先同步远程分支。
- 不知道当前分支：执行 `git branch --show-current`；开发时不应是 `main`。
- 误改其他模块：停止提交，用 `git diff` 检查并联系成员1。
