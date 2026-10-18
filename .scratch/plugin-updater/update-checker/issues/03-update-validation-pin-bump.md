Plugin: plugin-updater
Status: ready-for-agent
Category: enhancement

# 03: update 上半链——校验门 + pin bump

**What to build:** `update` 对有新版的条目走完仓库写半链：下载新 SHA tarball → plugin-validator standalone 校验门（非 0 error 中止且零写入）→ bump marketplace.json 的 `pinnedSha`/`pinnedAt` → 同步 compat 文档的外部聚合插件表格。校验门对外部引用式条目**特判「缺 .minimax-plugin」为 N/A**（本地无源码、不分发给 MiniMax——2026-10-18 手动重 pin 已按此先例执行），其余 error 照常阻断。无 pin 条目可 pin 到当时 head 建基线（照走同一校验门）。`--entry` 限定单条目；`--root` 指定 market 仓库根；非交互环境无 `--yes` 拒绝一切变更。

**Blocked by:** 01, 02

- [ ] tmp 假仓库：合法新版本 → pin 双字段 bump + compat 表格同步，产物正确且幂等（重跑无变化）
- [ ] 校验门：注入的假 runner 返回有 error → 全链中止，仓库文件零改动；「缺 .minimax-plugin」error 对外部条目特判为 N/A 不阻断
- [ ] 无 pin 条目建基线走同一校验门，成功后写齐 pinnedRef/pinnedSha/pinnedAt
- [ ] 非交互无 `--yes` 拒绝执行；`--entry` 只影响指定条目
- [ ] 校验门与外部访问为可注入接缝，成功/中止两条路径进回归测试
