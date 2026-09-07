# Codex Control Tower

一个基于 PyQt5/Qt 的本地浮动任务看板，适合配合 VS Code 的 Codex 和 codexswitch 使用。界面使用系统 Qt5，并直接连接 Fcitx5/Rime，支持在“今日待办”输入框中顺滑输入中文。

## 项目记忆

项目的长期产品约束、当前功能地图和后续事项记录在 [`docs/PROJECT_MEMORY.md`](docs/PROJECT_MEMORY.md)。领域学习系统的完整 pipeline 记录在 [`docs/LEARNING_SYSTEM.md`](docs/LEARNING_SYSTEM.md)。根目录的 `AGENTS.md` 会提醒新的 Codex 会话先读取这些文档，并要求重要决定不能只留在聊天记录中。

## 目录结构

```text
codex管理/
├── src/codex_control_tower/  # 正式 Python 应用
├── config/                   # 可编辑配置
├── data/                     # 本地运行数据（Git 忽略）
├── tests/                    # 自动化测试
├── extensions/               # 本地/远程 VS Code 扩展
├── learning/                 # 版本化领域知识资产
├── scripts/                  # 通知钩子等辅助入口
├── packaging/                # 桌面启动文件
├── assets/                   # 图标资源
├── docs/                     # 长期设计与项目记忆
└── launch.sh                 # 保持稳定的启动入口
```

## 启动

```bash
./launch.sh
```

窗口默认置顶并折叠为悬浮球；展开后可以查看 Codex 状态、账号额度、切换账号、管理今日待办，并跳转到对应的 VS Code 项目。

## 工作与灵感管理

“今日待办”可以把多个未完成事项设为“正在做”，适合并行推进不同工作。所有激活项都会自动置顶并高亮，每项可以独立开始或暂停。已有待办支持修改内容、优先级和绑定项目。

“任务监控”的每个项目窗口提供“记灵感”入口，用于保存暂时来不及实现的项目想法。卡片会预览最近一条未处理灵感，弹窗内可以新增、编辑、完成和删除。灵感仅保存在 `data/project_ideas.json`，按项目隔离且全局最多保留 1000 条。

## 等待学习

“等待学习”分成“前沿追踪”“系统学习”和“单词闪卡”三个模式。

“前沿追踪”会按 3、5、10 或 20 分钟生成有边界的具身智能前沿学习包。候选池宽召回 arXiv 机器人论文、GitHub 代码库、Hugging Face 模型和 Google DeepMind / Boston Dynamics / NVIDIA Developer 官方 Demo，再用范围相关度和质量门槛去掉普通行业应用、低信号模型和不相关的泛机器人内容。系统不再强制凑齐论文、视频和模型；当天没有足够好的内容时会少显示。

合格候选会同时计算 `Core / Adjacent / Major / Emerging / Serendipity` 五个通道得分，再在全局候选池中进行软分配、去重和多样性重排。兴趣只决定排序，不决定候选资格；来自重点团队、具有多来源证据或热度上升的未知方向仍可进入 `Major / Emerging / Serendipity`。论文、代码、模型和 Demo 如果属于同一项工作，会合并为一张研究事件卡。

推荐偏好保存在可直接编辑的 `config/learning_preferences.json` 中，包括兴趣与知识程度、近期兴趣有效期、参照工作、五通道比例、视频偏好和质量门槛。程序不会自动覆盖这个人工配置。学习页的“推荐设置”按钮可以直接打开它。

本地文件夹名和对话标题只用来得到抽象主题标识，并且只作为弱加分；原始路径和对话标题不会发给 DeepSeek。DeepSeek 只负责根据已选候选生成简体中文的摘要、增量和价值判断，不负责决定世界上哪些内容可以进入候选池。

学习历史、反馈和热度快照保存在本地 `data/learning.db` 中。URL 自动去重，可标记“多推类似、不感兴趣、太基础、太难”；不感兴趣的条目只会隐藏而不会破坏反馈历史。未收藏内容最多保留 1000 条且 60 天后自动清理，热度快照保留 180 天，收藏内容一直保留。

