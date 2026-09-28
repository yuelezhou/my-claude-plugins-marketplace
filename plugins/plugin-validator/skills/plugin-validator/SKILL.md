---
name: plugin-validator
description: |
  插件发布前验证工具——其他插件在发布/提交前必须用它跑一遍验证。
  静态校验一个 Claude Code 插件能否被正确加载运行：plugin.json 必填字段与命名、
  skills/*/SKILL.md frontmatter（name 与目录一致、description 可触发）、agents/*.md、
  .mcp.json / hooks.json 等 JSON 组件、scripts/*.py 语法、SKILL.md 引用的相对路径、
  marketplace.json 注册与两处 description 一致性。
  触发：用户说"验证插件 / 发布前检查 / check plugin / 插件能不能正确运行 /
  pre-release 校验"，或本仓库任何插件改完准备提交、发布、打 tag 之前。
  不用于：排查已安装插件的运行时报错（那是 runtime 调试）、评估 skill
  产出内容的质量（那是各 skill 自己的 check 脚本，如 check_anki_cards.py）。
displayNames:
  zh-Hans: "插件发布验证"
---

# Plugin Validator

验证一个插件目录能被 Claude Code 正确识别、加载、运行。**本仓库规则（见根目录 AGENTS.md）：任何插件在提交/发布前必须跑本 skill 的校验脚本，0 error 才能发布。** 它验证的是「结构正确、能加载」，不是「功能符合预期」——后者靠各插件自己的测试与人工冒烟。

## Procedure

1. 找到插件根（含 `.claude-plugin/plugin.json` 的目录），跑静态校验：

   ```bash
   python "<skill目录>/scripts/check_plugin.py" "<插件目录>"
   ```

   多个插件可一次传入。独立插件（不属于本仓库市场）加 `--standalone` 跳过注册检查。

2. 修错闭环：
   - **ERROR 必须修**，改完重跑直到 0 error。高频错误：plugin.json 缺字段 / 版本不是 x.y.z、SKILL.md frontmatter name 与目录名不一致、Python 脚本语法错、插件没注册进 marketplace.json、source 路径指错。
   - **WARNING 逐条人工确认**。最常见：plugin.json 与 marketplace.json 的 description 不一致（本仓库两处靠手工同步，曾漂移过）；SKILL.md 提到的外部路径（如指向其他插件脚本的绝对路径）可忽略。

3. 脚本之外的交叉验证（本机有 claude CLI 就做；命令不存在则跳过并在交付说明里注明）：

   ```bash
   claude plugin validate "<插件目录>"   # 官方校验器，结果以它为准
   claude --plugin-dir "<插件目录>"      # 启动后确认 skills/commands/agents 能被列出并调用
   ```

4. 全绿后按 AGENTS.md 的规则收尾：确认 marketplace.json 已注册、description / version 两处一致，再提交。

完整检查项清单见 `references/checklist.md`。
