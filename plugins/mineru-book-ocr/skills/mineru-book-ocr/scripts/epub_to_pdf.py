# -*- coding: utf-8 -*-
"""EPUB → PDF（不依赖 Calibre/pandoc）：解包合并成单 HTML，再用 Edge 无头打印。

用法：
    python epub_to_pdf.py --epub "<书.epub>" --out "<书.pdf>" --verify

为什么不用现成工具：本机通常没有 Calibre / pandoc / wkhtmltopdf，Python 也没有 epub 相关库，
而 Edge 是 Windows 自带的，用它的 headless 打印能得到带完整文字层的 A4 PDF。

关键坑（会让整本书的文字层报废）：Calibre 导出的 CSS 常把字体名写成 "MicrosoftYaHei"
（少一个空格，非法字体名）和 "STKaiti"，浏览器会回退到「等线」等字体，Chromium 生成
ToUnicode 时取字形的最小码位，于是汉字全被映射到康熙部首区（U+2Fxx）——字形一样，
但搜索/翻译/检索都不认。本脚本会改写这些字体名，并用 --verify 守住这条底线。
"""
import argparse
import base64
import json
import os
import posixpath
import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp"}

# 字体名修正：左边是 Calibre 写坏的名字，右边是真实存在的字体。
# 实测 Microsoft YaHei / SimSun / SimHei / KaiTi 正常；DengXian(等线) 与通用族名会触发康熙部首问题。
FONT_FIX = (
    ("MicrosoftYaHei", '"Microsoft YaHei", "SimSun"'),
    ("STKaiti", '"KaiTi", "Microsoft YaHei", "SimSun"'),
)

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

OVERLAY_CSS = """
@page { size: A4; margin: 14mm 12mm; }
html { -webkit-print-color-adjust: exact; }
body { font-family: "Microsoft YaHei", "SimSun", serif; font-size: 10.5pt; line-height: 1.65; margin: 0; }
.chap { page-break-before: auto; }
h1, h2, h3, h4 { page-break-after: avoid; break-after: avoid; line-height: 1.35; }
p { margin: 0.35em 0; text-align: justify; }
img { max-width: 100% !important; height: auto !important; }
pre { white-space: pre-wrap !important; word-wrap: break-word; overflow-wrap: anywhere;
      font-family: Consolas, "Microsoft YaHei", "SimSun", monospace; font-size: 8.5pt; line-height: 1.32;
      background: #f6f6f6; border: 1px solid #ddd; padding: 4px 6px; margin: 0.5em 0;
      page-break-inside: avoid; }
p, span, div, li, td, h1, h2, h3, h4 { font-family: inherit; }
"""


def local(tag):
    return tag.rsplit("}", 1)[-1]


def strip_ns(root):
    for el in root.iter():
        el.tag = local(el.tag)
    return root


def build_html(epub_path, title):
    """按 spine 顺序把 EPUB 合并成一个自包含 HTML 字符串。"""
    z = zipfile.ZipFile(epub_path)
    container = ET.fromstring(z.read("META-INF/container.xml"))
    opf_path = None
    for rf in container.iter():
        if local(rf.tag) == "rootfile":
            opf_path = rf.get("full-path")
    if not opf_path:
        raise RuntimeError("container.xml 里找不到 rootfile")
    opf_dir = posixpath.dirname(opf_path)
    opf = strip_ns(ET.fromstring(z.read(opf_path)))

    manifest = {it.get("id"): it.get("href") for it in opf.iter("item")}
    docs = [manifest[r.get("idref")] for r in opf.iter("itemref") if r.get("idref") in manifest]

    css = ""
    for name in ("stylesheet.css", "page_styles.css"):
        p = posixpath.join(opf_dir, name)
        if p in z.namelist():
            css += z.read(p).decode("utf-8", "replace") + "\n"
    for bad, good in FONT_FIX:
        css = css.replace(bad, good)          # 见文件头的字体坑说明
    if "MicrosoftYaHei" in css or "STKaiti" in css:
        print("警告: CSS 里仍有未修正的字体名，可能触发康熙部首问题")

    cache = {}

    def data_uri(base, rel):
        target = posixpath.normpath(posixpath.join(base, rel))
        if target in cache:
            return cache[target]
        mime = MIME.get(posixpath.splitext(target)[1].lower(), "image/jpeg")
        try:
            uri = "data:%s;base64,%s" % (mime, base64.b64encode(z.read(target)).decode("ascii"))
        except KeyError:
            print("  警告: EPUB 内缺少图片", target)
            uri = rel
        cache[target] = uri
        return uri

    body_re = re.compile(r"<body[^>]*>(.*)</body>", re.S | re.I)
    chunks = []
    for href in docs:
        path = posixpath.normpath(posixpath.join(opf_dir, href))
        raw = z.read(path).decode("utf-8", "replace")
        m = body_re.search(raw)
        body = m.group(1) if m else raw
        base = posixpath.dirname(path)
        body = re.sub(r'src="([^"]+)"', lambda mo: 'src="%s"' % data_uri(base, mo.group(1)), body)
        chunks.append('<section class="chap">%s</section>' % body)

    html = ("<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<title>%s</title>\n<style>\n%s\n%s\n</style></head><body class=\"calibre\">\n%s\n</body></html>"
            % (title, css, OVERLAY_CSS, "\n".join(chunks)))
    return html, len(docs), len(cache)


