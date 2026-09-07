# 账号与 API 服务商切换

最后更新：2026-09-07

## 已实现

Control Tower 同时支持两类 Codex 认证来源：

- Codex Switch 管理的 ChatGPT Plus 订阅账号；
- 手动选择的一个或多个第三方兼容 Responses API，当前配置示例显示为“备用 API”。

备用 API 不会在 Plus 额度用完时静默接管。用户必须在指定 VS Code 窗口的账号菜单中手动选择，再点“切换并聚焦”。切回任意 Plus 账号时，目标窗口先恢复默认 Codex 目录，再交给 Codex Switch 激活订阅账号。

## 隔离方式

- 现有 Plus/Codex Switch 继续使用 `~/.codex`，不修改其 `config.toml` 和 `auth.json`。
- 备用 API 使用权限受限的独立目录 `~/.codex-heju`。
- VS Code 桥接在 `~/.codex-window-manager/providers/` 中只保存“某工作区选择了哪类服务商”，不保存密钥。
- 桥接在目标 VS Code 扩展宿主启动时应用独立 `CODEX_HOME`，所以一个窗口可以用备用 API，其他窗口仍保持各自的 Plus 账号。

## 安全与兼容性

- API Key 仅由 Codex 登录流程写入 `~/.codex-heju/auth.json`，不得进入仓库、日志、文档或界面。
- 目录权限为 `700`，配置与认证文件权限为 `600`。
- 第三方服务商可以看到通过该窗口发出的提示、上下文和工具交互，因此只应用于允许发送给该服务商的项目。
- 当前本机 Codex CLI 0.114.0 不接受 `model_reasoning_effort = "ultra"`，备用配置使用其支持的最高档 `xhigh`。
- 中转站余额不与 Plus 额度混合计算，界面仅标注“按量计费”；余额以服务商后台为准。
- 目前中转站没有发现可确认的通用余额 API；后续可按接口配置增加余额查询。Codex 本地会话中的 token 使用可以按独立 `CODEX_HOME` 统计，但不等于服务商账单余额。

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
