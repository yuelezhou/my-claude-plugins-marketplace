Plugin: plugin-updater
Status: resolved
Category: enhancement

# 01: 插件骨架 + check 的 pin 线

**What to build:** 插件本体立起来并交付第一个可用行为：装好后跑 `check`，一条命令看到每条外部聚合条目是否落后于上游——pin SHA vs 上游 head、上游版本号、无 pin 条目报「无基线 + 当前 head」；全部最新退出码 0，有更新或无基线退出码 1。插件完整形态同步到位：双清单、明暗图标、市场注册、SKILL.md 触发词与相邻 skill（skill-distributor / plugin-validator）显式划界。

**Blocked by:** None (can start immediately)

- [ ] 对真实市场跑 check：mattpocock-skills 报「已最新」（pin 已于 2026-10-18 手动重 pin 到 head `49dd158d`/v1.3.1），obsidian-skills 报无基线并附当前 head——「最新」与「有事可报」两条路径都有真机覆盖
- [ ] 退出码语义正确：全部最新 0；有更新或无基线 1
- [ ] 中文 UTF-8 输出在 Windows 终端不乱码
- [ ] plugin-validator 对新插件 0 error（warning 逐条人工确认）
- [ ] 回归测试（内存接缝、外部访问注入假件）覆盖：条目解析、pin 比对、版本号拉取解析、报告生成、退出码

## Comments

**2026-10-18 验收通过，全部清单项完成。**

- **真跑 check**（`python plugins/plugin-updater/skills/plugin-updater/scripts/plugin_updater.py check`）：
  - mattpocock-skills：`pin 49dd158d1076…` = `head 49dd158d1076…`，版本 1.3.1，**已最新**
  - obsidian-skills：无 pin → **无基线**，附当前 head `3ccff5338ea7…`、上游版本 1.0.1
  - 汇总 `1 已最新 / 0 有更新 / 1 无基线 / 0 查询失败`，退出码 **1**
  - 环境到 github.com 的连接间歇性抖动（复跑偶发「查询失败」，也实测退出码 1；单条目失败不中断其余条目）
- **退出码 0 场景**：临时市场根（两条目 pin 到当时 head）真跑 `check --root`，汇总 `2 已最新`，退出码 **0**；同时覆盖了「版本号未知（上游拉取失败，不致命）」的真实路径
- **「有更新」分支**：真机实测被网络抖动挡住（ls-remote 连不上），该分支由注入接缝的回归测试覆盖（假 head → update-available → 退出码 1）
- **回归测试**：`test_plugin_updater.py` 10/10 通过，退出码 0；另做突变测试（pin 比对去掉大小写不敏感、ls-remote 解析改静默取首行）确认对应用例失败、退出码 1——用例非同义反复
- **plugin-validator** `--standalone`：**0 error, 0 warning**，无 warning 需人工确认
- **中文 UTF-8 输出**：Windows + Git Bash 终端实跑无乱码
- 附带产物：README.md（用法速查）；`.claude-plugin/marketplace.json` 追加 plugin-updater 条目（description 与 `.claude-plugin/plugin.json` 一致）
