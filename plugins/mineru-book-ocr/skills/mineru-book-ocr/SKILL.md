---
name: mineru-book-ocr
description: 把 PDF 书籍按 200 页拆分、用 computer use 驱动 MinerU 桌面版批量提交云端解析、把产物收进书籍工作区、再归档成坚果云读书笔记（合并原文 / 按章节拆分 / 写导读与 TL;DR / 生成 Anki 卡片）的完整流水线。当用户提到「拆分书籍 / 切分 PDF / 每 200 页切一份 / 提交 mineru / 用桌面版 mineru 跑 OCR / 批量解析成 markdown / 把解析产物收进 minuer_u未处理 / 接着跑下一批书」，或提到「归档 / 导入读书笔记 / 放进坚果云 / 合并 full.md / 按章节拆分原文 / 写某章的读书笔记导读 / 给某章出 Anki 卡」且对象是 MinerU 产物或书籍 OCR 时，都应当使用本 skill——即使用户没有明说「拆分」或「提交」这些词。也适用于排查这条链路上的失败：切分后页数不对、MinerU 界面读不到、文件对话框选不中多个文件、任务卡在某个状态、产物没落到预期位置、章节拆分失败。
---

# 书籍 → MinerU OCR → 读书笔记 流水线

这条链路有五段：**拆分 → 提交 → 等待 → 收集 → 归档**。每段都有一个容易踩的坑，本文把坑和验证方法写清楚，脚本放在 `scripts/`。

每一步的输入、输出产物与验收标准（含数值判据）见 `references/pipeline-contracts.md`。速查：

