Plugin: plugin-updater
Status: resolved
Category: enhancement

# 04: update 下半链——枢纽族实体同步

**What to build:** `update` 补全实体半链，按三方分类（枢纽实体 × 旧 pin × 新 pin）落地：干净落后（枢纽==旧 pin）直接覆盖；与基线不一致默认保留并标出，交互逐个问「覆盖/保留/看 diff」，`--adopt` 显式声明枢纽无手改后批量覆盖；上游新增装入枢纽；上游已移除逐个确认后连枢纽实体与链接层一起删（非交互须 `--delete-removed`，否则保留并报告）。更新链末尾调用 skill-distributor 的 link 同步链接层，最后打印各 agent 插件副本的刷新命令收尾。

**Blocked by:** 03

- [x] tmp 假枢纽四类场景全绿：干净覆盖 / 不一致保留（`--adopt` 后覆盖）/ 新增装入 / 已移除删除
- [x] 非交互无 `--delete-removed` 时，已移除条目保留且报告标出；有该 flag 才连链接层一起删
- [x] 交互模式下不一致实体可逐个选择 覆盖/保留/看 diff
- [x] 更新链末尾调用链接层同步（注入假 link 验证被调用且时机正确）
- [x] 结束报告含：覆盖/保留/新增/删除清单 + 各 agent 刷新命令
- [x] 真机 check 对「已收敛」tmp 状态退出码为 0（闭环验证）

## Comments

**2026-10-18 验收通过，全部清单项完成（73/73 测试通过，退出码 0；validator --standalone 0 error 0 warning）。**

- **三方分类**（`classify_family_sync` 纯函数 + `test_classify_family_sync_five_actions` 等四测）：枢纽==旧 pin 且 != 新 pin → 干净落后覆盖；枢纽==新 pin → 已同步不动；枢纽 != 旧 pin → 保留（可能手改）；枢纽缺成员（上游新增或一直缺）→ 装入；仅旧 pin 有而枢纽还在 → 删。建基线（无旧树）不覆盖不删、只保留/装入/同步；内容比对复用票 02 的 `compare_tree`（CRLF 归一），专测覆盖「枢纽 CRLF / pin 树 LF 不误判」在 update 分类路径
- **四类场景 tmp 全绿**：`test_sync_hub_yes_mode_policy`（干净覆盖/保留/装入/已移除保留四动作一批断言 + 产物核验）、`test_sync_hub_adopt_overrides_mismatch`、`test_sync_hub_delete_removed_with_flag`（枢纽实体 + `~/.claude/skills` junction 一起删，junction 目标正本核验完好）、`test_cmd_update_full_chain_hub_sync`（全链端到端）
- **删除纪律**：交互逐个确认（`prompt_removals` 注入应答序列测试）；非交互必须 `--delete-removed`，否则保留并标注原因（KEEP_NO_FLAG）；删链接一律 `remove_path_safe`/`os.rmdir` 只摘链接，绝不递归删穿 junction 目标（mklink /J 真夹具验证）；覆盖前发现枢纽目标是 junction 一律拒并报错单项（不写穿链接，其余成员照常，`test_sync_hub_junction_aborts_single_member`）
- **交互逐个选择**：`sync_hub_families` 三个决策函数（不一致逐个 覆盖/保留/看 diff、装入批量一次、已移除逐个）全部可注入，`test_sync_hub_interactive_injected_deciders` 用应答序列断言行为；真实 prompt（`prompt_*`）收 `input_fn` 亦可序列驱动（d 看 diff 重问、非法答重问）
- **旧 pin 树时序**：`plan_updates` 对 bump 条目在下载新树前先下载解包旧 pin 树（bump 完旧 SHA 就没了）；`keep_trees=True` 时计划携带 work/old_tree/new_tree，cmd_update 收尾统一清理；缺省 False 保持票 03 用完即清语义（旧 tarball 拉取失败进 stage=tarball 失败通道）
- **链接层同步时机**（注入假 link 断言）：仅装入/删除（结构变化实际执行）时调用且拿仓库根；纯覆盖不调用；失败不回滚已写入、报告给手动补救命令（`python plugins/skill-distributor/.../skill_distributor.py link`）、退出码 1（`test_sync_hub_link_only_on_structure_change` / `test_sync_hub_link_failure_reported_not_fatal`）；真实实现 = `sys.executable` + `link --root <仓库根>`（cwd 同仓库根）
- **结束报告**：`build_hub_sync_report` 出覆盖/保留（带原因）/装入/删除清单 + 已同步计数 + 错误项 + 链接层状态；`cmd_update` 收尾追加票 02 的副本线刷新命令（`collect_copies` 可注入，测试不碰真机 home）
- **幂等**：枢纽同一状态重跑 sync 全 same 零动作；命令级重跑（pin==head）全部 skip、不下载、不碰枢纽、不调链接层（`test_cmd_update_rerun_skip_zero_hub_actions`）
- **真机验收**：`update --entry mattpocock-skills --yes` 真跑——pin `49dd158d` == head（v1.3.1）→「已最新，跳过」，marketplace/compat 无变更、枢纽零动作、退出码 0（obsidian-skills 无 pin 未触碰，避免建基线写入）；真跑 check 无回归：29 已同步 / 2 与基线不一致（git-guardrails-claude-code、setup-pre-commit，已知措辞漂移）——该 2 项要等下次上游更新（或手工 --adopt）才收敛，属预期。**闭环验证**：真网络下载 pin tarball 搭 tmp 收敛态（31 族实体全装入 tmp 枢纽 + tmp 市场根），`check --root/--hub` 退出码 0、`update --yes` 零动作退出码 0。期间 github.com 间歇断连（已知网络抖动），重跑恢复
- **回归**：`test_plugin_updater.py` 73/73 通过（票 04 新增 27 条）；票 03 既有 cmd 级测试补注 tmp 枢纽/链接层注入（update 全链现在会碰枢纽，测试防误伤真机）；顺手修掉 pin 线报告里「update 子命令后续票交付」的过期措辞
- 交付物：plugin_updater.py（update 六步全链：classify_family_sync / diff_tree_summary / overwrite_entity / remove_path_safe / run_link_sync / prompt_* / sync_hub_families / build_hub_sync_report / plan_updates 扩展 / cmd_update 六步编排 + --adopt/--delete-removed/--hub/--link 旗标）、测试 +27 条、SKILL.md 与 README 更新（update 全链语义与边界）