“系统学习”读取 `learning/domains/` 中经过版本管理的 Curriculum。目前已导入 VLA v1：18 个来源、7 个模块、39 个节点，支持核心/标准/研究路线、进度、知识点状态、来源跳转和模块概览。框架当前保持 `reviewed_draft`，可以预览；只有你阅读完整框架和审查报告后点击“确认启用 v1”，本机才会记录为已确认。学习进度保存在 `data/curriculum_progress.json`，不会进入 Git。

知识点不会直接拿课程提纲充当正文：系统按“直觉 → 机制 → VLA 例子 → 方法辨析 → 术语 → 自测”展示 3～5 分钟微课。已审查的关键课随项目提供，其余课程首次打开时使用 DeepSeek 在后台生成、保存到有界本地缓存，并提前准备下一课。

系统学习页右下角始终悬浮“问 AI”按钮，滚动长课文时也不会消失。它会打开当前知识点专属的学习助手，并优先停靠到阅读窗口旁边而不是遮住正文。可以直接用自然语言连续追问，助手自动获得当前课程正文和知识边界，但不会收到项目路径、账号或 Codex 对话。问答记录仅保存在本机，每个知识点最多 40 条、全局最多 1200 条。

“单词闪卡”复用用户自有项目 `123awsd/win-floating-vocab` 的三套词库和 32 张猫猫 PNG，并按当前 Qt 界面重新实现。默认先隐藏释义，要求主动回想后再翻面；选择“忘了 / 模糊 / 记住了”会安排不同的下次复习时间，忘记的词还会在当前学习轮次稍后再次出现。切换单词后会自动使用本机 `Alt+Q` 的 Piper 自然英语声音朗读；快速切词时取消旧播放，只朗读画面上的最新单词。另提供在线语音与 eSpeak 兜底，并支持收藏、顺序/随机、键盘操作和导入 UTF-8 TXT 词库。内置词库进入 Git，个人词库与复习记录只保存在 `data/`。

## 系统监控

“系统监控”页面使用本机 Linux 的 procfs/sysfs，不依赖常驻后台服务，每 2 秒刷新 CPU、内存、Swap、磁盘、网络、高占用进程和 NVIDIA GPU/显存数据。磁盘区域会枚举当前所有有效的物理、网络和可移动挂载点，并过滤 proc、tmpfs、Snap 镜像等系统伪文件系统、EFI/boot 启动分区，以及包含 Windows 系统目录的 NTFS 系统盘。页面会显示最近样本的迷你曲线，曲线只保存在内存中，不会不断写入硬盘。当驱动或传感器不可用时，对应项目显示“数据不可用”，不弹窗、不干扰训练任务。

学习页面顶部始终显示 Codex 的运行中和已完成待处理数量。任务完成时会优先出现红色提醒，可直接跳回对应的 VS Code 窗口。

在项目目录创建不提交到 Git 的 `.env`：

```bash
DEEPSEEK_API_KEY=你的密钥
```

面板每 5 秒自动扫描桌面上的 VS Code 窗口。它会读取窗口标题，并结合 VS Code 的
`workspaceStorage` 自动显示项目文件夹和绝对路径（例如 `/home/uav/map_VLN`）。
“聚焦”可以直接切换到对应窗口，“建任务”会自动把该窗口绑定到一条任务。

每个窗口卡片还提供账号菜单。先选择目标账号，卡片会显示“待切换”，再点击“切换并聚焦”即可完成切换。面板会自动检查和修复
`extensions/vscode-bridge` 的本地安装版本；如果某个早先打开的窗口尚未加载桥接，第一次切换时会自动重新安装并热加载桥接，等待就绪后继续完成
Codex Switch 账号切换、重启扩展宿主，并重新打开 Codex 侧栏。

