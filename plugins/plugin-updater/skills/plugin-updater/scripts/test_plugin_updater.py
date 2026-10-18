#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_plugin_updater.py — plugin_updater.py check pin 线的回归自测。

覆盖：外部条目解析（github 引用式过滤、pin 字段提取、无 metadata 兜底）、
git ls-remote 输出解析（`main` 模式同时命中 changeset-release/main 时取精确行）、
pin 比对（已最新 / 有更新 / 无基线，SHA 大小写不敏感）、
上游版本号解析（合法 JSON / 坏 JSON / 缺字段 / 非对象）、
run_check 注入编排（假 head / 假版本号 / 单条目远端失败不中断其余条目）、
报告生成（中文措辞、版本号未知、无基线附 head、汇总行）、
退出码（全部最新 0 / 有更新或无基线或查询失败 1）。

接缝全在内存：远端 head 与上游版本号都是注入的假函数，不碰网络
（真实网络路径靠真跑一次 check 覆盖，见票 01 验收）。

用法:
    python test_plugin_updater.py

退出码:
    0  全部通过
    1  有用例失败
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plugin_updater import (
    build_report,
    decide_exit_code,
    judge_entry,
    parse_external_entries,
    parse_ls_remote_output,
    parse_upstream_plugin_json,
    run_check,
)


def make_marketplace():
    """迷你市场：本地路径条目 / github+pin / github 无 metadata 三种形态各一。"""
    return {
        "plugins": [
            {"name": "local-plugin", "description": "本地条目",
             "source": "./plugins/local-plugin"},
            {"name": "mattpocock-skills", "description": "外部聚合带 pin",
             "source": {"source": "github", "repo": "mattpocock/skills"},
             "metadata": {"pinnedRef": "main", "pinnedSha": "49dd158d1076"}},
            {"name": "obsidian-skills", "description": "外部无 pin",
             "source": {"source": "github", "repo": "kepano/obsidian-skills"}},
        ]
    }


def make_results():
    """用与真实市场同构的两条目走一遍注入的 run_check，供报告/退出码用例复用。"""
    entries = parse_external_entries(make_marketplace())
    heads = {("mattpocock/skills", "main"): "49dd158d1076",
             ("kepano/obsidian-skills", "HEAD"): "abc999ff00"}
    versions = {("mattpocock/skills", "49dd158d1076"): "1.3.1",
                ("kepano/obsidian-skills", "abc999ff00"): None}
    return run_check(entries,
                     fetch_head=lambda repo, ref: heads[(repo, ref)],
                     fetch_version=lambda repo, sha: versions[(repo, sha)])


# ---------------------------------------------------------------- 条目解析

def test_parse_external_entries():
    """只取 source.source==github 的条目；pin 字段进 dict，无 metadata 兜底 None。"""
    entries = parse_external_entries(make_marketplace())
    assert [e["name"] for e in entries] == ["mattpocock-skills", "obsidian-skills"], \
        "本地路径条目应被过滤，github 条目按市场顺序保留"
    assert entries[0]["repo"] == "mattpocock/skills"
    assert entries[0]["pinned_ref"] == "main"
    assert entries[0]["pinned_sha"] == "49dd158d1076"
    assert entries[1]["repo"] == "kepano/obsidian-skills"
    assert entries[1]["pinned_ref"] is None and entries[1]["pinned_sha"] is None, \
        "无 metadata 的 github 条目应兜底为无 pin"


def test_parse_ls_remote_exact_ref():
    """`main` 模式会同时命中 refs/heads/changeset-release/main——必须取精确 ref 行。"""
    out = ("f7f05086e564eff660e11273608469644c86c1c1\trefs/heads/changeset-release/main\n"
           "49dd158d1076134a641b33efb035946536778336\trefs/heads/main\n")
    assert parse_ls_remote_output(
        out, "main") == "49dd158d1076134a641b33efb035946536778336", \
        "changeset-release/main 在前也不能误当 head"
    assert parse_ls_remote_output("abc111\tHEAD\n", "HEAD") == "abc111"
    assert parse_ls_remote_output("abc222\trefs/tags/v1.2.3\n", "v1.2.3") == "abc222"
    try:
        parse_ls_remote_output(out, "no-such-ref")
        raise AssertionError("无匹配 ref 的输出应报错而不是静默返回")
    except ValueError:
        pass


# ---------------------------------------------------------------- pin 比对

def test_judge_up_to_date_and_update():
    """pin==head（大小写不敏感）-> 已最新；不等 -> 有更新，head/版本号随行。"""
    r = judge_entry({"name": "m", "repo": "a/b", "pinned_ref": "main",
                     "pinned_sha": "49DD158D"}, "49dd158d", "1.3.1")
    assert r["status"] == "up-to-date", "SHA 比对应大小写不敏感"
    assert r["head"] == "49dd158d" and r["upstream_version"] == "1.3.1"

    r = judge_entry({"name": "m", "repo": "a/b", "pinned_ref": "main",
                     "pinned_sha": "000000"}, "49dd158d", "1.3.1")
    assert r["status"] == "update-available"