def find_browser(explicit=None):
    for p in ([explicit] if explicit else []) + EDGE_CANDIDATES:
        if p and os.path.exists(p):
            return p
    raise RuntimeError("找不到 Edge/Chrome，无法打印 PDF")


def print_pdf(browser, html_path, pdf_path, profile_dir):
    os.makedirs(profile_dir, exist_ok=True)
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run",
           "--no-default-browser-check",
           "--user-data-dir=" + profile_dir,       # 独立 profile，别碰用户真实浏览器配置
           "--virtual-time-budget=20000",
           "--no-pdf-header-footer",
           "--print-to-pdf=" + pdf_path,
           "file:///" + html_path.replace("\\", "/")]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(pdf_path):
        raise RuntimeError("打印失败:\n%s\n%s" % (proc.stdout[-2000:], proc.stderr[-2000:]))
    return os.path.getsize(pdf_path)


def verify(pdf_path):
    from pypdf import PdfReader
    r = PdfReader(pdf_path)
    pages = len(r.pages)
    cjk = kanxi = 0
    for pg in r.pages:
        t = pg.extract_text() or ""
        for ch in t:
            o = ord(ch)
            if 0x4E00 <= o <= 0x9FFF:
                cjk += 1
            elif 0x2F00 <= o <= 0x2FDF:
                kanxi += 1
    nimg = 0
    for pg in r.pages:
        res = pg.get("/Resources")
        xo = res.get("/XObject") if res else None
        if not xo:
            continue
        xo = xo.get_object()
        nimg += sum(1 for k in xo if xo[k].get_object().get("/Subtype") == "/Image")
    print(f"  页数 {pages}  汉字 {cjk}  康熙部首 {kanxi}  页内图片 {nimg}")
    if kanxi:
        print("  FAIL: 文字层含康熙部首码位 —— 检查字体名修正是否漏了")
    overflow = None
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(pdf_path)
        w = doc[0].get_size()[0]
        worst = 0.0
        for i in range(len(doc)):
            tp = doc[i].get_textpage()
            for ci in range(tp.count_chars()):
                box = tp.get_charbox(ci)
                if box[2] > worst:
                    worst = box[2]
        overflow = worst
        print(f"  最右字符 x={worst:.1f}pt（页宽 {w:.1f}pt，A4 内容区右边界约 561pt）")
        if worst > w - 2:
            print("  FAIL: 有内容越出页面")
    except ImportError:
        print("  （未安装 pypdfium2，跳过越界检查）")
    ok = (kanxi == 0) and (overflow is None or overflow <= 590)
    print("  判定:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epub", required=True)
    ap.add_argument("--out", required=True, help="输出的 PDF 路径")
    ap.add_argument("--html-out", default=None, help="保留的中间 HTML 路径（默认放在临时目录）")
    ap.add_argument("--keep-html", action="store_true", help="保留中间 HTML 不删除")
    ap.add_argument("--browser", default=None, help="手动指定 msedge.exe / chrome.exe")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    work = os.path.join(os.environ.get("TEMP", "."), "epub2pdf")
    os.makedirs(work, exist_ok=True)
    html_path = args.html_out or os.path.join(work, "book.html")

    print(f"[1/3] 解包合并: {os.path.basename(args.epub)}")
    html, n_docs, n_img = build_html(args.epub, os.path.splitext(os.path.basename(args.epub))[0])
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"      spine 文档 {n_docs} 个，内嵌图片 {n_img} 张，HTML {os.path.getsize(html_path)/1048576:.2f} MB")

    print("[2/3] Edge 无头打印")
    browser = find_browser(args.browser)
    size = print_pdf(browser, html_path, args.out, os.path.join(work, "edge_profile"))
    print(f"      {args.out}  {size/1048576:.2f} MB")

    rc = 0
    if args.verify:
        print("[3/3] 校验")
        rc = verify(args.out)
    else:
        print("[3/3] 已跳过校验（建议加 --verify）")

    if not args.keep_html and not args.html_out:
        try:
            os.remove(html_path)
        except OSError:
            pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