| 阶段 | 输入 | 产物 | 验收（不过不进下一步） | 校验 |
|---|---|---|---|---|
| 1 拆分 | 整本 PDF/EPUB | `待处理\*_N_A-B.pdf`（EPUB 先转 PDF 入 `原书\`） | 页数守恒、区间自洽且连续；EPUB 件康熙部首=0、无越界 | `verify_splits.py` / `epub_to_pdf.py --verify` |
| 2 提交 | 分片 + 开着的应用 | `mineru.db` 新任务记录 | 记录数==计划数、路径正确、无重复 | 查 `taskData` |
| 3 等待 | 任务库 | 全部任务终态 | failed==0（有则列出 err_msg），extracted==total | `wait_and_collect.py` |
| 4 收集 | `C:\Users\yuele\MinerU\` 产物目录 | `minuer_u未处理\<分片>.pdf-<uuid>\` | full.md 非空、图片引用零缺失、4 类附属文件齐、康熙部首=0 | `wait_and_collect.py --collect --verify` |
| 5 归档 | 同一本书的各分片产物 | 笔记库书目录（原文/章节/images/笔记/anki_cards/_work zip） | 脚本校验全过 + zip 完整（过前不删源分片）+ 笔记三段式合规 + `check_anki_cards.py` 0 error | `archive_to_notes.py` / `check_anki_cards.py`（外部） |

工作区布局（默认为 `D:\垃圾文件夹`，可在对话里替换）：

| 目录 | 含义 |
|---|---|
| `待处理\` | 待送解析的分片 PDF（拆分的落点） |
| `原书\` | 整本原件（PDF/EPUB），已拆分的整本也放这里 |
| `minuer_u未处理\` | MinerU 解析产物，每份一个目录：`<分片名>.pdf-<uuid>\` |
| `英中对照成品\` | 下游翻译产物 |

归档的目的地在另一个地方：坚果云笔记库 `C:\Users\yuele\Documents\坚果云\文件\个人文件\笔记\编程读书笔记\`，见第 5 段。

## 0. 先确认三件事

1. **MinerU 单文件硬限制：≤ 200 页 且 ≤ 200MB**（云端服务限制，超限提交直接失败；单日上限 5000 份、单次上传最多 20 个文件，完整配额见 `references/mineru-desktop-internals.md`），所以按 200 页切。
2. **系统 Python 可用、项目 venv 可能不可用**。`py_pdf_book_helper` 的 `.venv` 如果是在 WSL 里建的（`pyvenv.cfg` 里 `home = /usr/bin`），在 Windows 下执行会报 `did not find executable`。用系统 Python（本机 `C:\Python313\python.exe`，已带 `pypdf`）。
3. **MinerU 桌面版是云端客户端**——它自己带登录态（`C:\Users\yuele\MinerU\config.json`），不依赖 `py_pdf_book_helper\.env` 里的 API key。所以桌面版这条路通常比走官方 API 更省事。详见 `references/mineru-desktop-internals.md`。

## 1. 拆分

用现成脚本，不要重写：

```bash
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
python "D:\code\toy_and_tools\py_pdf_book_helper\scripts\pdf_tools\pdf_spliter.py" "<整本 PDF 路径>" "<输出目录>"
```

命令行入口调用的是 `split_even(src, output_dir, max_pages=200)`（脚本第 43 行）。

**它是「均分」而不是「硬切 200 页」**：先算 `ceil(总页数/200)`，再让每份尽量相等。363 页会切成 2×182，而不是 200+163。这满足 MinerU 的上限要求，但如果用户要求的是严格 200 页一份，得改成脚本里的 `split1()` 那种步长切法——**先跟用户确认是哪一种**，两者结果不同。

命名规律：`<原文件名去扩展名>_<序号>_<起始页>-<结束页>.pdf`（页码从 1 开始）。

拆完必须验证页数守恒——漏页在这里看不出来，到翻译阶段才发现就晚了：

```bash
python scripts/verify_splits.py --parts "<分片目录>" --source "<整本 PDF 目录>"
```

它会逐本核对：分片页数之和 == 原书页数，且分片区间首尾相接、无重叠。

### 如果原件是 EPUB

MinerU 只吃 PDF，所以先把 EPUB 转 PDF。本机没有 Calibre/pandoc，走「解包 EPUB → 合并成单 HTML → Edge 无头打印」这条路，脚本在 `scripts/epub_to_pdf.py`。

**这里有个会让整本书报废的坑**：Calibre 导出的 CSS 常把字体写成 `MicrosoftYaHei`（中间少空格，不是合法字体名）或 `STKaiti`，浏览器认不出来就回退到「等线」等字体，而 Chromium 生成 PDF 的 ToUnicode 时会取该字形的最小码位——结果整个文字层的汉字都被写成**康熙部首**码位（「高」变 U+2FBC「⾼」）。字形一模一样，但搜索、翻译、检索全都不认。

脚本已经做了字体名修正。转完务必验证：`scripts/epub_to_pdf.py --verify` 会检查汉字数、康熙部首数（必须为 0）和是否有内容越出页边。细节见 `references/epub-to-pdf.md`。

## 2. 提交到 MinerU 桌面版

**先做这一步：把应用拉起来，并且带上可访问性开关。**

```bash
powershell -NoProfile -Command "Stop-Process -Name MinerU -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 3; Start-Process -FilePath 'C:\Users\yuele\AppData\Local\Programs\MinerU\MinerU.exe' -ArgumentList '--force-renderer-accessibility'; Start-Sleep -Seconds 25"
```

不加 `--force-renderer-accessibility` 的话，可访问性树几乎是空的（只剩关闭/最大化/最小化三个按钮），任何语义操作都无处落脚。加了之后界面完整暴露（150~330 个元素）。

### 提交流程

1. `get_app_state` 找到 `上传文件` 按钮，元素点击。
2. 系统文件对话框弹出（一般停在上次的目录）。把 `文件名(N)` 输入框设成目标**目录**路径，点 `打开(O)` —— 目录路径会让它进入该目录，而不是关掉对话框。
3. 多选文件：跑 `scripts/select_files_uia.ps1`（见下节）。
4. 点 `打开(O)`。应用会弹出「自定义页码（仅PDF）」确认框，列出每个文件及其页数范围（默认全选 1-N 页）。
5. 点 `上传`。任务即进入云端队列；应用每 5 秒轮询一次状态。

### 多选对话框：唯一可靠的做法

这是这条链路里最容易卡死的一步，说清楚为什么：

- **不能用通配符**。在文件名框里填 `*.pdf` 再点「打开」不会有任何反应——外壳只在**回车**时才把通配符展开成多选。
- **回车也用不了**。Windows 下键盘输入要求目标窗口在前台，而宿主策略会拒绝 `open_application(activate=true)`（报 `frontmost application is 0 active apps`），所以前台键盘这条路是断的。
- **可行的做法**：用 PowerShell 的 UI Automation 直接对列表项调用 `SelectionItemPattern.Select()`（第一项）和 `AddToSelection()`（其余）。选中之后，**外壳会自动把选中文件名带引号填进文件名框**，此时再点「打开」就生效了。

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/select_files_uia.ps1 -ProcessId <pid> -Suffix "_1_1-164,_2_165-328"
```

