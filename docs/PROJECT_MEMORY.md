# 项目长期记忆

最后更新：2026-09-06

这份文件是项目的稳定上下文和专题文档索引。它解决“更换 Codex 对话或几个月后继续开发时，不能只依赖聊天记忆”的问题。

## 产品定位

Codex Control Tower 是一个本地、常驻置顶的简体中文桌面工具，用于统一查看多个 VS Code/Codex 窗口、账号额度、待处理任务、个人待办、系统资源与等待期间的学习内容。

核心体验是：平时保持为小型悬浮球，需要时展开；从一个窗口完成监控、账号切换、任务回看和碎片时间学习，减少频繁切换 VS Code 窗口的成本。

## 当前功能地图

| 子系统 | 状态 | 当前责任 | 主要文件 |
| --- | --- | --- | --- |
| 悬浮窗与导航 | 已实现 | 置顶悬浮球、展开/收起、四个主页面 | `src/codex_control_tower/ui.py` |
| VS Code 窗口监控 | 已实现 | 自动发现本地和 SSH 窗口、项目、运行/完成状态、待查看提醒和聚焦 | `src/codex_control_tower/ui.py`、`extensions/vscode-bridge/`、`extensions/remote-monitor/` |
| 账号与额度 | 已实现 | 读取 Codex Switch 账号和额度周期，过滤无额度账号，切换后聚焦目标窗口 | `src/codex_control_tower/ui.py`、`extensions/vscode-bridge/` |
| 今日待办 | 已实现 | 本地待办、优先级、当日完成进度、系统中文输入法 | `src/codex_control_tower/ui.py` |
| 系统监控 | 已实现 | CPU、内存、Swap、GPU/显存、网络、磁盘和高占用进程 | `src/codex_control_tower/system_monitor.py`、`src/codex_control_tower/ui.py` |
| 前沿追踪 | 已实现 | 具身智能宽召回、质量门槛、五通道推荐、视频、反馈和有界存储 | `src/codex_control_tower/learning_feed.py`、`config/learning_preferences.json`、`src/codex_control_tower/ui.py` |
| 系统学习 | 基础版已实现 | 已导入 VLA reviewed draft，支持路线、框架审查门禁、进度、知识点状态和来源；微卡正文待框架冻结后生成 | `src/codex_control_tower/curriculum.py`、`learning/domains/vla/`、`docs/LEARNING_SYSTEM.md` |

## 稳定产品决定

### UI 与隐私

- UI 使用简体中文，信息层级明确，避免过大、模糊、拥挤或像调试工具。
- 系统学习页面使用中性名称“系统学习”，不在明显位置出现“面试”“求职”“目标岗位”等字样。
- 个人偏好、项目路径、对话标题和学习进度默认只留在本机。
- 密钥仅放在被 Git 忽略的 `.env` 中。

### VS Code 与账号

- 每个 VS Code 窗口应自动识别其文件夹；本地与 Remote SSH 都属于正常使用场景。
- 当前已经聚焦的窗口不应继续显示为“待查看”。
- 账号切换采用“选择目标账号 → 切换并聚焦”，并过滤明确没有额度的账号。

### 系统监控

- 主要用途是观察训练负载，不做主动异常弹窗。
- 过滤启动分区、伪文件系统和 Windows 系统盘等对用户无帮助的磁盘项。
- 高频曲线保存在内存中，不持续写盘。

### 学习系统

- “前沿追踪”与“系统学习”是两个独立页面/模式：前者动态发现增量，后者沿稳定框架推进。
- 前沿推荐遵循“兴趣影响排序，不影响候选资格”，允许高质量未知方向进入。
- 推荐质量不足时宁可少显示，不用普通内容凑数。
- Curriculum 由可靠资料一次性编译、人工审查后冻结；日常使用不能自动重构框架。
- Frontier Event 只能成为 Curriculum 补丁候选，不能直接修改已冻结版本。
- 第一批系统学习路线是 VLA、VLN、WAM；公共知识节点跨路线复用。

完整设计见 [领域学习系统](LEARNING_SYSTEM.md)。

## 数据与增长边界

- `data/tasks.json`、`data/daily_todos.json`、`data/seen_sessions.json`、`data/learning.db` 等个人运行状态不进入 Git。
- 前沿内容普通记录保留 60 天且总数受限；收藏长期保留；热度快照保留 180 天。
- 系统学习的 Curriculum、来源和人工审查结果属于长期知识资产，可版本管理。
- 学习进度、反馈、薄弱点和缓存属于个人运行数据，不进入 Git。

## 当前下一步

1. VLA 四份交付物已经导入并通过结构、引用、重复节点与依赖环校验。
2. 用户从“系统学习”打开完整框架和审查报告，人工检查关键取舍后点击“确认启用 v1”。
3. 确认后冻结 VLA Curriculum v1，再生成和抽检第一批 3～5 分钟知识卡正文。
4. 验证 VLA 学习体验后，复用同一 pipeline 增加 VLN 和 WAM。

## 记忆更新记录

- 2026-09-06：建立仓库级长期记忆机制；记录领域学习系统、现有功能约束与后续 VLA 交付流程。
- 2026-09-06：按源码、配置、运行数据、测试、扩展和打包资源重新整理仓库；根目录 `launch.sh` 保持为稳定入口。
- 2026-09-06：导入网页版 GPT 生成的 VLA v1（18 个来源、7 个模块、39 个节点）；自动校验通过，并加入系统学习预览、路线和本地进度功能，暂不替用户冻结框架。
