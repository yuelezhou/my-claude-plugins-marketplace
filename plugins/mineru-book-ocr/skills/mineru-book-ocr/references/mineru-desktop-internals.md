# MinerU 桌面版内部结构（实测）

版本 0.14.1，Electron 应用。以下结论都是在本机实测出来的，不是文档抄录。

## 它是云端客户端，不是本地推理

界面里写着 `解析中/下载中/解析成功`，数据落在 `mineru.db`，字段名是 `batch_id / task_id / full_zip_url`——这些都是云端 API 的字段。日志里能看到实际上传与下载地址：

- 上传：`https://mineru.oss-cn-shanghai.aliyuncs.com/api-upload/extract/<日期>/<batch_id>/<uuid>.pdf`
- 结果：`https://cdn-mineru.openxlab.org.cn/pdf/<日期>/<task_id>.zip`

模型版本显示为 `vlm3.4.4`（应用配置里 `model_version: "vlm"`）。

**推论：本机不需要 GPU。** 别看到是 AMD 核显就以为跑不动——计算在云端。反过来说，断网就用不了。

## 关键路径

| 用途 | 路径 |
|---|---|
| 主程序 | `%LOCALAPPDATA%\Programs\MinerU\MinerU.exe`（约 199MB，`resources\app.asar` 945MB） |
| 配置（含登录态） | `C:\Users\yuele\MinerU\config.json` |
| 任务库 | `C:\Users\yuele\MinerU\data\mineru.db`（better-sqlite3） |
| 日志 | `%APPDATA%\MinerU\logs\main.log` |
| 产物落点 | `C:\Users\yuele\MinerU\<原分片名>.pdf-<uuid>\` |

`config.json` 里的 `state.history_path` 就是产物根目录；同文件里还有 `client_api_token`、`model_version`、`enable_formula`/`enable_table`、`layout_model: doclayout_yolo`。

## 任务库

表 `taskData`（另有 `taskDemoData`，结构相同）。常用字段：

```
file_name            原文件名（含 .pdf）
state                见下方状态机
task_id / batch_id   云端任务与批次标识
origin_file_path     本地原文件绝对路径
unzip_file_output_path   解压后的产物目录（就是要搬走的东西）
extract_progress     形如 {"extracted_pages":112,"total_pages":113,"start_time":"..."}
full_zip_url         结果压缩包地址
err_msg / err_code   失败原因
file_size            字节数
model_version        如 vlm3.4.4
```

辅助表：`annotation`、`collection`、`downvote`、`edited_block`——都是界面上的标注/收藏功能，跟流水线无关。

### 状态机

```
waiting-file → uploading → pending → running → downloading → unzipping → unzipped
                                                    ↘ failed
```

- `waiting-file`：还没传完（大文件会停在这），或应用被关了
- `pending` / `running`：云端排队与解析
- `unzipping` / `unzipped`：结果包已下载并解压到 `unzip_file_output_path`

产物目录内容（每次都是这一套）：

```
<uuid>_content_list.json       结构化块列表
<uuid>_content_list_v2.json
<uuid>_model.json
<uuid>_origin.pdf              送进去的那个分片
full.md                        正文 markdown（下游主要用它）
images/                        插图
layout.json                    版面信息
```

## 配额与限制（应用界面原文）

> 服务策略调整：单日上限 5000 份｜单文件 ≤200 页｜高优每日 1000 页

界面提示另有：`支持单次上传最多 20 个文件`、`单个文档不超过 200MB、200页`、`单个图片不超过 10MB`。

超过每日高优页数不会拒收，只是排队优先级降低。

## 界面操作要点

- **必须带 `--force-renderer-accessibility` 启动**，否则可访问性树只有窗口按钮。正常关闭再打开就丢了，需要重新拉。
- 界面是中文；元素名形如 `上传文件`、`打开(O)`、`自定义页码（仅PDF）`、`选择文件: 14 个文件`。
- 「自定义页码（仅PDF）」确认框会逐文件列页数范围（`1-113`、`共 113 页`），默认全选；点 `上传` 才真正提交。
- 提交后主界面出现「最近文件」卡片，卡片数量变化会让**后续元素索引整体位移**——每次元素写入前重新观察。
- 应用保持开着才会轮询云端（约每 5 秒一次，日志里可见 `任务 <batch_id> 未完成，等待 5 秒后继续轮询`）。

## 与官方 API 的对比

官方 API v4 是可行的替代路径，接口形状：

1. `POST /api/v4/file-urls/batch`（`files: [{name, is_ocr}]`）拿到 `batch_id` + 预签名 `file_urls`
2. 对每个 URL `PUT` 文件（无需 Content-Type，链接 24 小时有效，单次最多 50 个）
3. `GET /api/v4/extract-results/batch/{batch_id}` 轮询到 `done`，取 `full_zip_url`

但有两个坑：

- **认证是 14 天有效期的 JWT**。`py_pdf_book_helper\.env` 里的 `MINERU_API_KEY` 就是这种（实测已过期，返回 `HTTP 401 / msgCode A0202 / user authenticate failed`）。过期后要去 mineru.net 重新申请；想长期自动化得处理续期，否则每次都要人工换。
- **桌面版的 `client_api_token` 不能用于官方 API**（同为 401 A0202）。它只对桌面版自己的接口有效，所以「把桌面版的 token 抠出来脚本化调用」这条路走不通。

结论：**能拿到新鲜 token 时优先走 API**（可脚本化、无需 GUI）；token 过期或不想维护时走桌面版 GUI。

## 项目里已有的相关代码

`D:\code\toy_and_tools\py_pdf_book_helper\`：

- `src/rpc_tool_call/mineru_ocr_api.py` — API 客户端（`task(url, page_ranges)`、`result(task_id)`），提交体为 `{url, is_ocr: true, model_version: "vlm"}`
- `src/service/miner_u_pipeline_service.py` — 提交并把任务写进项目自己的 `data/tasks.db`
- `scripts/pdf_tools/pdf_spliter.py` — 拆分脚本（本 skill 使用）
- `data/tasks.db` — 43 条历史任务，全部走 `temp-pdf.oss-cn-beijing.aliyuncs.com` 上的签名 URL，说明老流程是「先上传到自己的 OSS，再把 URL 交给 API」；仓库里没有上传代码

注意：项目 venv 若建在 WSL 里则 Windows 下不可用，用系统 Python 跑。