用法要点：

- `-Suffix` 用**纯 ASCII 后缀**匹配文件（列表项显示名不含 `.pdf` 扩展名）。不带 `-Suffix` 就是全选当前可见项。
- **列表是虚拟化的**，`FindAll` 只返回可见的约 15 行。要一次提交多于这个数量的文件，先把目标文件**临时移到一个空目录**让它们全部可见，提交后再移回——这比试图滚动列表可靠得多。
- 单次上传上限 20 个文件，超过就分批。
- 排除已经解析过的文件（比如断点续跑）时，也用 `-Suffix` 把它排除——按后缀精确跳过，避免重复消耗额度。

### 如果应用是别人正常打开的

可访问性树读不到就说明它没带那个开关。**先问用户能不能重启它**，不要盲试坐标点击。

## 3. 等待

解析在云端进行，应用只是轮询。**应用必须保持开着**，否则轮询中断。

盯进度不要靠界面，直接查库最省事也最准（`scripts/wait_and_collect.py` 封装了）：

```
C:\Users\yuele\MinerU\data\mineru.db  →  表 taskData
字段：file_name / state / task_id / batch_id / origin_file_path / unzip_file_output_path / extract_progress / err_msg
```

状态推进：`waiting-file → uploading → pending → running → downloading → unzipping → unzipped`（失败为 `failed`）。参考速度：113 页约 7 分钟；3,796 页（23 个分片）约 30 分钟——云端并行度很高，同时能有 7~10 个任务在跑，别按单线程线性估时。

## 4. 收集

应用会把结果自动解压到 `C:\Users\yuele\MinerU\<分片名>.pdf-<uuid>\`，**目录名正好就是工作区里惯用的命名**。搬进 `minuer_u未处理\` 即可：

```bash
python scripts/wait_and_collect.py --collect      # 全部到达终态后搬入 minuer_u未处理
```

每份产物应包含：`full.md`、`images/`、`*_content_list.json`、`*_content_list_v2.json`、`*_model.json`、`*_origin.pdf`、`layout.json`。

搬完逐份校验（脚本会一起做）：`full.md` 里的图片引用**必须都能对上实际文件**，附属文件齐全，并且**汉字里不能出现康熙部首码位**。英文原版书汉字数为 0 是正常的，别当成失败。

## 5. 归档到读书笔记（坚果云）

把 `minuer_u未处理\` 里同一本书的多个分片产物，归档成笔记库里的一本书。**先读 `references/notes-archive.md`**——那里有笔记格式范例的出处和全部约定，本节只写主线。

机械部分一条命令（对应笔记库 `.模板\miner_u导入模板\SKILL.md` 的规范）：

```bash
python scripts/archive_to_notes.py \
  --src "D:\垃圾文件夹\minuer_u未处理" --pick "<书名子串>" \
  --book "C:\Users\yuele\Documents\坚果云\文件\个人文件\笔记\编程读书笔记\<书名>" \
  --title "<书名>"
