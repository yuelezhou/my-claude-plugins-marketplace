#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_plugin_updater.py — plugin_updater.py 的回归自测（pin 线 + 枢纽同步线 + 副本线）。

覆盖（票 01 pin 线）：外部条目解析（github 引用式过滤、pin 字段提取、无 metadata 兜底）、
git ls-remote 输出解析（`main` 模式同时命中 changeset-release/main 时取精确行）、
pin 比对（已最新 / 有更新 / 无基线，SHA 大小写不敏感）、
上游版本号解析（合法 JSON / 坏 JSON / 缺字段 / 非对象）、
run_check 注入编排（假 head / 假版本号 / 单条目远端失败不中断其余条目）、
报告生成（中文措辞、版本号未知、无基线附 head、汇总行）、
退出码（全部最新 0 / 有更新或无基线或查询失败 1）。

覆盖（票 02 枢纽线 + 副本线）：
族派生（三分类一级子目录、deprecated/in-progress 与散文件排除、缺 skills/ 报错）、
枢纽三方状态（已同步 / 与基线不一致（落后或手改）/ 缺失，tmp 枢纽 + tmp 假 tarball）、
run_hub_check 编排（无 pin 条目跳过、tarball 下载失败进 hub-error 不崩）、
download_to_file 的 file:// 离线路径、
副本线（ZCode 列表格式 / Claude Code 字典格式安装记录解析、本仓库市场识别、
外部副本判定与刷新命令、缺安装文件按未安装处理）、
枢纽线报告与副本线报告措辞、退出码纳入枢纽漂移。

接缝全在内存 / tmp：远端 head、版本号、tarball 都是注入的假函数或 tmp 夹具，
不碰网络（真实网络路径靠真跑一次 check 覆盖，见票 01/02 验收）。

用法:
    python test_plugin_updater.py

退出码:
    0  全部通过
    1  有用例失败