**2026-10-18 code-review 后语义修订（Status 保持 resolved）：** 上游已移除的删除语义对齐为两态——①交互 tty 逐个 y/n 确认后即可删（无需旗标），`--delete-removed` 视作预先同意、跳过逐个询问；②非交互（无 tty 或 `--yes`）必须显式 `--delete-removed` 才删，否则保留并报告。此前实现虽允许交互逐个确认，但给旗标后仍逐个询问，且 dry-run 预览把删除全部列为「将删」而实际执行（非交互缺旗标）会保留。修订内容：`sync_hub_families` 的默认 `decide_removals` 分两态接线、dry-run 预览与执行按同一旗标规则展示（将删 N（连链接层）/ 将保留 N（非交互且未指定 `--delete-removed`））、KEEP_NO_FLAG 措辞对齐、`--delete-removed` help 与模块 docstring、update-contract.md 交互矩阵与三方分类表、spec.md Implementation Decisions 同步修订。配套交互纪律：`prompt_mismatch` 收紧为只认显式选项词 o/k/d（y/n 不再是覆盖/保留的别名——y 在装入/删除确认里是「确认」语义，混用会误答）。测试 +4 条（交互默认逐个确认即删、交互旗标预同意跳过询问、非交互缺旗标保留/有旗标才删、dry-run 两种预览对齐）+ y 语义回归断言，78/78 通过；顺手修：副本线四路径收集器提为 `default_copy_line_collector` 工厂（cmd_check/cmd_update 共用）、族清单对同一棵树只派生一次（`classify_family_sync` 接受预派生结果）、BOM 常量修为真 U+FEFF 并补「带 BOM 夹具 bump 后 BOM 仍在」回归测试。
