Plugin: plugin-updater
Status: ready-for-agent
Category: enhancement

# 02: check 补全——枢纽同步线与其他市场副本线

**What to build:** check 报告升级为三线全貌。除 pin 线外：① 枢纽线——下载 pin 处 tarball，动态派生族成员（engineering/productivity/misc 三类，deprecated/in-progress 永不装入），报告每个族实体相对 pin 基线的同步状态（已同步 / 落后 / 与基线不一致）；② 其他市场副本线——读各 agent 的插件安装记录，对来自其他市场的已装副本（如 ZCode 里来自 anthropics 官方市场的 mattpocock）报版本落后并附刷新命令（只打印不代跑）；未装外部插件的 agent 报「未安装」不报错。

**Blocked by:** 01

- [ ] 真跑 check：枢纽族实体报「已同步」（2026-10-18 已随手动升级收敛到 1.3.1），数量与上游族清单一致——含新增的 implement-spec/pr/retro、不含已移除的 resolving-merge-conflicts；「与基线不一致」分类由 tmp 夹具覆盖
- [ ] 族派生动态正确：以 pin 处上游目录清单为准，deprecated/in-progress 排除
- [ ] ZCode 副本线报出 v1.2.3 @ `3cca18b3`（官方市场来源）+ 两条刷新命令
- [ ] Claude Code / MiniMax 侧未装外部插件 → 报「未安装」，不报错
- [ ] 回归测试补：族派生（假目录树）、枢纽三方状态判定（tmp 枢纽 + 假 tarball）、副本线报告生成