def test_judge_no_baseline():
    """无 pin 条目 -> 无基线，但仍带当前 head 供人工确认。"""
    r = judge_entry({"name": "o", "repo": "c/d", "pinned_ref": None,
                     "pinned_sha": None}, "abc999", "0.2.1")
    assert r["status"] == "no-baseline"
    assert r["head"] == "abc999" and r["upstream_version"] == "0.2.1", \
        "无基线报告要附上游当前 head"


# ---------------------------------------------------------------- 版本号解析

def test_parse_upstream_plugin_json():
    """合法 JSON 取 version；坏 JSON / 缺字段 / 非对象都返回 None（版本号未知）。"""
    assert parse_upstream_plugin_json(
        b'{"name": "skills", "version": "1.3.1"}') == "1.3.1"
    assert parse_upstream_plugin_json(b'<html>502</html>') is None
    assert parse_upstream_plugin_json(b'{"name": "skills"}') is None
    assert parse_upstream_plugin_json(b'["not", "an", "object"]') is None
    assert parse_upstream_plugin_json('{"version": "中文1.0"}'.encode("utf-8")) == "中文1.0"


# ---------------------------------------------------------------- 编排（注入接缝）

def test_run_check_wires_injected_seams():
    """假 head/假版本号注入后，pin 线判定按条目独立成立。"""
    results = make_results()
    by_name = {r["name"]: r for r in results}
    assert by_name["mattpocock-skills"]["status"] == "up-to-date"
    assert by_name["mattpocock-skills"]["upstream_version"] == "1.3.1"
    assert by_name["obsidian-skills"]["status"] == "no-baseline"
    assert by_name["obsidian-skills"]["head"] == "abc999ff00"
    assert by_name["obsidian-skills"]["upstream_version"] is None, \
        "拉不到版本号不致命，只是未知"


def test_run_check_fetch_failure_isolated():
    """单条目远端查询失败 -> 该条目 status=error，其余条目照常判定。"""
    entries = parse_external_entries(make_marketplace())

    def boom(repo, ref):
        if repo.startswith("mattpocock"):
            raise RuntimeError("网络断了")
        return "abc999ff00"

    results = run_check(entries, fetch_head=boom, fetch_version=lambda repo, sha: None)
    by_name = {r["name"]: r for r in results}
    assert by_name["mattpocock-skills"]["status"] == "error"
    assert "网络断了" in by_name["mattpocock-skills"]["error"]
    assert by_name["obsidian-skills"]["status"] == "no-baseline", \
        "一条查不到不应中断其余条目的检查"


# ---------------------------------------------------------------- 报告与退出码

def mk_result(status):
    return {"name": "x", "repo": "a/b", "pinned_ref": "main",
            "pinned_sha": "s", "head": "h", "upstream_version": None,
            "status": status}


def test_build_report():
    """报告逐条目中文措辞：已最新 / 无基线附 head / 版本号未知 / 汇总计数。"""
    lines = build_report(make_results())
    text = "\n".join(lines)
    assert "已最新" in text and "mattpocock-skills" in text
    assert "1.3.1" in text, "有版本号时应展示上游版本"
    assert "无基线" in text and "abc999ff00" in text, "无基线结论要附当前 head"
    assert "版本号未知" in text, "拉不到版本号要明说未知"
    assert "汇总" in text and "1" in text and "1" in text, "汇总行给各结论计数"


def test_build_report_error_entry():
    """查询失败的条目在报告里有失败说明而不是被吞掉。"""
    entries = parse_external_entries(make_marketplace())

    def boom(repo, ref):
        raise RuntimeError("远端不可达")

    lines = build_report(run_check(entries, fetch_head=boom,
                                   fetch_version=lambda repo, sha: None))
    text = "\n".join(lines)
    assert "远端不可达" in text, "失败原因要进报告"
    assert "查询失败" in text


def test_decide_exit_code():
    """全部最新 -> 0；有更新 / 无基线 / 查询失败 -> 1。"""
    assert decide_exit_code([mk_result("up-to-date"),
                             mk_result("up-to-date")]) == 0
    assert decide_exit_code([mk_result("up-to-date"),
                             mk_result("update-available")]) == 1
    assert decide_exit_code([mk_result("no-baseline")]) == 1
    assert decide_exit_code([mk_result("error")]) == 1


# ---------------------------------------------------------------- 入口

TESTS = [
    test_parse_external_entries,
    test_parse_ls_remote_exact_ref,
    test_judge_up_to_date_and_update,
    test_judge_no_baseline,
    test_parse_upstream_plugin_json,
    test_run_check_wires_injected_seams,
    test_run_check_fetch_failure_isolated,
    test_build_report,
    test_build_report_error_entry,
    test_decide_exit_code,
]


def main():
    failed = []
    for fn in TESTS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed.append(fn.__name__)
            print(f"FAIL  {fn.__name__}: {e}")
    total = len(TESTS)
    print(f"\n{total - len(failed)}/{total} 通过")
    if failed:
        print("失败用例: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
