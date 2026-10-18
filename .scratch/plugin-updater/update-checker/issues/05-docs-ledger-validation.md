Plugin: plugin-updater
Status: resolved
Category: enhancement

# 05: 文档与台账收尾 + 全量交付校验

**What to build:** 交付前收尾：references 写更新契约文档（三线消费模型、三方分类语义、交互矩阵、退出码、注入接缝、无状态基线设计）；PROMPT-INSTALL.md 把四条「来源待补」（git-guardrails-claude-code、migrate-to-shoehorn、scaffold-exercises、setup-pre-commit）修正归入 mattpocock misc 族并更新族规模描述；compat 文档外部聚合插件节补自动化更新政策（校验门、族派生、删除语义）；AGENTS.md 插件清单表加 plugin-updater 行。

**Blocked by:** 04

- [x] references 契约覆盖全部对外行为：check/update 语义、三方分类、交互矩阵、退出码、无状态基线
- [x] PROMPT-INSTALL.md 四条来源待补归入 misc 族（并行手动升级已把族行改为 27 个并注明 resolving-merge-conflicts 移除；归族标注与三类总数仍待补）
- [x] compat 文档记录：更新流程已由 plugin-updater 自动化 + 政策要点
- [x] AGENTS.md 插件清单表新增 plugin-updater 行
- [x] plugin-validator 终检 0 error + 全量回归测试通过（退出码 0）

## Comments

**2026-10-18 验收通过，五项清单全过（validator `--standalone` 0 error 0 warning；回归测试 73/73 退出码 0；文档旗标逐一对照 `--help` 无出入）。**

- **references 契约**：新建 `plugins/plugin-updater/skills/plugin-updater/references/update-contract.md`，覆盖三线消费模型（pin / 枢纽族实体 / 其他市场副本：载体、数据来源、工具动作）、check 三段报告与四种结论处置口径、update 六步链与「先计划后写入全或无」、三方分类五动作表、校验门（「缺 .minimax-plugin」外部引用式条目 N/A 特判、无「结果:」汇总行保守拦截）、交互矩阵（8 旗标全表 + 交互/`--yes`/`--dry-run` 三运行形态的决策默认）、退出码全表、无状态基线设计（pin 即基线、不回写台账）、CRLF 归一、注入接缝（effect / 纯决策 / 交互 / 编排四层函数清单与测试点定位）。SKILL.md check/update 两节重写为「处置口径 + 执行规则」并指向 references（frontmatter 未动）。真机口径修正：ZCode 副本实际已是 1.3.1 @ `49dd158d`（spec 里 v1.2.3 @ `3cca18b3` 是升级前旧况，以真机为准）
- **PROMPT-INSTALL.md**：四条「来源待补」（git-guardrails-claude-code、migrate-to-shoehorn、scaffold-exercises、setup-pre-commit）经 1.3.1 缓存 `skills/misc/` 实测确认属 mattpocock misc 分类，合并进族行并删除四行；族行计数改「engineering + productivity + misc 三类约 31 个」并写清口径——27 = 插件清单 `.claude-plugin` 的 skills 数组（只注册 engineering+productivity），31 = 三类目录全口径（plugin-updater 族派生口径，真机 check 实测族成员恰 31 个）
- **compat 文档**：「外部聚合插件」节更新流程行改为「已由 plugin-validator 同仓库的 plugin-updater 插件自动化」+ 三句政策要点（bump 前必过 `--standalone` 校验门、族由 pin 处上游目录清单动态派生、已移除 skill 须确认后连枢纽实体与链接层删除）+ 指向契约文档；入库流程与其余内容未动
- **AGENTS.md**：插件清单表 skill-distributor 行后新增 plugin-updater 行
- **全量交付校验**：`check_plugin.py plugins/plugin-updater --standalone` → `0 error, 0 warning`（退出码 0）；`test_plugin_updater.py` → 73/73 通过（退出码 0）；`--help` 三级输出与文档出现的旗标（`--root`/`--hub`/`--link`/`--entry`/`--yes`/`--dry-run`/`--adopt`/`--delete-removed`）逐一核对全部一致、无未知旗标；真跑一次 check 对照契约：obsidian-skills 无基线、mattpocock-skills 已最新、枢纽 29 同步 / 2 与基线不一致（git-guardrails-claude-code、setup-pre-commit，已知措辞漂移）、副本线报 ZCode 1.3.1 + 刷新命令，退出码 1 符合语义
