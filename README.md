# Codex Control Tower

一个基于 PyQt5/Qt 的本地浮动任务看板，适合配合 VS Code 的 Codex 和 codexswitch 使用。界面使用系统 Qt5，并直接连接 Fcitx5/Rime，支持在“今日待办”输入框中顺滑输入中文。

## 启动

```bash
./launch.sh
```

窗口默认置顶并折叠为悬浮球；展开后可以查看 Codex 状态、账号额度、切换账号、管理今日待办，并跳转到对应的 VS Code 项目。

## 等待学习

“等待学习”会按 3、5、10 或 20 分钟生成有边界的机器人前沿学习包。论文列表来自最新 arXiv `cs.RO` 条目，卡片保留发布日期和原文链接；DeepSeek 仅负责生成“解决什么、相对已有工作的增量、为什么值得看”的短摘要。API 失败时会自动回退到原始摘要。

在项目目录创建不提交到 Git 的 `.env`：

```bash
DEEPSEEK_API_KEY=你的密钥
```

面板每 5 秒自动扫描桌面上的 VS Code 窗口。它会读取窗口标题，并结合 VS Code 的
`workspaceStorage` 自动显示项目文件夹和绝对路径（例如 `/home/uav/map_VLN`）。
“聚焦”可以直接切换到对应窗口，“建任务”会自动把该窗口绑定到一条任务。

每个窗口卡片还提供账号菜单。先选择目标账号，卡片会显示“待切换”，再点击“切换并聚焦”即可完成切换。首次安装 `vscode-bridge` 后，需要让每个
已打开的 VS Code 窗口执行一次“开发人员: 重新加载窗口”；之后面板会让目标窗口调用
Codex Switch、重启该窗口的扩展宿主，并重新打开 Codex 侧栏。

## 跳转窗口

“窗口标题（可选）”填写 Linux 窗口标题中的文字，程序会先用 `wmctrl -a` 聚焦已有窗口；聚焦失败时再执行 `code --reuse-window <项目路径>`。

## 状态

按钮会按 `Running → Needs input → Ready → Blocked → Done` 循环切换。数据保存在同目录的 `tasks.json`，不会接触任何账号密码、Cookie 或 token。

## 状态说明

系统进程数量可以自动统计；Codex 每条任务的“需要输入/已完成”等精确状态，需要在 Codex
配置中接入 `notify_hook.py`（见该文件顶部说明），或者直接点击任务卡片上的“状态”按钮。

## 下一步可扩展

- 接 Codex `notify` 回调，自动把 turn 完成事件写入看板
- 从 codexswitch 的公开状态接口读取当前账号（如果插件提供）
- 增加系统托盘图标、快捷键和任务筛选