```

脚本自动完成：按分片目录名里的页码区间排序 → 初始化书目录（原文/章节、原文/images、笔记、anki_cards、延伸阅读、_work）→ 合并 full.md → 围栏感知地按 `第N章`/`Chapter N` 拆章并改写图片路径为 `../images/` → 拷贝图片 → 生成笔记骨架（导读/TL;DR 留 TODO，问答留空）→ 打包源分片进 `_work/` → 全量校验。

脚本跑完后是**模型的工作**，逐章推进：

1. **填笔记**：读该章 `原文/章节/chapter-NN-*.md`，填骨架里的 `## 导读`（1~2 段 + 「带着问题读」）和 `## TL;DR`（要点 bullets）。**不要动 `## 问答`**——那是用户读书时自己提问回填的。
2. **出卡片**：按 `anki-card-from-notes` 技能给该章生成 `anki_cards/chapter-NN-*.md`。deck 约定 `笔记系统::计算机::<书名>::<章节名>`、tags 和卡数在**开工前向用户确认一次**，之后各章沿用。写完必跑 `~/.zcode/skills/anki-card-from-notes/scripts/check_anki_cards.py <文件>`，有 error 改到干净。
3. **节奏**：一本书十几章，逐章做；开工前确认用户要全本还是先做前几章。

两个已知边界：英文书（如 Grokking）章节标题不规整，拆不出时脚本按规范降级为只留 full.md，可加 `--pattern` 补该书的章节正则重跑；任何一步校验不过都不要删 `minuer_u未处理\` 里的源分片——zip 备份没校验通过前它们是唯一原件。

## 常见坑

| 现象 | 原因与处理 |
|---|---|
| 应用界面读不到（只有三个窗口按钮） | 没带 `--force-renderer-accessibility`，重启它 |
| 文件名框填了 `*.pdf`，点「打开」没反应 | 通配符只在回车时展开；改用 UIA 选中列表项 |
| 回车/输入无效，报 `frontmost_pid_mismatch` | 宿主拒绝激活窗口，前台键盘不可用；走元素点击 + UIA 脚本 |
| 选中的文件数不对（少了） | 列表虚拟化只实例化约 15 行；用临时目录让目标全部可见 |
| 元素索引对不上 | 应用视图会随最近文件卡片变化而位移；**每次元素写入前重新 `get_app_state`**，写入会消耗 state |
| 产物文字层是康熙部首（⾼/⼀/⾮） | EPUB 转 PDF 的字体名问题，见 `references/epub-to-pdf.md` |
| 任务停在 `waiting-file` 很久 | 上传未完成或应用被关；确认应用在跑，必要时重开 |
| `pdftotext` 抽不到中文 | 本机 `pdftotext` 是 Xpdf 4.00（Glyph & Cog），读不了 CID 子集字体；用 pdfium/pypdf 复核，别据此判定 PDF 有问题 |
| 拆章结果缺失或混乱 | 代码块里的 `#` 行被当成了标题（脚本已围栏感知），或该书标题格式不匹配；用 `--pattern` 补正则重跑，别手工补文件 |
| 归档后章节图片显示不出来 | 章节文件里图片路径必须是 `../images/`，`原文/full.md` 里保持 `images/`——脚本分别处理，人工改动时别搞混 |
| 读坚果云里的文件拿到 0 字节/打不开 | 坚果云占位文件未下载；先让同步完成再读，见 `references/notes-archive.md` |

## 相关文件

- `references/mineru-desktop-internals.md` — 桌面版的路径、库表结构、状态机、配额限制，以及与官方 API 的对比（含 API token 14 天过期的坑）
- `references/epub-to-pdf.md` — EPUB 转换的完整配方、字体坑的原理与验证方法
- `references/notes-archive.md` — 归档规范：笔记库结构、笔记三段式格式、Anki deck/tags 约定、逐章生成的节奏
- `references/pipeline-contracts.md` — **每步的输入/产物/验收标准**（含数值判据与退出条件），执行中拿不准是否放行就查它
- `scripts/select_files_uia.ps1` — 文件对话框多选（**必须保持纯 ASCII**：PowerShell 5.1 按 ANSI 读 `.ps1`，中文注释会导致语法错误）
- `scripts/verify_splits.py` — 拆分页数守恒校验
- `scripts/wait_and_collect.py` — 等待全部完成并把产物收进 `minuer_u未处理`
- `scripts/epub_to_pdf.py` — EPUB → 单 HTML → Edge 无头打印 PDF，含校验
- `scripts/archive_to_notes.py` — MinerU 产物 → 坚果云读书笔记（合并/拆章/图片/笔记骨架/打包/校验）