"""

import json
import os
import pathlib
import shutil
import sys
import tarfile
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plugin_updater import (
    build_copy_report,
    build_hub_report,
    build_report,
    collect_copy_line,
    decide_exit_code,
    derive_family_members,
    download_to_file,
    judge_entry,
    judge_hub_members,
    parse_external_entries,
    parse_ls_remote_output,
    parse_upstream_plugin_json,
    run_check,
    run_hub_check,
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


# ---------------------------------------------------------------- 族派生（票 02）

def test_derive_family_members():
    """族成员 = skills/ 下三分类的一级子目录；deprecated/in-progress 与散文件排除。"""
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, "tree")
        expected = make_upstream_tree(tree)
        fam = derive_family_members(tree)
        assert fam == expected, \
            "族清单应只含 engineering/productivity/misc 的一级子目录（含分类归属），" \
            "deprecated/in-progress 成员与 README/NOTICE 散文件一律排除"


def test_derive_family_members_missing_skills_dir():
    """上游树缺 skills/ 目录 -> ValueError（进 hub-error 通道，不静默当空族）。"""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            derive_family_members(tmp)
            raise AssertionError("缺 skills/ 目录应报错而不是返回空族")
        except ValueError:
            pass


# ---------------------------------------------------------------- 枢纽三方状态（票 02）

def test_judge_hub_members_three_states():
    """枢纽实体 vs pin tarball 内容：一致/不一致（手改或多文件）/缺失三分。"""
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, "tree")
        make_upstream_tree(tree)
        hub = make_hub_from_tree(tmp, tree)
        # code-review：内容被手改 -> 不一致
        with open(os.path.join(hub, "code-review", "SKILL.md"), "a",
                  encoding="utf-8") as f:
            f.write("手改一行\n")
        # wizard：多出一个基线没有的文件 -> 不一致
        write_text(os.path.join(hub, "wizard", "EXTRA.md"), "x\n")
        # grilling：枢纽整个缺 -> 缺失
        shutil.rmtree(os.path.join(hub, "grilling"))
        # tdd：连子目录（references/）原样拷贝 -> 已同步（子树内容也参与比对）

        fam = derive_family_members(tree)
        rows = judge_hub_members(fam, hub, tree)
        by = {r["name"]: r for r in rows}
        assert by["tdd"]["status"] == "hub-in-sync", "整树一致（含子目录）应判已同步"
        assert by["tdd"]["category"] == "engineering"
        assert by["code-review"]["status"] == "hub-drifted", "内容被手改应判不一致"
        assert by["wizard"]["status"] == "hub-drifted", "多出文件也应判不一致"
        assert by["grilling"]["status"] == "hub-missing", "枢纽缺条目应判缺失"

        # 枢纽里同名实体是个文件而不是目录 -> 也算不一致
        write_text(os.path.join(hub, "as-file"), "x")
        rows2 = judge_hub_members({"as-file": "misc"}, hub, tree)
        assert rows2[0]["status"] == "hub-drifted"


def test_judge_hub_members_missing_hub_dir():
    """枢纽目录整个不存在（新机器）-> 全部缺失，不崩。"""
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, "tree")
        make_upstream_tree(tree)
        fam = derive_family_members(tree)
        rows = judge_hub_members(fam, os.path.join(tmp, "no-such-hub"), tree)
        assert rows and all(r["status"] == "hub-missing" for r in rows)


def test_judge_hub_members_ignores_crlf():
    """行尾差异不算内容漂移：codeload 基线是 LF，Windows 安装链落盘常是 CRLF。"""
    with tempfile.TemporaryDirectory() as tmp:
        tree = os.path.join(tmp, "tree")
        make_upstream_tree(tree)
        hub = make_hub_from_tree(tmp, tree)
        # 把 tdd 实体重写为 CRLF 行尾（字节内容因此与基线不同，行内容相同）
        for dirpath, _dirnames, filenames in os.walk(os.path.join(hub, "tdd")):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                with open(p, "rb") as f:
                    data = f.read().replace(b"\r\n", b"\n")
                with open(p, "wb") as f:
                    f.write(data.replace(b"\n", b"\r\n"))
        rows = judge_hub_members(derive_family_members(tree), hub, tree)
        by = {r["name"]: r["status"] for r in rows}
        assert by["tdd"] == "hub-in-sync", "仅行尾不同（CRLF vs LF）应判已同步"
        assert by["code-review"] == "hub-in-sync"


# ---------------------------------------------------------------- 枢纽线编排（票 02）

def test_run_hub_check_skips_no_pin_and_judges():
    """无 pin 条目不进枢纽线；带 pin 条目下载 tarball 解包后逐成员判三方状态。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, tree = make_pin_tarball(tmp)
        hub = make_hub_from_tree(tmp, tree)
        calls = []

        def fake_tar(repo, sha, dest_dir, timeout=120):
            calls.append((repo, sha))
            assert os.path.isdir(dest_dir), "下载目标目录应由编排方建好"
            return tar_path

        results = run_hub_check(make_pinned_entries(), hub,
                                get_tarball=fake_tar,
                                work_root=os.path.join(tmp, "work"))
        assert calls == [("mattpocock/skills", "49dd158d1076")], \
            "只对带 pin 条目下载，且用 pinnedSha 而非 head"
        assert [r["name"] for r in results] == ["mattpocock-skills"], \
            "obsidian-skills 无 pin 无族，不进枢纽线"
        r = results[0]
        assert r["status"] == "hub-ok" and r["pinned_sha"] == "49dd158d1076"
        assert {m["name"]: m["status"] for m in r["members"]} == {
            "tdd": "hub-in-sync", "code-review": "hub-in-sync",
            "grilling": "hub-in-sync", "wizard": "hub-in-sync"}, \
            "从 tarball 动态派生的族实体在枢纽全部一致 -> 全部已同步"


def test_run_hub_check_reports_drift_and_missing():
    """枢纽与基线有差异时逐成员报不一致/缺失，而不是整条失败。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, tree = make_pin_tarball(tmp)
        hub = make_hub_from_tree(tmp, tree, omit=("grilling",))
        with open(os.path.join(hub, "tdd", "SKILL.md"), "a", encoding="utf-8") as f:
            f.write("手改\n")

        results = run_hub_check(make_pinned_entries()[:1], hub,
                                get_tarball=lambda repo, sha, dest_dir, timeout=120: tar_path,
                                work_root=os.path.join(tmp, "work"))
        by = {m["name"]: m["status"] for m in results[0]["members"]}
        assert by == {"tdd": "hub-drifted", "code-review": "hub-in-sync",
                      "wizard": "hub-in-sync", "grilling": "hub-missing"}
        assert results[0]["status"] == "hub-ok", \
            "成员级差异不改变条目状态，由报告与退出码表达"


def test_run_hub_check_download_failure_isolated():
    """tarball 下载失败（网络抖动）-> 该条目 hub-error 带可读错误，不崩不中断。"""
    with tempfile.TemporaryDirectory() as tmp:
        def boom(repo, sha, dest_dir, timeout=120):
            raise RuntimeError(
                f"tarball 下载失败（网络错误）: "
                f"https://codeload.github.com/{repo}/tar.gz/{sha}——连接超时")

        results = run_hub_check(make_pinned_entries(), os.path.join(tmp, "hub"),
                                get_tarball=boom,
                                work_root=os.path.join(tmp, "work"))
        assert len(results) == 1
        r = results[0]
        assert r["status"] == "hub-error"
        assert "HTTP" not in r["error"] and "codeload" in r["error"], "错误信息可读"
        assert r["members"] == []
        assert os.listdir(os.path.join(tmp, "work")) == [], \
            "失败后临时工作目录应被清理，不留半成品"


def test_download_to_file_offline():
    """download_to_file 的离线机制：file:// URL 也能拉到本地同内容文件。"""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "src.tar.gz")
        with open(src, "wb") as f:
            f.write(b"tarball-payload-\xe4\xb8\xad")
        dest = os.path.join(tmp, "out.tar.gz")
        download_to_file(pathlib.Path(src).as_uri(), dest, timeout=10)
        with open(dest, "rb") as f:
            assert f.read() == b"tarball-payload-\xe4\xb8\xad"


