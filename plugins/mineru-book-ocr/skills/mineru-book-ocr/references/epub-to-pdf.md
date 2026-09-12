# EPUB → PDF（无 Calibre 环境）

MinerU 只吃 PDF，所以 EPUB 必须转换。本机没有 Calibre / pandoc / wkhtmltopdf / weasyprint，Python 也没有相关库，能用的只有 Edge。可行配方：**解包 EPUB → 按 spine 顺序合并成单个 HTML（图片内嵌 base64）→ Edge 无头打印 A4 PDF**。

脚本：`scripts/epub_to_pdf.py`。它做完整条链路并自带校验。

```bash
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
python scripts/epub_to_pdf.py --epub "<书.epub>" --out "<书.pdf>" --verify
```

## 转换链路

1. 读 `META-INF/container.xml` 拿 OPF 路径，解析 manifest / spine 顺序（**必须按 spine 顺序拼接**，按文件名排序会乱）
2. 逐节取出 `<body>` 内容，把 `img` 的 `src` 换成本地 `data:` URI（151 张图、base64 后约 3MB，一次性内嵌最省事，也避免路径问题）
3. 内联 EPUB 自带 CSS，再追加一层覆盖样式：`@page { size: A4; margin: 14mm 12mm }`、`img { max-width:100% !important; height:auto !important }`、`pre { white-space: pre-wrap; overflow-wrap: anywhere }`
4. **保留 `<body class="calibre">`**。Calibre 的 `.calibre { margin: 0 5pt; font-size: 1em }` 会影响折页；去掉它同一本书会从 516 页变成 475 页（内容一字不差，只是排版更密）。想和既有产物页数一致就别动这个 class。
5. Edge 无头打印：

```bash
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  --headless=new --disable-gpu --no-first-run \
  --user-data-dir="C:/Users/yuele/AppData/Local/Temp/edgepdf_profile" \
  --virtual-time-budget=20000 --no-pdf-header-footer \
  --print-to-pdf="<输出.pdf>" "file:///<合并后的.html>"
```

用独立的 `--user-data-dir`，别碰用户真实的 Edge 配置。

## 必须知道的坑：康熙部首码位

**症状**：PDF 看着完全正常，但文字层抽出来的汉字是 U+2Fxx 康熙部首——「高」变「⾼」、「一」变「⼀」、「非」变「⾮」。肉眼一模一样，但搜索、翻译、检索全都不认。对「PDF 喂给 OCR/翻译」这条链路是致命的。

**根因**：Calibre 导出的 `stylesheet.css` 把字体名写成了 `MicrosoftYaHei`（**中间少一个空格**，不是合法字体名）和 `STKaiti`。浏览器认不出这些名字就回退到默认中文字体（本机是「等线」DengXian），而 Chromium 在生成 ToUnicode 映射时会取该字形对应的**最小码位**——康熙部首区（U+2F00–U+2FDF）排在 CJK 统一汉字（U+4E00+）前面，于是全被映射到部首码位。

**修法**：把 CSS 里的字体名换成真实存在的字体名。

```python
for bad, good in (("MicrosoftYaHei", '"Microsoft YaHei", "SimSun"'),
                  ("STKaiti", '"KaiTi", "Microsoft YaHei", "SimSun"')):
    css = css.replace(bad, good)
```

**实测结果**（同一段文字，同一次打印）：

| 字体 | 文字层 |
|---|---|
| `Microsoft YaHei` / `SimSun` / `SimHei` / `KaiTi` | 正常汉字 |
| `DengXian`（等线） | 康熙部首 |
| `serif` / `sans-serif`（通用族名） | 康熙部首 |

代码块也要管：`<pre>` 若只写 `monospace`，里面的中文注释会走回退字体而中招，所以写成 `Consolas, "Microsoft YaHei", monospace`。

## 校验（别跳过）

`--verify` 会做四件事，缺一不可：

1. **康熙部首计数必须为 0**（这是这道坎的守门员）
2. 汉字总数（正常一本中文技术书在 10 万量级）
3. 内嵌图片数量与 EPUB 里的图片数是否对得上
4. 用 pdfium 的真实字符边界框检查是否有内容**越出页面**（曾用 pypdf 的坐标算错过一次，pdfium 的 `get_charbox` 才准：A4 内容区右边界 561pt，页宽 595pt）

## 关于抽取工具的误报

本机 `pdftotext` 是 **Xpdf 4.00（Glyph & Cog）**，读不了 Chromium 生成的 CID 子集字体，会报「中文 0 个」，让人误以为 PDF 坏了。用 pdfium（`pypdfium2`）或 `pypdf` 复核——两者都能正确抽出全部汉字（该书 168,235 个汉字、0 个部首）。判断 PDF 文字层好坏时不要只信一个工具。

顺便：`pypdfium2` 和 `pillow` 是这条链路需要的（渲染页面图做边界检查/视觉抽查）。它们装在用户级 site-packages。

## 视觉抽查的局限

本环境里 CUA 的截图不会回传给模型（`include_screenshot=true` 只返回可访问性树，Read 图片会被 `model does not support image input` 丢弃），所以**无法肉眼确认版面**。替代做法就是上面的程序化校验（字符边界框、墨迹占比、行数、空白页检测）。若用户能看图，把渲染出的页面 PNG 交给他们看一眼最稳妥。
