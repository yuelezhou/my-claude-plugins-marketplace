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
        sm_path = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(sm_path):
            rep.error(f"skills/{entry}/ 缺少 SKILL.md")
            continue
        try:
            text = read_text(sm_path)
        except UnicodeDecodeError as e:
            rep.error(f"skills/{entry}/SKILL.md 不是 UTF-8: {e}")
            continue
        meta = parse_frontmatter(text)
        if meta is None:
            rep.error(f"skills/{entry}/SKILL.md 缺少 frontmatter（开头 --- ... ---）")
            continue
        sname = meta.get("name")
        if not sname:
            rep.error(f"skills/{entry}/SKILL.md frontmatter 缺少 name")
        elif sname != entry:
            rep.error(f"skills/{entry}/SKILL.md frontmatter name ({sname}) 与目录名 ({entry}) 不一致")
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
        # SKILL.md 提到的相对路径应存在（指向外部或其他 skill 的路径可忽略本警告）
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