# ---------------------------------------------------------------- 副本线（票 02）

def test_collect_copy_line_from_tmp_files():
    """tmp 假安装记录：外部市场副本报版本/来源/sha+刷新命令；本市场副本不算；缺装报未安装。"""
    with tempfile.TemporaryDirectory() as tmp:
        root, (zc_inst, zc_known, cc_inst, cc_known) = make_copy_fixtures(tmp)
        rows = collect_copy_line(["mattpocock-skills", "obsidian-skills"], root,
                                 zcode_installed_path=zc_inst,
                                 zcode_known_path=zc_known,
                                 claude_installed_path=cc_inst,
                                 claude_known_path=cc_known)
        by = {(r["agent"], r["plugin"]): r for r in rows}

        zc = by[("zcode", "mattpocock-skills")]
        assert zc["status"] == "copy-foreign"
        rec = zc["records"][0]
        assert rec["version"] == "1.2.3", "已装版本要报出"
        assert rec["marketplace"] == "claude-plugins-official", "来源市场要报出"
        assert rec["sha"] == "3cca18b3ffff", "记录里的上游 sha 要报出"
        assert zc["commands"] == [
            "zcode plugins marketplace update claude-plugins-official",
            "zcode plugins plugin update mattpocock-skills@claude-plugins-official"], \
            "ZCode 外部副本附两条刷新命令"

        assert by[("zcode", "obsidian-skills")]["status"] == "copy-own-market", \
            "装自本仓库市场的副本不算其他市场副本（ZCode 侧 own-market 识别）"

        cc = by[("claude-code", "mattpocock-skills")]
        assert cc["status"] == "copy-foreign"
        assert cc["records"][0]["version"] == "1.2.3"
        assert cc["commands"] == [
            "claude plugin update mattpocock-skills@claude-plugins-official"], \
            "Claude Code 外部副本附一条刷新命令"

        assert by[("claude-code", "obsidian-skills")]["status"] == "copy-own-market", \
            "装自本仓库市场的副本不算其他市场副本，不打印刷新命令"

        for plugin in ("mattpocock-skills", "obsidian-skills"):
            row = by[("minimax", plugin)]
            assert row["status"] == "copy-not-installed"
            assert row["commands"] == []
            assert row["note"], "MiniMax 无独立安装记录，未安装附说明"

        # video-agent-kit 不是市场里的外部条目，整行不应出现
        assert all(r["plugin"] in ("mattpocock-skills", "obsidian-skills")
                   for r in rows)


def test_collect_copy_line_missing_files():
    """安装记录文件全缺（新机器）-> 各 agent 全报未安装，不抛异常。"""
    with tempfile.TemporaryDirectory() as tmp:
        missing = os.path.join(tmp, "nope.json")
        rows = collect_copy_line(["mattpocock-skills"], tmp,
                                 zcode_installed_path=missing,
                                 zcode_known_path=missing,
                                 claude_installed_path=missing,
                                 claude_known_path=missing)
        assert len(rows) == 3
        assert all(r["status"] == "copy-not-installed" for r in rows)
        assert all(r["commands"] == [] for r in rows)


# ---------------------------------------------------------------- 报告与退出码（票 02）

