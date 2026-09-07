# 账号与 API 服务商切换

最后更新：2026-09-07

## 已实现（安全路由 v2）

Control Tower 同时支持两类 Codex 认证来源：

- Codex Switch 管理的 ChatGPT Plus 订阅账号；
- 手动选择的一个或多个第三方兼容 Responses API，当前配置示例显示为“备用 API”。

备用 API 不会在 Plus 额度用完时静默接管。用户必须在指定 VS Code 窗口的账号菜单中手动选择，再点“切换并聚焦”。切回任意 Plus 账号时，目标窗口先恢复默认 Codex 目录，再交给 Codex Switch 激活订阅账号。

## 隔离方式

- 现有 Plus/Codex Switch 继续使用 `~/.codex`，不修改其 `config.toml` 和 `auth.json`。
- 每个备用 API 使用权限受限的独立 `CODEX_HOME`，例如 `~/.codex-heju` 或 `~/.codex-providers/<provider>`。
- 每个 Plus/API 运行时都拥有完整、独立的 `CODEX_HOME`。严禁共享或链接 `state_*.sqlite`、WAL、IPC、锁、日志、会话目录和附件目录。
- 路由身份由 `vscode.env.sessionId + workspace fingerprint + extension host PID` 组成，而不是只用文件夹路径；同一文件夹开两个窗口时，聚焦后的目标宿主 PID 决定请求归属。
- VS Code 完全关闭后，旧窗口会话身份失效；下次新开默认回到订阅，避免把旧 API 路由误套到同路径的新窗口。
- API 切换保留原 VS Code 窗口、用户目录、扩展、布局和打开文件，只重启目标扩展宿主中的 Codex `app-server` 子进程。
- 本地启动补丁只把目标 `CODEX_HOME` 传给 Codex 子进程，不改模型、服务商配置或认证内容。服务商行为仍由该运行时自己的 `config.toml` 和 `auth.json` 决定。
- 切换采用 `准备 → 写入路由 → 重启子进程 → 读取 /proc 验证 → 提交界面状态`。实际目录不符或超时会回滚路由并显示失败，不允许“界面显示 API、实际仍用 Plus”。

## 安全与兼容性

- API Key 仅保存在对应服务商的本地 `auth.json`，不得进入仓库、日志、文档或界面。
- 目录权限为 `700`，配置与认证文件权限为 `600`。
- 第三方服务商可以看到通过该窗口发出的提示、上下文和工具交互，因此只应用于允许发送给该服务商的项目。
- Codex 扩展补丁只支持经过审核的确切版本和 SHA-256。安装前同时检查版本、文件哈希和唯一启动签名，临时文件通过 VS Code 自带 Node 运行时语法检查后原子替换；不兼容时只禁用 API 切换，Plus/Codex Switch 保持可用。
- 原始扩展最多保留 3 份本地备份；回执、宿主标记和临时 IPC 保留不超过 24 小时，失效会话路由保留不超过 7 天。
- 当前本机 Codex CLI 0.114.0 不接受 `model_reasoning_effort = "ultra"`，备用配置使用其支持的最高档 `xhigh`。
- 中转站余额不与 Plus 额度混合计算，界面仅标注“按量计费”；余额以服务商后台为准。
- 用量接口按服务商配置。当前 `fastlab-api` 的 `/v1/usage` 会读取剩余量；Heju 没有发现可确认的通用余额 API，因此显示“暂无用量接口”。Codex 本地会话中的 token 使用可以按独立 `CODEX_HOME` 统计，但不等于服务商账单余额。

## 涉及文件

- `src/codex_control_tower/ui.py`
- `src/codex_control_tower/provider_routing.py`
- `config/api_providers.json`（只放接口元数据，不放密钥）
- `extensions/vscode-bridge/extension.js`
- `extensions/vscode-bridge/package.json`
- `extensions/vscode-bridge/extension.vsixmanifest`
- 本地非仓库配置：`~/.codex-heju/`

## 对话历史

- Control Tower 以只读方式扫描默认目录和每个 API 目录的 `sessions/`，按项目合并展示，并标注来源。
- 点击另一个 API 运行时所属的历史时，先通过上述事务切换到所属运行时，验证后再打开。
- 不向某个正在运行的 Codex 实例挂载另一运行时的数据库，也不复制正在写入的 SQLite/WAL。
- Plus 历史目前只能可靠识别为“订阅”，Codex 本地记录没有稳定保存具体 Plus 账号所有者；从 API 打开 Plus 历史时会选择当前可用的订阅账号。

## 新增服务商

- 如果服务商提供稳定的余额查询 API，再在不上传项目数据的前提下增加余额展示。
- 增加接口时，在 `config/api_providers.json` 增加一个条目，并为它准备独立的 `CODEX_HOME`；不要复用 Plus 的 `~/.codex`。
- 对第三方端点做小型可用性检查，但不实现失败后的静默自动切换。
