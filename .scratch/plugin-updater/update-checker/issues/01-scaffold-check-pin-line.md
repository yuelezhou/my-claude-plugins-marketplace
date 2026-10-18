Plugin: plugin-updater
Status: ready-for-agent
Category: enhancement

# 01: 插件骨架 + check 的 pin 线

**What to build:** 插件本体立起来并交付第一个可用行为：装好后跑 `check`，一条命令看到每条外部聚合条目是否落后于上游——pin SHA vs 上游 head、上游版本号、无 pin 条目报「无基线 + 当前 head」；全部最新退出码 0，有更新或无基线退出码 1。插件完整形态同步到位：双清单、明暗图标、市场注册、SKILL.md 触发词与相邻 skill（skill-distributor / plugin-validator）显式划界。

**Blocked by:** None (can start immediately)

- [ ] 对真实市场跑 check：mattpocock-skills 报「已最新」（pin 已于 2026-10-18 手动重 pin 到 head `49dd158d`/v1.3.1），obsidian-skills 报无基线并附当前 head——「最新」与「有事可报」两条路径都有真机覆盖
- [ ] 退出码语义正确：全部最新 0；有更新或无基线 1
- [ ] 中文 UTF-8 输出在 Windows 终端不乱码
- [ ] plugin-validator 对新插件 0 error（warning 逐条人工确认）
- [ ] 回归测试（内存接缝、外部访问注入假件）覆盖：条目解析、pin 比对、版本号拉取解析、报告生成、退出码