def test_build_hub_report():
    """枢纽线报告：逐成员中文状态、跳过无 pin 条目、失败条目带原因、小结计数。"""
    results = [hub_result(member_statuses=("hub-in-sync", "hub-drifted", "hub-missing")),
               hub_result(status="hub-error")]
    text = "\n".join(build_hub_report(results, hub_dir="HUB",
                                      skipped=["obsidian-skills"]))
    assert "枢纽同步线" in text
    assert "obsidian-skills" in text, "被跳过的无 pin 条目要有说明"
    assert "已同步" in text and "与基线不一致（落后或手改）" in text and "缺失" in text
    assert "49dd158d1076" in text, "逐条目标明基线 pin"
    assert "1 已同步" in text, "小结给各状态计数"
    assert "tarball 下载失败" in text, "枢纽线失败的条目带可读原因"


def test_build_copy_report():
    """副本线报告：版本/来源市场/sha、两条 ZCode 命令、一条 Claude 命令、未安装。"""
    with tempfile.TemporaryDirectory() as tmp:
        root, (zc_inst, zc_known, cc_inst, cc_known) = make_copy_fixtures(tmp)
        rows = collect_copy_line(["mattpocock-skills", "obsidian-skills"], root,
                                 zcode_installed_path=zc_inst,
                                 zcode_known_path=zc_known,
                                 claude_installed_path=cc_inst,
                                 claude_known_path=cc_known)
        text = "\n".join(build_copy_report(rows))
        assert "其他市场插件副本" in text
        assert "1.2.3" in text and "3cca18b3ffff" in text
        assert "claude-plugins-official" in text
        assert "zcode plugins marketplace update claude-plugins-official" in text
        assert "zcode plugins plugin update mattpocock-skills@claude-plugins-official" in text
        assert "claude plugin update mattpocock-skills@claude-plugins-official" in text
        assert "未安装" in text, "未装的 agent 要报未安装"
        assert "本仓库市场" in text, "本市场来源的副本要标明无需处理"


def test_decide_exit_code_with_hub():
    """退出码纳入枢纽线：全同步才 0；不一致/缺失/枢纽线失败任一 -> 1；副本线不影响。"""
    pin_ok = [mk_result("up-to-date")]
    assert decide_exit_code(pin_ok, [hub_result()]) == 0
    assert decide_exit_code(pin_ok, [hub_result(member_statuses=("hub-drifted",))]) == 1
    assert decide_exit_code(pin_ok, [hub_result(member_statuses=("hub-missing",))]) == 1
    assert decide_exit_code(pin_ok, [hub_result(status="hub-error")]) == 1
    assert decide_exit_code([mk_result("update-available")], [hub_result()]) == 1


# ---------------------------------------------------------------- 枢纽线夹具

