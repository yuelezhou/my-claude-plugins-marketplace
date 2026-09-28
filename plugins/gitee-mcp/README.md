# Gitee MCP Plugin

把 [Gitee 官方 MCP Server](https://gitee.com/oschina/mcp-gitee) 包成 Claude Code 插件：
启用插件即自动连上 Gitee 云端 Remote MCP，AI 助手可以直接读写仓库、文件、Issue、PR、发行版和通知。

**零安装**：走 `https://api.gitee.com/mcp` 远程端点，不需要 Go、不需要 npx、不需要本地二进制。

## 前置：Gitee 访问令牌

1. 登录 Gitee → **设置** → **私人令牌**（Personal Access Token）
2. 勾选权限：`projects`、`pull_requests`、`issues`、`notes`
3. 复制生成的令牌

## 配置环境变量

令牌**不写进仓库**。`.mcp.json` 里只引用变量 `${GITEE_ACCESS_TOKEN}`，真值由系统环境变量提供。

PowerShell（永久生效，需重开终端并重启 Claude Code）：

```powershell
setx GITEE_ACCESS_TOKEN "你的令牌"
```

bash / zsh：

```bash
export GITEE_ACCESS_TOKEN="你的令牌"   # 写进 ~/.bashrc / ~/.zshrc 以长期有效
```

## 安装

```bash
# 把本市场加进 Claude Code
claude plugin marketplace add local /d/code/toy_and_tools/my_claude_code_market

# 安装插件
claude plugin install gitee-mcp
```

装完在会话里 `/mcp` 能看到 `gitee`，并标注来自插件。也可以不安装、临时试用：

```bash
claude --plugin-dir ./plugins/gitee-mcp
```

## 能干什么

| 类别 | 工具 |
| --- | --- |
| 仓库 | `list_user_repos`、`create_repo`、`fork_repository`、`get_file_content`、`search_files_by_content`、`compare_branches_tags`、`create_release`、`list_releases`、`search_open_source_repositories` |
| Pull Request | `list_repo_pulls`、`create_pull`、`update_pull`、`get_pull_detail`、`get_diff_files`、`merge_pull`、`manage_pull_review` |
| Issue | `list_repo_issues`、`get_repo_issue_detail`、`create_issue`、`update_issue`、`create_comment`、`list_comments` |
| 用户 / 通知 | `get_user_info`、`search_users`、`list_user_notifications` |

典型流程：读 Issue → 本地改代码 → `create_pull` 建 PR 并自动填描述 → `get_diff_files` 自查 → 评审通过后 `merge_pull`。

⚠️ 本插件是**全读写**的，`create_repo` / `create_pull` / `merge_pull` 这类写操作会直接落到 Gitee 上，不经过二次确认。

## 工具全名（写规则时必须用全名）

插件自带的 MCP 工具，调用名带插件名前缀：

```text
mcp__gitee-mcp_gitee__list_repo_issues
mcp__gitee-mcp_gitee__create_repo
```

在 permission rules、Skill 的 `allowed-tools`、subagent 的 `tools`、hook matcher 里都要用这个全名；
写 `mcp__gitee__.*` 永远不会命中。

想收口权限，在 `settings.json` 里加，例如：

```json
{
  "permissions": {
    "allow": [
      "mcp__gitee-mcp_gitee__list_repo_issues",
      "mcp__gitee-mcp_gitee__get_file_content"
    ],
    "deny": [
      "mcp__gitee-mcp_gitee__merge_pull"
    ]
  }
}
```

更彻底的办法是用 Gitee MCP 服务端自带的工具过滤——在 `.mcp.json` 的 `headers` 里加一行，
白名单优先于黑名单：

```json
"headers": {
  "Authorization": "Bearer ${GITEE_ACCESS_TOKEN}",
  "X-MCP-Enabled-Tools": "list_user_repos,get_file_content,list_repo_issues,create_pull,merge_pull"
}
```

## 关于 alwaysLoad

`.mcp.json` 里设了 `"alwaysLoad": true`，让这 30 来个工具在会话启动时就进上下文，
不用等模型先搜索工具。代价是每次启动多占一点上下文——删掉这一行就恢复成按需加载。

## 排错

| 现象 | 原因 / 处理 |
| --- | --- |
| `/mcp` 里 gitee 连不上 | 检查 `GITEE_ACCESS_TOKEN` 是否在**启动 Claude Code 的那个**环境里（`setx` 后要重开终端） |
| 401 / 认证失败 | 令牌过期或权限没勾全，重新生成并确认 `projects` / `pull_requests` / `issues` / `notes` 都在 |
| 变量没被替换成真值 | `.mcp.json` 里必须原样写 `${GITEE_ACCESS_TOKEN}`，别提前填成明文令牌（会进 git） |
| 公司网络访问不了 | `https://api.gitee.com/mcp` 被拦，可换成本地 stdio 版，见下 |

## 备选：本地 stdio 版

不想让令牌经过 Gitee 云端、或网络访问不了云端端点时，改用本地二进制
（`npx -y @gitee/mcp-gitee@latest`），令牌只交给本机进程。把 `.mcp.json` 换成：

```json
{
  "mcpServers": {
    "gitee": {
      "command": "npx",
      "args": ["-y", "@gitee/mcp-gitee@latest"],
      "env": {
        "GITEE_API_BASE": "https://gitee.com/api/v5",
        "GITEE_ACCESS_TOKEN": "${GITEE_ACCESS_TOKEN}"
      }
    }
  }
}
```

注意：本地版没有 `alwaysLoad` 之外的远程特性（`X-MCP-Enabled-Tools` 请求头过滤是远程版专属），
要限制工具集得改用 `--enabled-toolsets` / `ENABLED_TOOLSETS` 环境变量。

## 参考

- Gitee MCP Server 源码：https://gitee.com/oschina/mcp-gitee
- Gitee 帮助中心：https://help.gitee.com/ai-productivity/mcp-server
- Claude Code 插件文档：https://code.claude.com/docs/en/plugins
- Claude Code MCP 文档：https://code.claude.com/docs/en/mcp
