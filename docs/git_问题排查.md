# Marketplace 故障排除文档

## 常见问题

### 1. SSH 权限问题：`Permission denied (publickey)`

**错误信息：**
```
Failed to clone repository: Cloning into '/root/.claude/plugins/cache/...'...
git@github.com: Permission denied (publickey).
fatal: Could not read from remote repository.
```

**原因：**
Claude Code 默认使用 SSH (`git@github.com`) 来克隆 GitHub 仓库，但系统没有配置 SSH 密钥。

**解决方案：**

配置 Git 自动使用 HTTPS 而不是 SSH：

```bash
# 将 git@github.com URL 转换为 https://github.com
git config --global url."https://github.com/".insteadOf "git@github.com:"

# 将 ssh://git@github.com URL 转换为 https://github  
git config --global url."https://github.com/".insteadOf "ssh://git@github.com/"
```

**验证配置：**
```bash
# 检查配置
git config --global --list | grep url

# 测试 URL 转换
git ls-remote --get-url git@github.com:user/repo
# 应输出: https://github.com/user/repo
```

**重要提示：**
- 配置后需要重启 Claude Code 才能生效
- 这个配置对所有 Git 操作全局生效
- 适用于公开仓库，私有仓库仍需配置认证

---

### 2. 主机密钥验证失败

**错误信息：**
```
No ECDSA host key is known for github.com and you have requested strict checking.
Host key verification failed.
```

**解决方案：**

添加 GitHub 主机密钥到 `known_hosts`：

```bash
ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts
ssh-keyscan -t ecdsa github.com >> ~/.ssh/known_hosts
ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts
```

---

### 3. Plugin manifest 格式错误

**错误信息：**
```
Plugin has an invalid manifest file at .../plugin.json
Validation errors: author: Invalid input: expected object, received string
```

**原因：**
`plugin.json` 中的 `author` 字段应该是对象，不是字符串。

**解决方案：**

```json
// ❌ 错误格式
{
  "author": "yuelezhou"
}

// ✅ 正确格式
{
  "author": {
    "name": "yuelezhou"
  }
}
```

---

## Marketplace 配置参考

### 本地插件

对于同一仓库中的插件：

```json
{
  "name": "my-plugin",
  "description": "我的插件",
  "source": "./plugins/my-plugin"
}
```

路径相对于 marketplace 根目录解析（包含 `.claude-plugin/` 的目录）。

### 远程 GitHub 插件

```json
{
  "name": "remote-plugin",
  "description": "远程插件",
  "source": {
    "source": "github",
    "repo": "owner/repo-name"
  },
  "homepage": "https://github.com/owner/repo-name"
}
```

---

## 完整的 Git 配置命令

一键修复 SSH 权限问题：

```bash
# 添加 GitHub 主机密钥
ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts 2>/dev/null
ssh-keyscan -t ecdsa github.com >> ~/.ssh/known_hosts 2>/dev/null

# 配置 HTTPS 代替 SSH
git config --global url."https://github.com/".insteadOf "git@github.com:"
git config --global url."https://github.com/".insteadOf "ssh://git@github.com:"

# 验证
echo "✅ 配置完成！请重启 Claude Code"
```

---

## 恢复默认 Git 配置

如果需要恢复默认行为：

```bash
git config --global --unset url."https://github.com/".insteadOf
git config --global --unset url."https://github.com/".insteadOf
```