def write_text(path, text):
    """小工具：按 UTF-8 + LF 落一个文本文件（目录不存在则建）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def make_upstream_tree(tree_root):
    """搭一棵 pin 处上游树：三分类成员 + deprecated/in-progress 干扰 + 散文件。

    返回族成员期望值（name -> category）。
    """
    expected = {}
    for cat, names in (("engineering", ["tdd", "code-review"]),
                       ("productivity", ["grilling"]),
                       ("misc", ["wizard"])):
        for n in names:
            write_text(os.path.join(tree_root, "skills", cat, n, "SKILL.md"),
                       f"---\nname: {n}\n---\nbody of {n}\n")
            expected[n] = cat
    # 永不装入的分类：deprecated / in-progress 各放一个成员
    for cat in ("deprecated", "in-progress"):
        write_text(os.path.join(tree_root, "skills", cat, "old-skill", "SKILL.md"),
                   "old\n")
    # 散文件与子目录内容：不影响族清单，但参与内容比对
    write_text(os.path.join(tree_root, "skills", "README.md"), "readme\n")
    write_text(os.path.join(tree_root, "skills", "engineering", "NOTICE.txt"), "notice\n")
    write_text(os.path.join(tree_root, "skills", "engineering", "tdd",
                            "references", "tests.md"), "tests md\n")
    return expected


def make_pin_tarball(tmp, top_name="skills-49dd158d"):
    """把上游树打成 codeload 形态的 tar.gz（单顶层目录），返回 (tar_path, tree_root)。"""
    tree_root = os.path.join(tmp, top_name)
    make_upstream_tree(tree_root)
    tar_path = os.path.join(tmp, "pin.tar.gz")
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(tree_root, arcname=top_name)
    return tar_path, tree_root


def make_hub_from_tree(tmp, tree_root, omit=()):
    """按上游树把枢纽实体原样拷出来（全部已同步的枢纽），返回枢纽目录。"""
    hub = os.path.join(tmp, "hub")
    fam = derive_family_members(tree_root)
    for name, cat in fam.items():
        if name in omit:
            continue
        shutil.copytree(os.path.join(tree_root, "skills", cat, name),
                        os.path.join(hub, name))
    return hub


def make_pinned_entries():
    """一条带 pin 一条无 pin，与真实市场同构。"""
    return [
        {"name": "mattpocock-skills", "repo": "mattpocock/skills",
         "pinned_ref": "main", "pinned_sha": "49dd158d1076"},
        {"name": "obsidian-skills", "repo": "kepano/obsidian-skills",
         "pinned_ref": None, "pinned_sha": None},
    ]


# ---------------------------------------------------------------- 副本线夹具

def make_copy_fixtures(tmp):
    """tmp 假安装记录：ZCode 列表格式 / Claude Code 字典格式，形态对齐真实文件。

    ZCode：mattpocock 来自 claude-plugins-official（外部副本，v1.2.3 @ 3cca18b3）、
    obsidian 装自本仓库市场（不算外部副本）；
    Claude Code：obsidian 装自本仓库市场、mattpocock 来自官方市场（外部副本）。
    返回 (market_root, 四个 json 路径)。
    """
    root = os.path.join(tmp, "market")
    os.makedirs(root)
    zc_inst = os.path.join(tmp, "zcode_installed.json")
    with open(zc_inst, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "plugins": [
            {"id": "mattpocock-skills@claude-plugins-official",
             "name": "mattpocock-skills", "marketplace": "claude-plugins-official",
             "version": "1.2.3",
             "source": {"source": "url",
                        "url": "https://github.com/mattpocock/skills.git",
                        "sha": "3cca18b3ffff"}},
            {"id": "obsidian-skills@my-claude-market",
             "name": "obsidian-skills", "marketplace": "my-claude-market",
             "version": "1.0.1", "source": {"source": "directory"}},
            {"id": "video-agent-kit@zcode-plugins-official",
             "name": "video-agent-kit", "marketplace": "zcode-plugins-official",
             "version": "0.4.3", "source": {"source": "url"}},
        ]}, f)
    zc_known = os.path.join(tmp, "zcode_known.json")
    with open(zc_known, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "marketplaces": [
            # 故意用正斜杠路径：验证路径归一化（normcase/realpath）后仍能识别本仓库市场
            {"id": "my-claude-market",
             "source": {"source": "directory", "path": root.replace("\\", "/")}},
            {"id": "claude-plugins-official",
             "source": {"source": "github",
                        "repo": "anthropics/claude-plugins-official"}},
        ]}, f)
    cc_inst = os.path.join(tmp, "claude_installed.json")
    with open(cc_inst, "w", encoding="utf-8") as f:
        json.dump({"version": 2, "plugins": {
            "mattpocock-skills@claude-plugins-official": [
                {"scope": "user", "version": "1.2.3",
                 "installPath": os.path.join(tmp, "cache", "m")}],
            "obsidian-skills@my-claude-market": [
                {"scope": "user", "version": "1.0.1",
                 "gitCommitSha": "01591573"}],
        }}, f)
    cc_known = os.path.join(tmp, "claude_known.json")
    with open(cc_known, "w", encoding="utf-8") as f:
        json.dump({
            "claude-plugins-official": {"source": {"source": "github",
                                                   "repo": "anthropics/claude-plugins-official"}},
            "my-claude-market": {"source": {"source": "directory", "path": root},
                                 "installLocation": root},
        }, f)
    return root, (zc_inst, zc_known, cc_inst, cc_known)


def hub_result(status="hub-ok", member_statuses=("hub-in-sync",)):
    """手搓一条枢纽线结果，供报告 / 退出码用例使用。"""
    return {"name": "mattpocock-skills", "repo": "mattpocock/skills",
            "pinned_sha": "49dd158d1076", "status": status,
            "members": [{"name": f"skill-{i}", "category": "engineering",
                         "status": st}
                        for i, st in enumerate(member_statuses)],
            "error": "tarball 下载失败（HTTP 502）: https://codeload.example"
                     if status == "hub-error" else None}


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
    test_derive_family_members,
    test_derive_family_members_missing_skills_dir,
    test_judge_hub_members_three_states,
    test_judge_hub_members_missing_hub_dir,
    test_judge_hub_members_ignores_crlf,
    test_run_hub_check_skips_no_pin_and_judges,
    test_run_hub_check_reports_drift_and_missing,
    test_run_hub_check_download_failure_isolated,
    test_download_to_file_offline,
    test_collect_copy_line_from_tmp_files,
    test_collect_copy_line_missing_files,
    test_build_hub_report,
    test_build_copy_report,
    test_decide_exit_code_with_hub,
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
