# plugin-validator

其他插件**发布前必须运行**的验证工具：静态校验一个插件目录能否被 Claude Code 正确识别、加载、运行。0 error 才能发布。

## 用法

```bash
python skills/plugin-validator/scripts/check_plugin.py <插件目录> [更多目录...]
```

| 选项 | 说明 |
|---|---|
| `--standalone` | 独立插件（不属于本仓库市场）时跳过 marketplace.json 注册检查 |

安装本插件后，直接对 agent 说「发布前验证一下 xxx 插件」即可。

## 检查范围

- `.claude-plugin/plugin.json`：存在、合法 JSON、name / version(x.y.z) / description 必填、name 与目录名一致
- `skills/*/SKILL.md`：frontmatter 齐全、name 与目录名一致、description 非空可触发、SKILL.md 引用的相对路径存在
- `agents/*.md`：frontmatter 齐全且含 name
- `.mcp.json` / `hooks/hooks.json` 等 JSON 组件：可解析
- `scripts/*.py`：UTF-8、语法可编译
- `marketplace.json`：插件已注册、source 指向本目录、与 plugin.json 的 description 一致

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 无 error（warning 需逐条人工确认） |
| 1 | 有 error，禁止发布 |
| 2 | 用法/输入错误 |

完整发布清单见 `skills/plugin-validator/references/checklist.md`。
