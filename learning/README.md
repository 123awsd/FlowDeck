# 领域知识资产

每个领域使用独立目录保存经过来源核验、人工审查和版本化的 Curriculum。运行进度不放在这里，而是保存在被 Git 忽略的 `data/`。

当前状态：

- `domains/vla/`：VLA Curriculum v1，结构校验通过，状态为 `reviewed_draft`，等待用户人工确认。
- `domains/vln/`：待导入。
- `domains/wam/`：待导入。

导入新版本后运行：

```bash
PYTHONPATH=src python3 scripts/validate_curriculum.py learning/domains/<领域>
```
