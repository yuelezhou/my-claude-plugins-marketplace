Plugin: plugin-updater
Status: ready-for-agent
Category: enhancement

# 05: 文档与台账收尾 + 全量交付校验

**What to build:** 交付前收尾：references 写更新契约文档（三线消费模型、三方分类语义、交互矩阵、退出码、注入接缝、无状态基线设计）；PROMPT-INSTALL.md 把四条「来源待补」（git-guardrails-claude-code、migrate-to-shoehorn、scaffold-exercises、setup-pre-commit）修正归入 mattpocock misc 族并更新族规模描述；compat 文档外部聚合插件节补自动化更新政策（校验门、族派生、删除语义）；AGENTS.md 插件清单表加 plugin-updater 行。

**Blocked by:** 04

- [ ] references 契约覆盖全部对外行为：check/update 语义、三方分类、交互矩阵、退出码、无状态基线
- [ ] PROMPT-INSTALL.md 四条来源待补归入 misc 族（并行手动升级已把族行改为 27 个并注明 resolving-merge-conflicts 移除；归族标注与三类总数仍待补）
- [ ] compat 文档记录：更新流程已由 plugin-updater 自动化 + 政策要点
- [ ] AGENTS.md 插件清单表新增 plugin-updater 行
- [ ] plugin-validator 终检 0 error + 全量回归测试通过（退出码 0）
