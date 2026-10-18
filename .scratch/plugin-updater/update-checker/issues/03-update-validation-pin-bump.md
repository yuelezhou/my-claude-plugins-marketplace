Plugin: plugin-updater
Status: resolved
Category: enhancement

# 03: update 上半链——校验门 + pin bump

**What to build:** `update` 对有新版的条目走完仓库写半链：下载新 SHA tarball → plugin-validator standalone 校验门（非 0 error 中止且零写入）→ bump marketplace.json 的 `pinnedSha`/`pinnedAt` → 同步 compat 文档的外部聚合插件表格。校验门对外部引用式条目**特判「缺 .minimax-plugin」为 N/A**（本地无源码、不分发给 MiniMax——2026-10-18 手动重 pin 已按此先例执行），其余 error 照常阻断。无 pin 条目可 pin 到当时 head 建基线（照走同一校验门）。`--entry` 限定单条目；`--root` 指定 market 仓库根；非交互环境无 `--yes` 拒绝一切变更。

**Blocked by:** 01, 02

- [x] tmp 假仓库：合法新版本 → pin 双字段 bump + compat 表格同步，产物正确且幂等（重跑无变化）
- [x] 校验门：注入的假 runner 返回有 error → 全链中止，仓库文件零改动；「缺 .minimax-plugin」error 对外部条目特判为 N/A 不阻断
- [x] 无 pin 条目建基线走同一校验门，成功后写齐 pinnedRef/pinnedSha/pinnedAt
- [x] 非交互无 `--yes` 拒绝执行；`--entry` 只影响指定条目
- [x] 校验门与外部访问为可注入接缝，成功/中止两条路径进回归测试

## Comments

**2026-10-18 验收通过，全部清单项完成（46/46 测试通过，退出码 0）。**

- **tmp 假仓库全链**（`test_apply_updates_writes_both_files` / `test_apply_updates_idempotent_byte_level` / `test_cmd_update_end_to_end_idempotent`）：合法新版本 → pinnedSha/pinnedAt 双字段 bump + note 内嵌旧 SHA/日期同步 + compat 表格 pin 列同步；marketplace.json 保持 CRLF 与 2 空格缩进、compat 保持 LF；同一批计划重复 apply 与命令级重跑均字节级零改动
- **校验门**（`test_judge_validator_output` / `test_plan_updates_gate_failure_isolated` / `test_cmd_update_gate_failure_aborts_zero_write`）：假 runner 返回 error → 退出码 1、全链中止、仓库文件零改动（混合结果下过了门的条目也不写，全或无）；「缺 .minimax-plugin」error 对外部引用式条目特判 N/A 不阻断（专测覆盖），其余 error 照常阻断；validator 输出无「结果:」行视为不可识别，保守拦截
- **无 pin 建基线**（`test_apply_pin_bump_baseline_creates_metadata` / `test_plan_updates_bump_and_baseline` / `test_cmd_update_entry_filter`）：照走同一校验门，写齐 pinnedRef（`git ls-remote --symref` 取默认分支）/pinnedSha/pinnedAt，键序对齐现有条目；compat 表无行时跳过表格同步不算失败
- **守卫与旗标**（`test_cmd_update_guard_noninteractive` / `test_cmd_update_entry_filter` / `test_cmd_update_dry_run_zero_write` / `test_cmd_update_entry_unknown`）：非交互无 --yes 在任何外部访问前拒绝（退出码 2）；--entry 只影响指定条目；--dry-run 走完整校验门但零写入
- **接缝**：head/版本号/默认分支/tarball/validator 全部可注入，成功与中止两条路径都进回归（`make_update_seams`）
- **真机验收**（网络正常，未硬重试）：`update --entry obsidian-skills --dry-run` 真跑全链——取 head `3ccff5338ea7…`、symref 得默认分支 main、下载 tarball、真 validator --standalone 校验「缺 .minimax-plugin」N/A 豁免后 0 阻断，正确产出建基线计划 `main \`3ccff53\`（2026-10-18，v1.0.1）` 且零写入。过程中发现并修掉一个真问题：codeload 解包顶层目录是 `<repo>-<sha>`，validator 的 name/目录名检查会出假阻断（手动重 pin 先例用 git clone 目录名天然对齐）——新增 normalize_tree_root 在校验门前把树根改名为 plugin.json 的 name（专测覆盖）
- **回归**：`python plugins/plugin-updater/skills/plugin-updater/scripts/test_plugin_updater.py` 46/46 通过退出码 0；validator --standalone 对插件本体 0 error 0 warning；真跑 check 全链无回归
- 交付物：plugin_updater.py（update 半链：plan_updates/apply_updates/cmd_update + 校验门/建基线/表格同步）、测试 +22 条、SKILL.md / README 更新（update 用法与边界）。枢纽实体同步/链接层同步为票 04，未触碰
