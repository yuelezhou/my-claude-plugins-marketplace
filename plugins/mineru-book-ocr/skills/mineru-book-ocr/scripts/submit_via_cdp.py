# -*- coding: utf-8 -*-
"""MinerU 桌面版无界面提交：CDP 点页面按钮 + Win32 消息驱动原生文件对话框。

用法：
    python submit_via_cdp.py --files <pdf1> <pdf2> ... [--port 9223]

前提：
  1. MinerU 以 `--remote-debugging-port=9223 --force-renderer-accessibility` 启动；
  2. `pip install --user websocket-client`；
  3. 应用已登录（C:\\Users\\yuele\\MinerU\\config.json 有登录态）。

流程：点「上传文件」→ 等「打开」对话框 → WM_SETTEXT 写带引号的路径串 →
IDOK 确认 → 等「自定义页码」弹层 → 点「上传」→ 打印 taskData 新增记录。

铁律：上传流程中**绝不 reload 页面**——原生对话框挂在渲染页面上，reload 会立刻
杀掉它且已选路径全部丢失；对话框弹出约 40 秒后也可能自关，动作要连贯，
失败就重新走一遍（重跑本脚本即可）。

为什么不用 UIA：
  - Electron 渲染层的可访问性树对普通 UIA 客户端不开放（--force-renderer-
    accessibility 只对 computer-use 这类 AT 生效），PowerShell UIA 对主窗口
    只能看到 2 个元素；
  - 新式「打开」对话框把「文件名(N):」暴露成无 ValuePattern 的 Static Pane，
    UIA 旧路（select_files_uia.ps1）在这种视图下会失败。
  Win32 消息（WM_SETTEXT + IDOK）两条路都绕开，且一次完成多文件选择。
"""
import argparse
import ctypes
import json
import sqlite3
import time
import urllib.request
from ctypes import wintypes

import websocket

u = ctypes.windll.user32
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_COMMAND = 0x0111
IDOK = 1


def get_ws(port):
    """找 MinerU 主页面 target 的 webSocketDebuggerUrl。"""
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
    for t in targets:
        if t.get("type") == "page" and "MinerU" in (t.get("title") or ""):
            return t["webSocketDebuggerUrl"]
    raise SystemExit("未找到 MinerU 页面 target——确认应用带 --remote-debugging-port=%d 启动" % port)


def ev(ws_url, js, timeout=30):
    """在页面里执行 JS，返回结果值；异常时抛带信息的错。"""
    ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
    ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": js, "returnByValue": True,
                                   "userGesture": True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == 1:
            ws.close()
            res = m.get("result", {})
            if "exceptionDetails" in res:
                raise RuntimeError("页面 JS 异常: " + json.dumps(
                    res["exceptionDetails"].get("exception", res["exceptionDetails"]),
                    ensure_ascii=False)[:300])
            return res.get("result", {}).get("value")


def mineru_pids():
    import subprocess
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        '(Get-Process MinerU).Id -join ","'], capture_output=True)
    out = (r.stdout or b"").decode("utf-8", "replace")
    return {int(x) for x in out.strip().split(",") if x.strip()}


def find_dialogs(pids):
    """枚举 MinerU 进程下标题为「打开」的可见顶层窗口（原生文件对话框）。"""
    res = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @EnumProc
    def cb(hwnd, lparam):
        if u.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids:
                n = u.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                if buf.value == "打开":
                    res.append(hwnd)
        return True

    u.EnumWindows(cb, 0)
    return res


