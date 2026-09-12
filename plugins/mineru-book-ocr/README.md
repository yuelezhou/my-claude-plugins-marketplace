# MinerU Book OCR Plugin

书籍 → MinerU OCR → 读书笔记的完整流水线。把整本 PDF/EPUB 书籍按 200 页拆分，用 computer use 驱动 MinerU 桌面版批量提交云端解析，把产物收进书籍工作区，再归档成坚果云读书笔记（合并原文 / 围栏感知按章节拆分 / 写导读与 TL;DR / 生成 Anki 卡片）。

## 📦 包含内容

### Skills

- **mineru-book-ocr** — 五段式流水线：**拆分 → 提交 → 等待 → 收集 → 归档**
  - `SKILL.md`：主线流程、每步的坑与验证方法
  - `references/pipeline-contracts.md`：每步的输入/产物/验收标准（含数值判据）
  - `references/mineru-desktop-internals.md`：MinerU 桌面版路径、库表结构、状态机、配额限制（单文件 ≤200 页 / ≤200MB、单日 5000 份、单次 20 个文件）
  - `references/notes-archive.md`：归档规范、笔记三段式、Anki deck/tags 约定
  - `references/epub-to-pdf.md`：EPUB → PDF 转换配方与康熙部首字体坑
  - `scripts/`：`pdf 拆分校验 / MinerU 等待收集 / 归档到笔记库 / EPUB 转换 / 文件对话框多选(UIA)` 五个脚本

## ⚙️ 外部依赖（本插件脚本不自带）

| 依赖 | 用途 | 缺失时的表现 |
|---|---|---|
| [MinerU 桌面版](https://mineru.net/) | 云端解析客户端，需已登录（自带登录态） | 提交/等待/收集三段无法进行 |
| 系统 Python（≥3.10，装 `pypdf`） | 拆分、校验、归档脚本 | 所有脚本无法运行 |
| `pdf_spliter.py`（py_pdf_book_helper 仓库） | 按 200 页均分 PDF | 拆分段需自行替换实现 |
| `anki-card-from-notes` 插件（本市场内含） | 归档段生成 Anki 卡片后的格式校验脚本 `check_anki_cards.py` | 卡片校验退化为人工核对 |

> 流水线里部分路径是本机约定（如工作区 `D:\垃圾文件夹`、坚果云笔记库路径），换机器使用时按 SKILL.md 第 0 步的说明替换即可。

## 🚀 安装

```bash
cd /path/to/my_claude_code_market
claude plugin marketplace add local ./my_claude_code_market
claude plugin install mineru-book-ocr
```

## 📝 使用

安装后直接说触发词即可，例如：

```
帮我把 原书/xxx.pdf 每 200 页切一份，提交 mineru 跑 OCR
```
```
把 minuer_u未处理 里同一本书的产物归档到读书笔记，逐章写导读并出 Anki 卡
```

## 📄 License

MIT
