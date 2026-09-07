# 账号与 API 服务商切换

最后更新：2026-09-07

## 已实现

Control Tower 同时支持两类 Codex 认证来源：

- Codex Switch 管理的 ChatGPT Plus 订阅账号；
- 手动选择的一个或多个第三方兼容 Responses API，当前配置示例显示为“备用 API”。

备用 API 不会在 Plus 额度用完时静默接管。用户必须在指定 VS Code 窗口的账号菜单中手动选择，再点“切换并聚焦”。切回任意 Plus 账号时，目标窗口先恢复默认 Codex 目录，再交给 Codex Switch 激活订阅账号。

## 隔离方式

- 现有 Plus/Codex Switch 继续使用 `~/.codex`，不修改其 `config.toml` 和 `auth.json`。
- 每个备用 API 使用权限受限的独立 `CODEX_HOME`，例如 `~/.codex-heju` 或 `~/.codex-providers/<provider>`。
- VS Code 桥接在 `~/.codex-window-manager/providers/` 中只保存“某工作区选择了哪类服务商”，不保存密钥。
- VS Code 的同一个主进程会共享扩展启动环境，不能可靠地只改单个窗口的 `CODEX_HOME`。因此切到 API 时，Control Tower 会正常关闭目标窗口，再以独立 VS Code 用户数据目录和对应 `CODEX_HOME` 重开该项目。其他 Plus 窗口不受影响。
- 启动时直接调用 VS Code Electron 主进程并清理继承的 VS Code IPC 环境，避免命令被已有 Plus 实例接管。桥接只有在读到的实际进程环境与路由一致时，才会向界面报告 API 服务商。
- 切回 Plus 时会用默认 VS Code 用户目录重开项目，随后自动调用 Codex Switch 激活用户选中的订阅账号。

## 安全与兼容性

- API Key 仅保存在对应服务商的本地 `auth.json`，不得进入仓库、日志、文档或界面。
- 目录权限为 `700`，配置与认证文件权限为 `600`。
- 第三方服务商可以看到通过该窗口发出的提示、上下文和工具交互，因此只应用于允许发送给该服务商的项目。
- 当前本机 Codex CLI 0.114.0 不接受 `model_reasoning_effort = "ultra"`，备用配置使用其支持的最高档 `xhigh`。
- 中转站余额不与 Plus 额度混合计算，界面仅标注“按量计费”；余额以服务商后台为准。
- 用量接口按服务商配置。当前 `fastlab-api` 的 `/v1/usage` 会读取剩余量；Heju 没有发现可确认的通用余额 API，因此显示“暂无用量接口”。Codex 本地会话中的 token 使用可以按独立 `CODEX_HOME` 统计，但不等于服务商账单余额。

## 涉及文件

- `src/codex_control_tower/ui.py`
- `config/api_providers.json`（只放接口元数据，不放密钥）
- `extensions/vscode-bridge/extension.js`
- `extensions/vscode-bridge/package.json`
- `extensions/vscode-bridge/extension.vsixmanifest`
- 本地非仓库配置：`~/.codex-heju/`

## 下一步

- 如果服务商提供稳定的余额查询 API，再在不上传项目数据的前提下增加余额展示。
- 增加接口时，在 `config/api_providers.json` 增加一个条目，并为它准备独立的 `CODEX_HOME`；不要复用 Plus 的 `~/.codex`。
- 对第三方端点做小型可用性检查，但不实现失败后的静默自动切换。
