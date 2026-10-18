Plugin: plugin-updater
Status: resolved
Category: enhancement

# 02: check 补全——枢纽同步线与其他市场副本线

**What to build:** check 报告升级为三线全貌。除 pin 线外：① 枢纽线——下载 pin 处 tarball，动态派生族成员（engineering/productivity/misc 三类，deprecated/in-progress 永不装入），报告每个族实体相对 pin 基线的同步状态（已同步 / 落后 / 与基线不一致）；② 其他市场副本线——读各 agent 的插件安装记录，对来自其他市场的已装副本（如 ZCode 里来自 anthropics 官方市场的 mattpocock）报版本落后并附刷新命令（只打印不代跑）；未装外部插件的 agent 报「未安装」不报错。

**Blocked by:** 01

- [ ] 真跑 check：枢纽族实体报「已同步」（2026-10-18 已随手动升级收敛到 1.3.1），数量与上游族清单一致——含新增的 implement-spec/pr/retro、不含已移除的 resolving-merge-conflicts；「与基线不一致」分类由 tmp 夹具覆盖
- [ ] 族派生动态正确：以 pin 处上游目录清单为准，deprecated/in-progress 排除
- [ ] ZCode 副本线报出 v1.2.3 @ `3cca18b3`（官方市场来源）+ 两条刷新命令
- [ ] Claude Code / MiniMax 侧未装外部插件 → 报「未安装」，不报错
- [ ] 回归测试补：族派生（假目录树）、枢纽三方状态判定（tmp 枢纽 + 假 tarball）、副本线报告生成

## Comments

**2026-10-18 验收通过，全部清单项完成（两处现实偏差见下）。**

- **真跑 check**（`python plugins/plugin-updater/skills/plugin-updater/scripts/plugin_updater.py check`）：
  - **枢纽线**：mattpocock 族派生 **31 个成员**（engineering 20 / productivity 7 / misc 4），含 implement-spec/pr/retro、不含 resolving-merge-conflicts，与 pin `49dd158d` 处上游目录清单一致；codeload 通道全程可用，真跑稳定复现
  - 比对结果 **29 已同步 / 2 与基线不一致 / 0 缺失**——2 个不一致（git-guardrails-claude-code、setup-pre-commit）经 diff 确认是**真实漂移**：枢纽副本与 pin 基线在各差一句措辞（疑似官方市场 1.3.1 与上游 main 的微小差异），check 按设计只报不一致、不做落后/手改区分，留待 update/人工处理
  - **CRLF 发现**：真跑首签名 31/31 全部「不一致」，诊断证实是行尾噪音（codeload 基线 LF、Windows 安装链落盘 CRLF，文件集合与行内容完全一致）——比对已改为行尾归一（`\r\n`→`\n`），归一后真机收敛状态如实呈现；该语义进回归测试（tmp 夹具：仅行尾不同 → 已同步），票 04 三方分类将复用同一比对函数
  - **副本线**：ZCode 报 `1.3.1 @ 49dd158d1076…`（来源市场 claude-plugins-official）+ 两条刷新命令（`zcode plugins marketplace update claude-plugins-official` / `zcode plugins plugin update mattpocock-skills@claude-plugins-official`）；Claude Code / MiniMax / obsidian-skills 全部报「未安装」（MiniMax 附「原生读枢纽，无独立安装记录」说明），无报错
  - **pin 线**：本次真跑赶上 github.com:443 不可达窗口（无代理；codeload.github.com 的 CDN 通道不受影响，全程可用），mattpocock ls-remote 复跑多次均「查询失败」、退出码 1、不崩、不中断其余条目——可读错误路径真机覆盖；同一跑里 obsidian 的 ls-remote + raw 版本号通道真机成功（head `3ccff533`、版本 1.0.1、无基线）
- **两处现实偏差（票面预期被并行会话超越，机制不受影响）**：
  1. ZCode 副本已非 v1.2.3 @ `3cca18b3`——维护者手动收敛链把 ZCode 副本也刷到了 1.3.1（安装记录 `updatedAt` 2026-10-18T05:04:54Z，sha 已是 `49dd158d…`）；「报 v1.2.3 @ 3cca18b3 + 两条命令」的报告形态由 tmp 夹具用例覆盖（版本/来源市场/上游 sha 逐项断言）
  2. 「枢纽族实体报已同步」实测为 29/31 已同步 + 2 个真实措辞漂移（见上），非工具误报
- **回归测试**：`test_plugin_updater.py` **24/24 通过**（票 01 的 10 例 + 本票 14 例），退出码 0；族派生（tmp 假目录树：三分类 + deprecated/in-progress + 散文件排除）、枢纽三方状态（tmp 枢纽 + tmp 假 tarball：已同步/不一致/缺失/枢纽目录整个缺失/CRLF 归一）、编排（无 pin 跳过、tarball 下载失败 → hub-error 可读错误 + 工作目录清理）、副本线（ZCode 列表格式/Claude 字典格式、本仓库市场识别含正斜杠路径归一、缺安装文件 → 未安装、刷新命令）、报告与退出码（枢纽差异/失败 → 1，副本线不影响退出码）全覆盖
- **突变测试**：三处决策点突变全部变红——派生扫全部分类（deprecated 泄漏）、枢纽比对恒判已同步、ZCode own-market 识别失效；其中第三处首测未变红，暴露 ZCode 侧 own-market 分支无覆盖，已补用例后复测变红
- **plugin-validator** `--standalone`：**0 error, 0 warning**
- 退出码语义扩展：0=全部最新且枢纽全同步；1=有更新/无基线/查询失败/枢纽有差异；副本线只报告不影响退出码（外部市场副本是常驻消费线，非 check 可消除的漂移）
