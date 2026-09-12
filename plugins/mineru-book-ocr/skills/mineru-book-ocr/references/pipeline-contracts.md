# 流水线步骤契约（输入 / 产物 / 验收标准）

每段的输入、输出产物、产出标准与校验方式。**上一步验收不过，不进入下一步**；数值标准都来自实测，不要凭感觉放行。

## 阶段 1 拆分

| | |
|---|---|
| 输入 | 整本 PDF（`原书\*.pdf`）；EPUB 先经 `epub_to_pdf.py` 转 PDF 入 `原书\` |
| 产物 | `待处理\<书名>_<序号>_<起页>-<止页>.pdf`，每份 ≤200 页 ≤200MB；EPUB 路线另有转换出的 `<书名>.pdf`（与 epub 同名，放 `原书\`） |
| 校验 | `verify_splits.py --parts <分片目录> --source <原书目录>`；EPUB 路线 `epub_to_pdf.py --verify` |

通过标准：

1. **页数守恒**：每本书所有分片页数之和 == 原书页数。
2. **区间自洽**：每个分片的实际页数 == 文件名里标注的 `A-B` 范围（b-a+1）。
3. **区间连续**：按序号排列后首尾相接，无缺口、无重叠（第一个分片从第 1 页开始）。
4. EPUB 转换件追加：**康熙部首码位 == 0**（硬性，出现即整书报废）；汉字数在中文书正常量级（技术书 10 万+）；页内图片数 == EPUB 内图片总数；最右字符 x ≤ 内容区右边界（A4 595pt 宽，内容区约 561pt），无内容越界；页数与同书既往产物一致（同内容页数突变说明排版样式被改）。

## 阶段 2 提交

| | |
|---|---|
| 输入 | `待处理\*.pdf`；MinerU 桌面版（必须带 `--force-renderer-accessibility` 启动） |
| 产物 | `C:\Users\yuele\MinerU\data\mineru.db` 表 `taskData` 新增记录：`file_name`、`state`（初始 waiting-file/uploading）、`task_id`、`batch_id`、`origin_file_path` |
| 校验 | sqlite 查 `taskData`；界面元素 `选择文件: N 个文件` |

通过标准：

1. 库中新增记录数 == 本批计划提交数（多选脚本复核过的选中数）。
2. 每条记录的 `origin_file_path` 指向 `待处理\` 里的正确文件（路径对、无同名混淆）。
3. 无重复提交：同名 `file_name` 已有非 failed 记录的不再提交（断点续跑按后缀排除）。
4. 单批 ≤20 个文件；列表虚拟化只能选到可见行，超出的用临时目录分批。

## 阶段 3 等待

| | |
|---|---|
| 输入 | `mineru.db`（应用保持开着，它负责轮询云端） |
| 产物 | 全部任务到达终态 `unzipped` 或 `failed`；成功任务在 `unzip_file_output_path` 落地产物目录 |
| 校验 | `wait_and_collect.py`（轮询打印分布；终态后列出所有 failed 及 err_msg） |

通过标准：

1. `failed` == 0。有 failed 时逐个看 `err_msg` 决定重提还是放弃，**不许静默跳过**。
2. 成功任务的 `extract_progress` 里 `extracted_pages == total_pages`。
3. 参考速度：113 页约 7 分钟，3,796 页约 30 分钟（云端并行 7~10 个）；显著慢于该量级先确认应用还开着。

## 阶段 4 收集

| | |
|---|---|
| 输入 | `C:\Users\yuele\MinerU\<分片名>.pdf-<uuid>\` 产物目录 |
| 产物 | `minuer_u未处理\<分片名>.pdf-<uuid>\`，内含 `full.md`、`images\`、`*_content_list.json`、`*_content_list_v2.json`、`*_model.json`、`*_origin.pdf`、`layout.json` |
| 校验 | `wait_and_collect.py --collect --verify` |

通过标准（逐份，全部满足）：

1. `full.md` 存在且非空。
2. **图片引用零缺失**：`full.md` 里每个 `![](images/…)` 都能对上 `images\` 里的实际文件。
3. 附属文件 4 类齐全（content_list / model / origin.pdf / layout.json）。
4. **康熙部首码位 == 0**。
5. 汉字数 > 0（中文书）；英文原版书 == 0 属正常，不是失败。
6. 搬运后源目录 `C:\Users\yuele\MinerU\` 只剩 `config.json` 与 `data\`。

## 阶段 5 归档

| | |
|---|---|
| 输入 | `minuer_u未处理\` 中**同一本书**的各分片产物目录 |
| 产物 | 笔记库书目录（`编程读书笔记\<书名>\`）：`原文\full.md`、`原文\章节\chapter-NN-标题.md`、`原文\images\`、`笔记\chapter-NN-标题.md`、`anki_cards\chapter-NN-标题.md`、`_work\<书名>_miner_u_YYYYMMDD.zip` |
| 校验 | `archive_to_notes.py` 内建校验（任何一项失败退出码 1）；笔记/卡片的内容标准靠人工与 `check_anki_cards.py` |

### 5a. 机械归档（脚本），通过标准：

1. `原文\full.md` 是文件（非目录）且非空。
2. `原文\章节\` 下只有 `.md` 文件、无子文件夹。
3. 章节文件图片路径**全部**为 `../images/`，零残留 `](images/`；`原文\full.md` 保持 `images/` 原样（两者方向相反，别改错）。
4. `原文\images\` 文件数 ≥ 各源分片 images 之和。
5. zip：`testzip` 通过，且包内 full.md 数 ≥ 分片数；**zip 校验通过前不得删 `minuer_u未处理\` 源分片**。
6. 拆章覆盖合理：中文章节书的章数应接近图书目录（明显偏少说明标题正则没匹配上，用 `--pattern` 补后重跑）；确实拆不出（英文书常见）按规范降级为只保留 full.md 并明确报告，**不硬造章节**。

### 5b. 笔记（模型填写骨架），通过标准：

1. 每个章节文件都有同名笔记；导读 1~2 段、基于该章原文（不是靠书名想象）、结尾有「带着问题读：<提问>」。
2. TL;DR 为要点 bullets、术语加粗，覆盖主干概念与关键结论。
3. **`## 问答` 段保持占位原文不动**——那是用户读书时自己回填的。
4. 笔记头部引用块与上/下一章导航链接有效（同目录相对链接）。

### 5c. Anki 卡片，通过标准：

1. 每章一个 `anki_cards\chapter-NN-*.md`，格式符合 anki-card-from-notes 契约（`## 卡片名` + `#### 正面/背面/笔记` 或 cloze `Text/Back Extra`；无 `###` 标题；新卡无 `##### id`）。
2. `check_anki_cards.py` 结果 **0 error**（warning 能修则修）。
3. deck `笔记系统::计算机::<书名>::<章节名>`、tags、卡数已与用户确认过一次并全程沿用。
4. 卡片内容来自该章原文；同一知识点只出 1 张卡。

## 通用纪律

- 每步先校验后前进；校验脚本退出码非 0 就停下报告，不要"先继续再补验"。
- 凡删除动作（删源分片、删临时目录）都排在全部相关校验通过之后。
- 读坚果云里的文件先确认不是 0 字节占位符；写完的校验若读到空文件，先怀疑同步未完成。
