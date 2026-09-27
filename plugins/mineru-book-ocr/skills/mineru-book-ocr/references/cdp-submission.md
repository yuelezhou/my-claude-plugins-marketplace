# CDP + Win32 备用提交通道（无 computer-use 时）

实测于 2026-09《An Illustrated Guide to AI Agents》（769 页 4 分片）提交全程。当会话里
computer-use 工具不可用、或 `select_files_uia.ps1` 因对话框 UIA 视图退化而失效时，
用这条路提交。核心脚本：`scripts/submit_via_cdp.py`。

## 背景：三条路各自的边界

| 通道 | 能做什么 | 边界（实测） |
|---|---|---|
| computer-use 元素操作 | 全流程 | **不是每个会话都可用**——同一会话早期可用，后面的轮次可能从工具清单里消失 |
| PowerShell UIA（.NET UIAutomationClient） | 原生对话框的部分操作 | **Electron 渲染层树对它不开放**：`--force-renderer-accessibility` 只对 computer-use 这类 AT 生效，普通 UIA 对主窗口只查到 2 个元素，等再久也不生长；新式「打开」对话框里「文件名(N):」是**无 ValuePattern 的 Static Pane**，「打开(O)」是 Pane 不是 Button，UIA 旧路（select_files_uia.ps1）在此视图下失败 |
| CDP（DevTools 协议）+ Win32 消息 | 全流程 | 推荐：页面按钮用 `Runtime.evaluate` 的 `el.click()`（React 合成事件收得到）；原生对话框用 Win32 消息 |

## 启动：两个开关都带上

```bash
powershell -NoProfile -Command "Stop-Process -Name MinerU -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 3; Start-Process -FilePath 'C:\Users\yuele\AppData\Local\Programs\MinerU\MinerU.exe' -ArgumentList '--force-renderer-accessibility','--remote-debugging-port=9223'; Start-Sleep -Seconds 25"
```

`--remote-debugging-port` 无副作用，平时也开着，computer-use 可用时走路线 A、
不可用时立刻能切 CDP。

## CDP 要点

1. `http://127.0.0.1:9223/json` 找 title 含 MinerU 的 page target 拿 `webSocketDebuggerUrl`。
2. **WebSocket 握手会 403 Forbidden**（Chromium 拒带 Origin 的连接）：客户端用
   `websocket.create_connection(url, suppress_origin=True)`，或启动加
   `--remote-allow-origins=*`。依赖：`pip install --user websocket-client`。
3. 页面按钮用 `Runtime.evaluate` + `el.click()` 触发（React 合成事件收得到）。
   点「上传文件」用文本精确匹配；弹层里的「上传」按钮取**文本恰为「上传」**的
   最后一个，避免命中「上传文件」主按钮。
4. `Page.setInterceptFileChooserDialog` + `DOM.setFileInputFiles` **拦不到**——
   MinerU 走的是 Electron 原生 `dialog.showOpenDialog`，不是 `<input type=file>`。

## 原生「打开」对话框：Win32 消息驱动（关键技巧）

不导航目录、不做列表多选——**一个 Edit 控件 + 一条带引号的路径串搞定多选**：

```python
import ctypes
u = ctypes.windll.user32
# 1) 定位：EnumWindows 按进程 PID 集合 + 窗口标题「打开」
# 2) 枚举对话框的子窗口，取 class == "Edit" 的（文件名输入框）
# 3) WM_SETTEXT 写入带引号的完整路径串（多文件 = 空格分隔的多段引号路径）
quoted = '"D:\\待处理\\书_1_1-193.pdf" "D:\\待处理\\书_2_194-385.pdf"'
u.SendMessageW(edit, 0x000C, 0, quoted)          # WM_SETTEXT
# 4) 读回（WM_GETTEXT）校验引号数 == 2×文件数
# 5) PostMessageW(dlg, 0x0111, 1, 0)              # WM_COMMAND + IDOK 关闭并确认
```

这条路绕开了 UIA 的两类失败（渲染层树不可见、对话框 UIA 视图退化），且天然支持
一次多文件。以上全部封装在 `scripts/submit_via_cdp.py`，直接调用即可。

## 三个会翻车的时序坑

1. **对话框约 40 秒后自关**。所有动作要连贯；超时后直接重跑脚本（重新点
   「上传文件」再走一遍）。
2. **绝不在上传流程中 reload 页面**。原生对话框挂在渲染页面上，`location.reload()`
   会立刻杀掉对话框，且用户选好的路径结果随 IPC 一起丢失。实测：reload 后再点
   「上传文件」弹出过一次对话框，之后 `el.click()` 与 CDP 真实鼠标事件
   （`Input.dispatchMouseEvent`，isTrusted=true）都弹不出来了——重开应用才恢复。
3. **一次会话对话框未必能可靠弹第二次**。如果连点都不弹，重启 MinerU（带两个
   开关）是最快的复位方式。

## 云端阶段（等待/收集）的实测教训

- **瞬时失败要重提**：某 192 页分片跑到 33 页报
  `state=failed, err_msg='parsing failed, please try again later'`。原样重提同一
  文件即成功。库里 failed 旧记录与新记录并存是正常现象。
- **`extracted_pages` 不可信**：`unzipped` 状态下可能显示 105/139、146/162 这类
  缺页数字，但 `*_content_list.json` 的 distinct `page_idx` 实际覆盖全部页
  （进度计数口径不同/滞后）。页覆盖校验以 content_list 为准：

  ```python
  items = json.load(open(glob.glob(os.path.join(d, "*_content_list.json"))[0]))
  pages = {it["page_idx"] for it in items if it.get("page_idx") is not None}
  missing = [i for i in range(max(pages) + 1) if i not in pages]
  ```

- **产物内容缺失 ≠ OCR 问题**：实测某书「第 7 章整章没了」但每页 content 都在——
  用 pdfium 在**原书 PDF 全文**检索缺失章节的特征词，0 命中，实锤是源 PDF 本身
  被删了那几页（渠道版删页）。这种情况下重提 OCR 无用，要么换完整版源文件，
  要么在笔记里放缺页说明占位。