def find_edit(dlg):
    """对话框里 class=Edit 的子控件（文件名输入框）。"""
    found = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    buf = ctypes.create_unicode_buffer(256)

    @EnumProc
    def cb(h, lp):
        if u.IsWindowVisible(h):
            u.GetClassNameW(h, buf, 256)
            if buf.value == "Edit":
                found.append(h)
        return True

    u.EnumChildWindows(dlg, cb, 0)
    return found[0] if found else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="+", required=True, help="要提交的 PDF 绝对路径")
    ap.add_argument("--port", type=int, default=9223, help="CDP 调试端口")
    ap.add_argument("--db", default=r"C:\Users\yuele\MinerU\data\mineru.db")
    args = ap.parse_args()

    quoted = " ".join('"%s"' % f for f in args.files)
    names = {f.rsplit("\\", 1)[-1] for f in args.files}

    con = sqlite3.connect(args.db)
    before = {n for (n,) in con.execute("select file_name from taskData")}
    con.close()

    ws_url = get_ws(args.port)

    # 1) 点「上传文件」
    r = ev(ws_url, "(() => { const b=[...document.querySelectorAll('button')]"
                   ".find(b=>(b.textContent||'').trim()==='上传文件');"
                   " if(!b) return 'NO BTN'; b.click(); return 'clicked'; })()")
    print("[1/5] 上传文件按钮:", r)
    if r != "clicked":
        raise SystemExit(1)

    # 2) 等「打开」对话框
    dlg = None
    pids = mineru_pids()
    for _ in range(50):
        time.sleep(0.5)
        ds = find_dialogs(pids)
        if ds:
            dlg = ds[0]
            break
    if not dlg:
        raise SystemExit("25 秒内「打开」对话框未出现——重跑本脚本再试一次")
    print("[2/5] 对话框出现 hwnd=%d" % dlg)

    # 3) 等 Edit 子控件并写带引号路径
    edit = None
    for _ in range(20):
        edit = find_edit(dlg)
        if edit:
            break
        time.sleep(0.3)
    if not edit:
        raise SystemExit("对话框里未找到 Edit 子控件")
    u.SendMessageW(edit, WM_SETTEXT, 0, quoted)
    time.sleep(0.5)
    readback = ctypes.create_unicode_buffer(4096)
    u.SendMessageW(edit, WM_GETTEXT, 4096, readback)
    if readback.value.count('"') != 2 * len(args.files):
        raise SystemExit("路径写入校验失败: " + readback.value[:120])
    u.PostMessageW(dlg, WM_COMMAND, IDOK, 0)
    print("[3/5] 路径串已写入并 IDOK（%d 个文件）" % len(args.files))

    # 4) 等「自定义页码」弹层
    modal = False
    for _ in range(25):
        time.sleep(1)
        if ev(ws_url, "document.body.innerText.indexOf('自定义页码')>=0 ? 'YES':'NO'") == "YES":
            modal = True
            break
    if not modal:
        raise SystemExit("「自定义页码」弹层未出现——若对话框又自关，直接重跑本脚本")
    print("[4/5] 自定义页码弹层出现")

    # 5) 点「上传」（精确匹配，避免命中「上传文件」主按钮）
    r = ev(ws_url, "(() => { const ups=[...document.querySelectorAll('button')]"
                   ".filter(b=>(b.textContent||'').trim()==='上传');"
                   " if(!ups.length) return 'NO BTN'; ups[ups.length-1].click();"
                   " return 'clicked'; })()")
    print("[5/5] 上传按钮:", r)
    if r != "clicked":
        raise SystemExit(1)

    # 6) 验库
    time.sleep(8)
    con = sqlite3.connect(args.db)
    rows = con.execute(
        "select file_name, state from taskData order by id desc limit 40").fetchall()
    con.close()
    new = [(n, s) for n, s in rows if n in names]
    print("新增任务记录:")
    for n, s in new:
        print("  %-70s %s" % (n[-70:], s))
    got = {n for n, _ in new}
    missing = names - got
    print("计划 %d 个，已入库 %d 个%s" % (len(names), len(got),
          ("，缺: " + "; ".join(sorted(missing))) if missing else ""))
    raise SystemExit(0 if not missing else 1)


if __name__ == "__main__":
    main()
