# My Claude Code Market

个人 agent skill 的统一管理与分发仓库：自研 skill 以插件形式在此版本化，经链接暴露给各 agent 的 skill 目录；第三方 skill 的安装记录在此登记以保证可复现。

## Language

### Skill 归属

**自研 skill**:
由本人在 market 仓库开发的 skill，正本固定在 `plugins/<name>/skills/<name>/`，经链接暴露给各 agent。
_Avoid_: 本地 skill、私有 skill

**第三方 skill**:
他人开发的 skill，正本即 `~/.agents/skills/` 里的安装实体，仓库只记账（PROMPT-INSTALL.md）不存源码。
_Avoid_: 外部 skill、引进 skill

**正本**:
一份 skill 唯一允许被编辑的那份拷贝；改动其他任何拷贝都构成漂移。自研 skill 的正本在 market 仓库，第三方 skill 的正本在 `~/.agents/skills/`。
_Avoid_: 源头、母本、master

**运行时枢纽（Hub）**:
`~/.agents/skills/` —— 跨 agent 公共 skill 目录。已确认原生读取：ZCode（实测）、OpenCode 与 DeepSeek Deep Code（官方文档）、MiniMax Code（本机 runtime 源码 `roots.ts` 确认，默认开启）；Claude Code 是目前已知唯一必须靠链接层的。自研 skill 以链接形式出现在这里，第三方 skill 以实体形式安装在这里。
_Avoid_: 共享目录、公共目录

**复现**:
在新机器上恢复全部 skill 的流程：clone market 仓库 → `python scripts/link_skills.py` 重建链接 → 按台账补装第三方 skill。
_Avoid_: 同步、恢复、迁移

**台账（PROMPT-INSTALL.md）**:
常用 skill 的声明式清单——只记「用什么、怎么装」，不记录安装状态；「哪个装了哪个没装」由 agent 定期核对，核对结果不回写台账。
_Avoid_: 安装记录、状态表

### 失效模式

**漂移**:
同一 skill 的多份拷贝内容不一致的状态。本仓库政策用「正本唯一 + 链接分发」消灭多份实拷贝来预防，而非靠手工同步来修补。
_Avoid_: 不同步、版本不一致

**残留拷贝**:
同一 skill 在非正本位置出现的实体目录（多为 agent 私有目录里的旧拷贝）。与正本内容一致的用 skill-distributor 的 `clean` 直接清理；不一致的默认保留、人工裁决（可能含未同步的独有修改）。
_Avoid_: 冗余拷贝、垃圾、重复文件
