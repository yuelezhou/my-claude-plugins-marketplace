# Issue tracker：本地 Markdown

本仓库的 issue 与 spec 以 markdown 文件形式放在 `.scratch/` 下。
**本仓库的主要产出物是插件，插件之间功能独立、互不关联——所有票必须标明归属。**

## 分域约定

- 插件域：`.scratch/<插件名>/<feature-slug>/` —— 某个插件的功能 / 缺陷 / 规格
- 仓库域：`.scratch/market/<主题>/` —— 跨插件或仓库级事务（marketplace 配置、分发架构、AGENTS 政策、发布流程）
- 插件名用插件目录名（`word-frequency`、`skill-distributor`…）；拿不准归哪个插件 = 大概率属于仓库域

## 文件约定

- 一个 feature 一个目录：`.scratch/<域名>/<feature-slug>/`
- 规格文件是 `spec.md`；实施票一票一文件：`issues/NN-<slug>.md`，从 `01` 起编号——绝不合并成一个大票文件
- 每个文件顶部写元数据行（正文第一行之前）：
  - `Plugin: <插件名|market>` —— 必填，归属标识
  - `Status: <角色字符串>` —— triage 状态（见 `triage-labels.md`）
- 讨论与过程记录追加到文件底部 `## Comments` 标题下
- 查某插件的全部票：看目录 `.scratch/<插件名>/`，或 `grep -rl "Plugin: <插件名>" .scratch/`

## 当 skill 说「publish to the issue tracker」

在 `.scratch/<域名>/<feature-slug>/` 下新建文件（目录不存在则创建），`Plugin:` 行必填。

## 当 skill 说「fetch the relevant ticket」

读引用路径的文件；用户通常直接给路径或编号。

## Wayfinding 操作

`/wayfinder` 使用。map 是总图，每个决策票一个子文件。

- **Map**：`.scratch/<域名>/<effort>/map.md` —— Notes / Decisions-so-far / Fog 正文，头部同样写 `Plugin:`
- **子票**：`.scratch/<域名>/<effort>/issues/NN-<slug>.md`，从 `01` 起编号，问题写在正文；`Type:` 行记类型（`research`/`prototype`/`grilling`/`task`），`Status:` 行记 `claimed`/`resolved`
- **Blocking**：顶部 `Blocked by: NN, NN` 行；所列文件全部 `resolved` 即解锁
- **Frontier**：扫描该 effort 的 `issues/` 下 open、无阻塞、未 claim 的票，编号最小者优先
- **Claim**：开工前置 `Status: claimed` 并保存
- **Resolve**：答案追加到 `## Answer` 标题下，置 `Status: resolved`，并在 map.md 的 Decisions-so-far 追加上下文指针
