#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_plugin.py — Claude Code 插件发布前静态校验。

验证一个插件目录能否被 Claude Code 正确识别、加载、运行：
plugin.json 必填字段、skills/*/SKILL.md frontmatter、agents/*.md、
JSON 组件（.mcp.json / hooks/hooks.json 等）、scripts/*.py 语法、
SKILL.md 引用的相对路径、marketplace.json 注册与 description 一致性。

其他插件提交/发布前必须跑一遍，0 error 才能发布（warning 需逐条人工确认）。

用法:
    python check_plugin.py <插件目录> [更多目录...]
    python check_plugin.py --standalone <插件目录>   # 不属于本仓库市场的独立插件

退出码:
    0  无 error（warning 不阻塞，但发布前逐条确认）
    1  有 error
    2  用法/输入错误
"""

import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
KEBAB_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# SKILL.md 里提到的相对路径（references/xxx、scripts/xxx、data/xxx）
REF_PATH_RE = re.compile(
    r"(?<![\w/\\])((?:references|scripts|data|assets)/[A-Za-z0-9_\-./]+)")
JSON_COMPONENTS = [
    ".mcp.json",
    "mcp.json",
    "hooks/hooks.json",
    ".lsp.json",
    "monitors/monitors.json",
    "settings.json",
]
WALK_EXCLUDE = {"__pycache__", ".git", "node_modules", ".venv", "venv"}


def read_text(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def parse_frontmatter(text):
    """极简 frontmatter 解析：只取顶层 key，支持 `|`/`>` 块标量与空值缩进块。
    没有 frontmatter 返回 None。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    meta, key, block = {}, None, None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z][\w-]*):(?:\s+(.*))?$", line)
        if m:
            if key is not None and block is not None:
                meta[key] = "\n".join(block).strip()
            key, val = m.group(1), (m.group(2) or "").strip()
            if val in ("|", "|-", ">", ">-") or val == "":
                block = []
            else:
                meta[key] = val.strip("'\"")
                key, block = None, None
        elif key is not None and block is not None:
            block.append(line)
    if key is not None and block is not None:
        meta[key] = "\n".join(block).strip()
    return meta


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def check_skills(rep, plugin_dir):
    skills_dir = os.path.join(plugin_dir, "skills")
    if not os.path.isdir(skills_dir):
        return
    for entry in sorted(os.listdir(skills_dir)):
        skill_dir = os.path.join(skills_dir, entry)
        if not os.path.isdir(skill_dir):
            continue
        if not os.path.isfile(os.path.join(skill_dir, "SKILL.md")):
            # 类别目录（嵌套 skills，如 skills/engineering/<名>/SKILL.md）：递归一层
            sub_skills = [s for s in sorted(os.listdir(skill_dir))
                          if os.path.isfile(os.path.join(skill_dir, s, "SKILL.md"))]
            if sub_skills:
                for s in sub_skills:
                    _check_one_skill(rep, f"{entry}/{s}", os.path.join(skill_dir, s))
                continue
            rep.warn(f"skills/{entry}/ 无有效 skill（归档/类别目录，仅含说明文件）")
            continue
        _check_one_skill(rep, entry, skill_dir)


def _check_one_skill(rep, entry, skill_dir):
    sm_path = os.path.join(skill_dir, "SKILL.md")
    try:
        text = read_text(sm_path)
    except UnicodeDecodeError as e:
        rep.error(f"skills/{entry}/SKILL.md 不是 UTF-8: {e}")
        return
    meta = parse_frontmatter(text)
    if meta is None:
        rep.error(f"skills/{entry}/SKILL.md 缺少 frontmatter（开头 --- ... ---）")
        return
    sname = meta.get("name")
    if not sname:
        rep.error(f"skills/{entry}/SKILL.md frontmatter 缺少 name")
    elif sname != os.path.basename(entry):
        rep.error(f"skills/{entry}/SKILL.md frontmatter name ({sname}) 与目录名 ({os.path.basename(entry)}) 不一致")
    elif not KEBAB_RE.match(sname):
        rep.warn(f"skill 名 {sname} 不是 kebab-case（小写字母/数字/连字符）")
    sdesc = str(meta.get("description", "")).strip()
    if not sdesc:
        rep.error(f"skills/{entry}/SKILL.md frontmatter 缺少 description")
    elif len(sdesc) < 30:
        rep.warn(f"skills/{entry}/SKILL.md description 偏短——它是触发依据，应写清何时用/不用于")
    body = re.sub(r"\A---.*?---", "", text, count=1, flags=re.S)
    if len(body.strip()) < 10:
        rep.warn(f"skills/{entry}/SKILL.md 正文为空")
    for ref in sorted(set(REF_PATH_RE.findall(text))):
        if not os.path.exists(os.path.join(skill_dir, ref)):
            rep.warn(f"skills/{entry}/SKILL.md 提到 {ref} 但文件不存在（外部路径/示例可忽略）")


def check_agents(rep, plugin_dir):
    agents_dir = os.path.join(plugin_dir, "agents")
    if not os.path.isdir(agents_dir):
        return
    for fname in sorted(os.listdir(agents_dir)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(agents_dir, fname)
        try:
            text = read_text(path)
        except UnicodeDecodeError as e:
            rep.error(f"agents/{fname} 不是 UTF-8: {e}")
            continue
        meta = parse_frontmatter(text)
        if meta is None:
            rep.error(f"agents/{fname} 缺少 frontmatter，不会被识别为 agent")
            continue
        if not meta.get("name"):
            rep.error(f"agents/{fname} frontmatter 缺少 name")
        if not str(meta.get("description", "")).strip():
            rep.warn(f"agents/{fname} frontmatter 缺少 description")


def check_json_components(rep, plugin_dir):
    for rel in JSON_COMPONENTS:
        path = os.path.join(plugin_dir, rel)
        if not os.path.isfile(path):
            continue
        try:
            data = json.loads(read_text(path))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            rep.error(f"{rel} 不是合法 JSON: {e}")
            continue
        if rel == ".mcp.json" and not (isinstance(data, dict) and data.get("mcpServers")):
            rep.warn(".mcp.json 缺少 mcpServers 键")
        if rel == "hooks/hooks.json" and isinstance(data, dict) and not data.get("hooks"):
            rep.warn("hooks.json 缺少 hooks 键")


def check_python_scripts(rep, plugin_dir):
    for root, dirs, files in os.walk(plugin_dir):
        dirs[:] = [d for d in dirs if d not in WALK_EXCLUDE]
        for fname in sorted(files):
            if not fname.endswith(".py"):
                continue
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, plugin_dir)
            try:
                src = read_text(path)
            except UnicodeDecodeError as e:
                rep.error(f"{rel} 不是 UTF-8，Python 脚本必须 UTF-8: {e}")
                continue
            try:
                compile(src, path, "exec")
            except SyntaxError as e:
                rep.error(f"{rel} Python 语法错误: {e}")


def find_marketplace(start_dir):
    d = os.path.abspath(start_dir)
    for _ in range(5):
        cand = os.path.join(d, ".claude-plugin", "marketplace.json")
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    return None


def marketplace_root(mp_path):
    """source 路径的基准目录：marketplace.json 所在仓库的根目录
    （.claude-plugin/marketplace.json 时取其上两级，根级时取其上一级）。"""
    mp_dir = os.path.dirname(mp_path)
    if os.path.basename(mp_dir) == ".claude-plugin":
        return os.path.dirname(mp_dir)
    return mp_dir


def check_marketplace(rep, plugin_dir, pj, standalone):
    if standalone:
        return
    name = pj.get("name")
    if not name:
        return  # name 缺失已单独报错
    mp_path = find_marketplace(plugin_dir)
    if mp_path is None:
        return
    try:
        mp = json.loads(read_text(mp_path))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        rep.warn(f"marketplace.json 无法解析: {e}")
        return
    entries = mp.get("plugins", []) if isinstance(mp, dict) else []
    hit = next((e for e in entries if isinstance(e, dict) and e.get("name") == name), None)
    if hit is None:
        rep.error(f"未注册进 {os.path.relpath(mp_path, plugin_dir)} 的 plugins 数组"
                  f"（本仓库规则：发布前必须注册，见根目录 AGENTS.md）")
        return
    src = hit.get("source")
    if src is None:
        rep.warn("marketplace.json 条目缺少 source 字段")
    elif isinstance(src, str):
        src_path = os.path.realpath(os.path.join(marketplace_root(mp_path), src))
        if src_path != os.path.realpath(plugin_dir):
            rep.error(f"marketplace.json source 指向 {src}，与当前插件目录不一致")
    # dict 形式的 source（如 github 外部插件）无法本地比对路径，跳过
    mdesc = str(hit.get("description", "") or "").strip()
    pdesc = str(pj.get("description", "") or "").strip()
    if mdesc and pdesc and mdesc != pdesc:
        rep.warn("plugin.json 与 marketplace.json 的 description 不一致（两处需人工同步）")


MINIMAX_CATEGORIES = {
    "Office", "Studio", "Design & Sites", "Code", "Business", "Sales",
    "Productivity", "Science & Healthcare", "Education", "Other",
}
# 取自 Desktop app.asar 中 readMiniMaxPluginPackage 的 MANIFEST_FIELDS（封闭集）
MINIMAX_FIELDS = {
    "$schema", "schemaVersion", "name", "displayName", "version", "description",
    "author", "icon", "darkIcon", "category", "exampleQueries", "apps",
    "mcpServers", "skills", "hooks", "hostBindings",
}
MINIMAX_REQUIRED = {
    "schemaVersion", "name", "version", "description", "author", "icon",
    "category", "exampleQueries", "apps", "mcpServers", "skills",
}
AGENT_FIELDS = {
    "$schema", "name", "version", "description", "author",
    "homepage", "repository", "license", "keywords", "extensions",
}
AGENT_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def check_minimax_manifest(rep, plugin_dir, pj):
    """MiniMax Plugin V1 清单：.minimax-plugin/plugin.json。

    根目录 plugin.json（Agent Plugins 1.0）只有在被该读取器完整接受时才优先；
    本仓库统一使用 .minimax-plugin/ 形态，故根清单改为可选。
    """
    mp = os.path.join(plugin_dir, ".minimax-plugin", "plugin.json")
    if not os.path.isfile(mp):
        rep.error("缺少 .minimax-plugin/plugin.json（MiniMax Plugin V1 入口清单）")
        return
    try:
        data = json.loads(read_text(mp))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        rep.error(f".minimax-plugin/plugin.json 不是合法 JSON: {e}")
        return
    if not isinstance(data, dict):
        rep.error(".minimax-plugin/plugin.json 顶层必须是 JSON 对象")
        return

    missing = MINIMAX_REQUIRED - set(data)
    if missing:
        rep.error(f".minimax-plugin/plugin.json 缺必填字段: {', '.join(sorted(missing))}")
    unknown = set(data) - MINIMAX_FIELDS
    if unknown:
        rep.error(f".minimax-plugin/plugin.json 含封闭集外字段: {', '.join(sorted(unknown))}")
    if data.get("schemaVersion") != 1:
        rep.error(f".minimax-plugin/plugin.json schemaVersion 必须为 1，实际 {data.get('schemaVersion')}")
    if data.get("name") != pj.get("name"):
        rep.error(f".minimax-plugin name ({data.get('name')}) 与 .claude-plugin 清单 name ({pj.get('name')}) 不一致")
    if data.get("version") != pj.get("version"):
        rep.warn(f".minimax-plugin version ({data.get('version')}) 与 .claude-plugin 清单 version ({pj.get('version')}) 不一致")
    if data.get("category") not in MINIMAX_CATEGORIES:
        rep.error(f".minimax-plugin category 非法: {data.get('category')}")
    if data.get("apps") != []:
        rep.error(".minimax-plugin apps 必须为 []（本地插件不支持 App 能力）")
    eq = data.get("exampleQueries")
    if not isinstance(eq, list) or not eq:
        rep.error(".minimax-plugin exampleQueries 必须为非空数组")
    for key in ("icon", "darkIcon"):
        v = data.get(key)
        if not isinstance(v, str) or not v.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            rep.error(f".minimax-plugin {key} 扩展名非法: {v}")
        elif not os.path.isfile(os.path.join(plugin_dir, v.replace("/", os.sep))):
            rep.error(f".minimax-plugin {key} 引用的文件不存在: {v}")
    caps = sum(len(data.get(k) or []) for k in ("mcpServers", "skills", "hooks"))
    if caps == 0:
        rep.error(".minimax-plugin 未声明任何能力（mcpServers/skills/hooks 至少一项非空）")
    for s in data.get("skills") or []:
        if not re.match(r"^skills/[^/]+/SKILL\.md$", s):
            rep.error(f".minimax-plugin skills 路径格式非法: {s}")
        elif not os.path.isfile(os.path.join(plugin_dir, s.replace("/", os.sep))):
            rep.error(f".minimax-plugin skills 引用的文件不存在: {s}")
    for m in data.get("mcpServers") or []:
        if not os.path.isfile(os.path.join(plugin_dir, m.replace("/", os.sep))):
            rep.error(f".minimax-plugin mcpServers 引用的文件不存在: {m}")


def check_agent_plugins_spec(rep, plugin_dir, pj):
    """根目录 plugin.json（Agent Plugins 1.0 便携清单）——可选。

    运行时优先级：根 plugin.json 仅在被 Agent Plugins 1.0 读取器完整接受时上位，
    否则自动穿透到 .minimax-plugin/。本仓库已统一走 .minimax-plugin/，故根清单
    存在时只做一致性核对，缺失不再报错。
    """
    root_pj = os.path.join(plugin_dir, "plugin.json")
    if not os.path.isfile(root_pj):
        return
    try:
        data = json.loads(read_text(root_pj))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        rep.warn(f"根目录 plugin.json 不是合法 JSON（会被运行时忽略）: {e}")
        return
    if os.path.isfile(os.path.join(plugin_dir, ".minimax-plugin", "plugin.json")):
        rep.warn("根 plugin.json 与 .minimax-plugin/ 并存——根清单会先被 Agent Plugins 1.0 读取器接受，"
                 "导致 .minimax-plugin 的图标/分类/示例查询不生效")
    if data.get("$schema") != AGENT_SCHEMA:
        rep.error(f"根 plugin.json $schema 应为 {AGENT_SCHEMA}，实际 {data.get('$schema')}")
    if data.get("name") != pj.get("name"):
        rep.error(f"根 plugin.json name ({data.get('name')}) 与 .claude-plugin 清单 name ({pj.get('name')}) 不一致")
    if data.get("version") != pj.get("version"):
        rep.warn(f"根 plugin.json version ({data.get('version')}) 与 .claude-plugin 清单 version ({pj.get('version')}) 不一致")
    extra = set(data) - AGENT_FIELDS
    if extra:
        rep.warn(f"根 plugin.json 含规范外字段: {', '.join(sorted(extra))}")


def check_minimax_compat(rep, plugin_dir):
    """MiniMax Code Desktop 兼容性检查。

    依据 Desktop 运行时（app.asar 内 readAgentPluginPackage / readMiniMaxPluginPackage）：
    - 清单优先级：根 plugin.json（Agent Plugins 1.0）仅在被完整接受时上位，
      否则穿透到 .minimax-plugin/plugin.json，再到 .claude-plugin/（vendor）、.codex-plugin/。
    - skills 由 skills/<name>/SKILL.md 自动发现；每插件上限 64 skill、8 个 MCP。
    - 自定义 agents/commands/LSP 不支持。
    - .mcp.json（Claude/ZCode 方言）与 mcp.json（MiniMax 方言）允许不同，
      但服务器身份（名字/URL）必须一致。
    """
    agents_dir = os.path.join(plugin_dir, "agents")
    if os.path.isdir(agents_dir) and any(f.endswith(".md") for f in os.listdir(agents_dir)):
        rep.warn("agents/ 自定义 agent 在 MiniMax Code 不支持（该组件在 Claude/ZCode 仍可用）")

    dot_mcp = os.path.join(plugin_dir, ".mcp.json")
    plain_mcp = os.path.join(plugin_dir, "mcp.json")
    if os.path.isfile(plain_mcp) and not os.path.isfile(dot_mcp):
        rep.warn("存在 mcp.json 但缺 .mcp.json——Claude/ZCode 读不到该 MCP 配置")
    if os.path.isfile(dot_mcp) and os.path.isfile(plain_mcp):
        try:
            a = json.loads(read_text(dot_mcp)).get("mcpServers") or {}
            b = json.loads(read_text(plain_mcp)).get("mcpServers") or {}
        except json.JSONDecodeError:
            a = b = None  # JSON 合法性已在组件检查中报告
        if a is not None and b is not None:
            if set(a) != set(b):
                rep.error(f".mcp.json 与 mcp.json 的 MCP 服务器集合不一致: "
                          f"{sorted(a)} vs {sorted(b)}")
            else:
                for sname in sorted(a):
                    ua = (a[sname] or {}).get("url")
                    ub = (b[sname] or {}).get("url")
                    if ua and ub and ua != ub:
                        rep.error(f"MCP [{sname}] 两份配置的 url 不一致: {ua} vs {ub}")
                    ta = (a[sname] or {}).get("type")
                    tb = (b[sname] or {}).get("type")
                    if ta != tb:
                        rep.warn(f"MCP [{sname}] transport 声明不同（{ta} / {tb}）——"
                                 f"方言差异属预期，仅确认各自客户端可接受")

    skills_dir = os.path.join(plugin_dir, "skills")
    if os.path.isdir(skills_dir):
        n = sum(1 for e in os.listdir(skills_dir)
                if os.path.isfile(os.path.join(skills_dir, e, "SKILL.md")))
        if n > 64:
            rep.error(f"skills 数量 {n} 超过 MiniMax 上限 64")
    for rel in (".mcp.json", "mcp.json"):
        p = os.path.join(plugin_dir, rel)
        if os.path.isfile(p):
            try:
                servers = json.loads(read_text(p)).get("mcpServers", {})
                if isinstance(servers, dict) and len(servers) > 8:
                    rep.warn(f"{rel} 含 {len(servers)} 个 MCP 服务器，超过 MiniMax 上限 8")
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                pass


def check_plugin_dir(plugin_dir, standalone=False):
    plugin_dir = os.path.abspath(plugin_dir)
    rep = Report()
    pj_path = os.path.join(plugin_dir, ".claude-plugin", "plugin.json")
    if not os.path.isfile(pj_path):
        rep.error(".claude-plugin/plugin.json 不存在——不是合法的插件目录")
        return rep
    try:
        pj = json.loads(read_text(pj_path))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        rep.error(f".claude-plugin/plugin.json 不是合法 UTF-8 JSON: {e}")
        return rep
    if not isinstance(pj, dict):
        rep.error(".claude-plugin/plugin.json 顶层必须是 JSON 对象")
        return rep

    name = pj.get("name")
    dir_name = os.path.basename(plugin_dir)
    if not name or not isinstance(name, str) or not name.strip():
        rep.error("plugin.json 缺少 name")
        name = None
    elif name != dir_name:
        rep.error(f"plugin.json name ({name}) 与目录名 ({dir_name}) 不一致")
    elif not KEBAB_RE.match(name):
        rep.warn(f"插件名 {name} 不是 kebab-case（小写字母/数字/连字符）")

    version = pj.get("version")
    if not version:
        rep.error("plugin.json 缺少 version")
    elif not SEMVER_RE.match(str(version)):
        rep.error(f"plugin.json version 不是 x.y.z 格式: {version}")

    description = pj.get("description")
    if not description or not str(description).strip():
        rep.error("plugin.json 缺少 description")
    elif len(str(description)) < 10:
        rep.warn("plugin.json description 过短，说不清插件用途")

    check_skills(rep, plugin_dir)
    check_agents(rep, plugin_dir)
    check_json_components(rep, plugin_dir)
    check_python_scripts(rep, plugin_dir)
    check_minimax_compat(rep, plugin_dir)
    check_minimax_manifest(rep, plugin_dir, pj)
    check_agent_plugins_spec(rep, plugin_dir, pj)
    if not os.path.isfile(os.path.join(plugin_dir, "README.md")):
        rep.warn("缺少 README.md（建议补一份插件说明）")
    check_marketplace(rep, plugin_dir, pj, standalone)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="Claude Code 插件发布前静态校验（0 error 才能发布）")
    ap.add_argument("plugin_dirs", nargs="+", help="插件目录（含 .claude-plugin/plugin.json），可传多个")
    ap.add_argument("--standalone", action="store_true",
                    help="独立插件：跳过 marketplace.json 注册检查")
    args = ap.parse_args(argv)

    total_errors = total_warnings = 0
    input_error = False
    for d in args.plugin_dirs:
        print(f"== {os.path.abspath(d)}")
        if not os.path.isdir(d):
            print("  ERROR   目录不存在")
            print()
            input_error = True
            continue
        rep = check_plugin_dir(d, standalone=args.standalone)
        for msg in rep.errors:
            print(f"  ERROR   {msg}")
        for msg in rep.warnings:
            print(f"  WARN    {msg}")
        if not rep.errors and not rep.warnings:
            print("  全部检查通过")
        print()
        total_errors += len(rep.errors)
        total_warnings += len(rep.warnings)

    if input_error:
        print("结果: 输入目录不存在")
        return 2
    if total_errors:
        print(f"结果: {total_errors} error, {total_warnings} warning — 未通过，修完 error 才能发布")
        return 1
    print(f"结果: 0 error, {total_warnings} warning — 通过（warning 请逐条人工确认后发布）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