账号菜单还提供手动的一个或多个“API 备用”选项，公共元数据在 [`config/api_providers.json`](config/api_providers.json)中维护。它们各自使用完全独立的 `CODEX_HOME`，只作为 Plus 额度不足时的按量计费备用通道；不会自动接管，也不会覆盖 Codex Switch 中现有的 Plus 登录。切换保留原 VS Code 窗口，并在真实 Codex 子进程目录验证成功后才显示完成。不同运行时的历史只读聚合展示，不共享可写数据库。具体约束见 [`docs/ACCOUNT_PROVIDERS.md`](docs/ACCOUNT_PROVIDERS.md)。

### 新增备用 API

每个 API 服务商必须使用独立的 `CODEX_HOME`。以下示例用 `new-api` 作为服务商 ID；实际添加时，需要把它替换为简短且唯一的英文 ID。

1. 创建独立目录：

```bash
mkdir -p ~/.codex-providers/new-api
chmod 700 ~/.codex-providers/new-api
```

2. 创建 `~/.codex-providers/new-api/config.toml`：

```toml
model = "gpt-6-astra"
model_provider = "new-api"
model_reasoning_effort = "xhigh"
approval_policy = "never"
sandbox_mode = "danger-full-access"
service_tier = "fast"

[model_providers.new-api]
name = "new-api"
base_url = "https://example.com/v1"
wire_api = "responses"
requires_openai_auth = true
```

模型、推理档位和 `base_url` 应以服务商文档为准。当前窗口路由要求服务商兼容 Responses API。配置完成后收紧权限：

```bash
chmod 600 ~/.codex-providers/new-api/config.toml
```

3. 使用 Codex 登录命令将 API Key 一次性保存到本地。下面的写法不会把密钥明文写进 Shell 历史：

```bash
IFS= read -r -s new_api_secret
printf '%s' "$new_api_secret" |
  CODEX_HOME="$HOME/.codex-providers/new-api" codex login --with-api-key
unset new_api_secret
```

粘贴密钥并按回车后，验证认证状态：

```bash
CODEX_HOME="$HOME/.codex-providers/new-api" codex login status
```

输出应包含 `Logged in using an API key`。密钥只保存在该目录的 `auth.json` 中，不要把密钥写入仓库、README、`config/api_providers.json` 或命令参数。

4. 在 [`config/api_providers.json`](config/api_providers.json) 的 `providers` 数组中加入公共元数据：

```json
{
  "id": "new-api",
  "name": "New API",
  "base_url": "https://example.com/v1",
  "codex_home": "~/.codex-providers/new-api",
  "auth": "api_key",
  "configured": true
}
```

其中 `id` 必须和 `config.toml` 中的 `model_provider` 一致。如果服务商提供经过确认的余额接口，可以额外添加类似 `"usage_path": "/usage"` 的字段。最后重启一次 Control Tower，新服务商就会出现在窗口账号菜单中。首次使用前建议先测试服务商端点与模型是否真实可用。

## 跳转窗口

“窗口标题（可选）”填写 Linux 窗口标题中的文字，程序会先用 `wmctrl -a` 聚焦已有窗口；聚焦失败时再执行 `code --reuse-window <项目路径>`。

## 状态

按钮会按 `Running → Needs input → Ready → Blocked → Done` 循环切换。数据保存在 `data/tasks.json`，不会接触任何账号密码、Cookie 或 token。

## 状态说明

系统进程数量可以自动统计；Codex 每条任务的“需要输入/已完成”等精确状态，需要在 Codex
配置中接入 `scripts/notify_hook.py`（见该文件顶部说明），或者直接点击任务卡片上的“状态”按钮。

## 下一步可扩展

- 接 Codex `notify` 回调，自动把 turn 完成事件写入看板
- 从 codexswitch 的公开状态接口读取当前账号（如果插件提供）
- 增加系统托盘图标、快捷键和任务筛选
