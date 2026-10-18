Plugin: plugin-updater
Status: ready-for-agent
Category: enhancement

# 04: update 下半链——枢纽族实体同步

**What to build:** `update` 补全实体半链，按三方分类（枢纽实体 × 旧 pin × 新 pin）落地：干净落后（枢纽==旧 pin）直接覆盖；与基线不一致默认保留并标出，交互逐个问「覆盖/保留/看 diff」，`--adopt` 显式声明枢纽无手改后批量覆盖；上游新增装入枢纽；上游已移除逐个确认后连枢纽实体与链接层一起删（非交互须 `--delete-removed`，否则保留并报告）。更新链末尾调用 skill-distributor 的 link 同步链接层，最后打印各 agent 插件副本刷新命令收尾。

**Blocked by:** 03

- [ ] tmp 假枢纽四类场景全绿：干净覆盖 / 不一致保留（`--adopt` 后覆盖）/ 新增装入 / 已移除删除
- [ ] 非交互无 `--delete-removed` 时，已移除条目保留且报告标出；有该 flag 才连链接层一起删
- [ ] 交互模式下不一致实体可逐个选择 覆盖/保留/看 diff
- [ ] 更新链末尾调用链接层同步（注入假 link 验证被调用且时机正确）
- [ ] 结束报告含：覆盖/保留/新增/删除清单 + 各 agent 刷新命令
- [ ] 真机 check 对「已收敛」tmp 状态退出码为 0（闭环验证）
