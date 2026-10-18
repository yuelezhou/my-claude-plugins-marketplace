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

覆盖（票 03 update 仓库写半链）：
校验门判定（0 error 放行、「缺 .minimax-plugin」对外部引用式条目特判 N/A、
其余 error 阻断、无「结果:」行的不可识别输出保守拦截）、
git ls-remote --symref 输出解析（默认分支）、
marketplace pin bump（pinnedSha/pinnedAt 双字段、note 仅同步内嵌旧 SHA/日期的文字、
原 dict 不被修改、已同步值重跑零改动、无 pin 条目建基线写齐三字段且键序固定）、
compat 表格 pin 列同步（精准行替换、其余行列不动、已同步零改动、无该行跳过）、
plan_updates 编排（bump/建基线/跳过三分、单条目校验失败不中断其余条目、
head 查询失败进失败通道、无 pin 条目才查默认分支、下载用新 head SHA、
校验门前树根目录名规范成 plugin.json 的 name——codeload 顶层 <repo>-<sha>
会让 validator 的 name/目录名检查出假阻断）、
apply_updates（tmp 假仓库双文件产物正确且保持 CRLF/缩进、dry-run 零写入、
重复 apply 字节级零改动）、cmd_update（非交互无 --yes 拒绝、校验门失败全链中止
零写入、--entry 单条目、--dry-run、成功后重跑已最新零改动）。

覆盖（票 04 update 下半链：枢纽族实体三方同步）：
classify_family_sync 五动作（干净落后覆盖 / 已同步不动 / 不一致保留 /
新增装入 / 已移除删除；建基线无旧树时不覆盖不删；旧成员枢纽缺失补装入；
CRLF 行尾差异复用 compare_tree 归一不误判）、
diff_tree_summary（仅枢纽有/仅基线有/内容不同，CRLF 不算差异）、
实体操作（overwrite_entity 删旧拷新、junction 拒覆盖不写穿；
remove_path_safe 删 junction 只摘链接目标完好）、
sync_hub_families 编排（--yes 策略：干净落后自动覆盖/不一致保留/新增自动装入/
已移除缺 --delete-removed 保留标注；--adopt 覆盖不一致；交互注入决策序列——
不一致逐个问拿到 diff、装入批量确认可拒、已移除逐个确认即删；
链接层仅结构变化时调用、失败不回滚不抛异常；junction 项报错不中断其余；
同状态重跑零动作；dry-run 只计划零写入）、
交互 prompt 应答序列（d 看 diff 重问、非法答重问、批量 y/n、逐个删）、
plan_updates 扩展（旧 pin 树先于新树下载、keep_trees 携带 work/old_tree/new_tree、
缺省用完即清、旧 tarball 拉取失败进失败通道）、
cmd_update 全链（tmp 假枢纽四类场景端到端、重跑全 skip 零枢纽动作不调链接层、
枢纽错误项退出码 1 但仓库写入不回滚、dry-run 枢纽只出计划、
报告三段收尾）、build_hub_sync_report 措辞（四类清单+保留原因、错误项、
链接层失败给手动补救命令、dry-run 标注）。

用法:
    python test_plugin_updater.py

退出码:
    0  全部通过
    1  有用例失败
"""

import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plugin_updater import (
    apply_pin_bump,
    apply_updates,
    build_copy_report,
    build_hub_report,
    build_hub_sync_report,
    build_report,
    build_update_report,
    classify_family_sync,
    cmd_update,
    collect_copy_line,
    decide_exit_code,
    derive_family_members,
    diff_tree_summary,
    download_to_file,
    HubSyncError,
    is_link_path,
    judge_entry,
    judge_hub_members,
    judge_validator_output,
    KEEP_MISMATCH,
    KEEP_NO_FLAG,
    KEEP_USER,
    normalize_tree_root,
    overwrite_entity,
    parse_external_entries,
    parse_ls_remote_output,
    parse_symref_output,
    parse_upstream_plugin_json,
    plan_updates,
    prompt_batch_install,
    prompt_mismatch,
    prompt_removals,
    render_pin_cell,
    remove_path_safe,
    run_check,
    run_hub_check,
    sync_compat_table,
    sync_hub_families,
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


# ---------------------------------------------------------------- update 校验门判定（票 03）

GATE_PASS_OUTPUT = ("== /tmp/tree\n"
                    "  全部检查通过\n"
                    "\n"
                    "结果: 0 error, 2 warning — 通过（warning 请逐条人工确认后发布）\n")
GATE_NA_OUTPUT = ("== /tmp/tree\n"
                  "  ERROR   缺少 .minimax-plugin/plugin.json（MiniMax Plugin V1 入口清单）\n"
                  "  ERROR   skills/x/SKILL.md frontmatter 缺少 name\n"
                  "结果: 2 error, 1 warning — 未通过，修完 error 才能发布\n")


def test_judge_validator_output():
    """0 error 放行；「缺 .minimax-plugin」对外部条目 N/A、其余 error 阻断；
    无「结果:」行的不可识别输出保守拦截（0 error 也必须有证据）。"""
    verdict = judge_validator_output(GATE_PASS_OUTPUT, external_ref=True)
    assert verdict["passed"] and verdict["blocking"] == [] and verdict["waived"] == []

    verdict = judge_validator_output(GATE_NA_OUTPUT, external_ref=True)
    assert not verdict["passed"]
    assert len(verdict["waived"]) == 1 and "缺少 .minimax-plugin" in verdict["waived"][0], \
        "外部引用式条目的「缺 .minimax-plugin」error 特判 N/A（2026-10-18 手动重 pin 先例）"
    assert len(verdict["blocking"]) == 1 and "缺少 name" in verdict["blocking"][0], \
        "其余 error 照常阻断"

    verdict = judge_validator_output(GATE_NA_OUTPUT, external_ref=False)
    assert len(verdict["blocking"]) == 2 and verdict["waived"] == [], \
        "非外部引用式条目不豁免任何 error"

    verdict = judge_validator_output("Traceback (most recent call last): ...", external_ref=True)
    assert not verdict["passed"] and not verdict["recognized"], \
        "无「结果:」行 = validator 输出不可识别，保守按未通过处理"


# ---------------------------------------------------------------- update 默认分支解析（票 03）

def test_parse_symref_output():
    """`git ls-remote --symref` 首行 ref: refs/heads/<名> 取默认分支短名。"""
    out = ("ref: refs/heads/main\tHEAD\n"
           "0f9e8d7c6b5a4444444444444444444444444444\tHEAD\n")
    assert parse_symref_output(out) == "main"
    assert parse_symref_output("ref: refs/heads/master\tHEAD\n") == "master"
    try:
        parse_symref_output("abc\tHEAD\n")
        raise AssertionError("没有 ref: 行应报错而不是静默返回")
    except ValueError:
        pass


# ---------------------------------------------------------------- pin bump 纯决策（票 03）

def alpha_entry():
    """与真实市场同构的带 pin 条目（note 内嵌旧短 SHA + 旧日期）。"""
    return {"name": "alpha-skills", "description": "外部聚合带 pin",
            "source": {"source": "github", "repo": "alpha/one"},
            "metadata": {"pinnedRef": "main", "pinnedSha": OLD_SHA,
                         "pinnedAt": OLD_DATE,
                         "note": f"外部聚合插件（引用式 + pin SHA）；"
                                 f"旧基线 {OLD_SHA[:7]}（{OLD_DATE}）重 pin，校验 0 error"}}


def test_apply_pin_bump_syncs_note_and_idempotent():
    """bump 双字段 + note 只同步内嵌旧 SHA/日期的文字；原 dict 不动；重跑零改动。"""
    mp = {"plugins": [alpha_entry(),
                      {"name": "gamma-skills", "source": {"source": "github", "repo": "g/h"},
                       "metadata": {"pinnedRef": "main", "pinnedSha": OLD_SHA,
                                    "pinnedAt": OLD_DATE,
                                    "note": f"全串 pin {OLD_SHA}，人工核对过"}}]}
    new_mp, changed = apply_pin_bump(mp, "alpha-skills", NEW_SHA, NEW_DATE)
    assert changed
    meta = new_mp["plugins"][0]["metadata"]
    assert meta["pinnedSha"] == NEW_SHA and meta["pinnedAt"] == NEW_DATE
    assert meta["pinnedRef"] == "main"
    assert meta["note"] == (f"外部聚合插件（引用式 + pin SHA）；"
                            f"旧基线 {NEW_SHA[:7]}（{NEW_DATE}）重 pin，校验 0 error"), \
        "note 里内嵌的旧短 SHA 与旧日期被替换，其余文字原样保留"
    assert mp["plugins"][0]["metadata"]["pinnedSha"] == OLD_SHA, "原 marketplace dict 不被修改"

    new_mp2, changed2 = apply_pin_bump(new_mp, "alpha-skills", NEW_SHA, NEW_DATE)
    assert not changed2, "对已同步条目重跑（旧值==新值）零改动"

    # 内嵌全串 SHA 的 note 同步为全串新 SHA
    new_mp3, _ = apply_pin_bump(mp, "gamma-skills", NEW_SHA, NEW_DATE)
    assert new_mp3["plugins"][1]["metadata"]["note"] == f"全串 pin {NEW_SHA}，人工核对过"


def test_apply_pin_bump_baseline_creates_metadata():
    """无 pin 条目建基线：新建 metadata 写齐 pinnedRef/pinnedSha/pinnedAt（键序固定）。"""
    mp = {"plugins": [{"name": "beta-skills", "description": "外部聚合无 pin",
                       "source": {"source": "github", "repo": "beta/two"}}]}
    new_mp, changed = apply_pin_bump(mp, "beta-skills", BASE_SHA, NEW_DATE, new_ref="main")
    assert changed
    meta = new_mp["plugins"][0]["metadata"]
    assert meta == {"pinnedRef": "main", "pinnedSha": BASE_SHA, "pinnedAt": NEW_DATE}
    assert list(meta.keys()) == ["pinnedRef", "pinnedSha", "pinnedAt"], \
        "基线三字段按 pinnedRef/pinnedSha/pinnedAt 的顺序写（对齐现有条目排版）"


# ---------------------------------------------------------------- compat 表格同步（票 03）

def test_render_pin_cell():
    """pin 列格式 `main `<短sha>`（日期，v版本）`；版本号未知时省略版本段。"""
    assert render_pin_cell("main", NEW_SHA, NEW_DATE, "2.0.0") == \
        f"main `{NEW_SHA[:7]}`（{NEW_DATE}，v2.0.0）"
    assert render_pin_cell("main", NEW_SHA, NEW_DATE, None) == \
        f"main `{NEW_SHA[:7]}`（{NEW_DATE}）"


def make_compat_text():
    """与真实 docs/plugin-compatibility.md「外部聚合插件」节同构的最小表格。"""
    return ("# 兼容性\n\n## 外部聚合插件（引用式 + pin SHA）\n\n"
            "| 插件 | 上游 | pin | 三平台 |\n"
            "|---|---|---|---|\n"
            f"| alpha-skills | [alpha/one](https://github.com/alpha/one) "
            f"| main `{OLD_SHA[:7]}`（{OLD_DATE}，v1.0.0） | ✅✅✅ 纯 skills |\n"
            "| beta-skills | [beta/two](https://github.com/beta/two) | 无 pin "
            "| ✅✅✅ 纯 skills |\n\n"
            "入库流程：clone → 校验 → 本表标注 → marketplace.json 加条目。\n")


def test_sync_compat_table():
    """只替换该条目行的 pin 列（第 3 列）；上游列/三平台列/其余行不动；幂等。"""
    text = make_compat_text()
    cell = f"main `{NEW_SHA[:7]}`（{NEW_DATE}，v2.0.0）"
    new_text, changed = sync_compat_table(text, "alpha-skills", cell)
    assert changed
    assert f"| alpha-skills | [alpha/one](https://github.com/alpha/one) | {cell} " \
           "| ✅✅✅ 纯 skills |" in new_text, "pin 列换新，同行其余列原样"
    assert "无 pin" in new_text, "其余条目的行不动"
    assert "入库流程" in new_text, "表格外的正文不动"

    again, changed2 = sync_compat_table(new_text, "alpha-skills", cell)
    assert not changed2 and again == new_text, "已同步的行重跑零改动"

    _, changed3 = sync_compat_table(text, "gamma-skills", cell)
    assert not changed3, "表里没有该条目行 -> 不改动（由调用方注明跳过）"


# ---------------------------------------------------------------- update 编排（票 03）

OLD_SHA = "a1b2c3d4e5f6000000000000000000000000000"
NEW_SHA = "f6e5d4c3b2a1999999999999999999999999999"
BASE_SHA = "0f9e8d7c6b5a4444444444444444444444444444"
OLD_DATE = "2026-01-02"
NEW_DATE = "2026-10-19"


def make_update_entries():
    """一 bump 一建基线，与真实市场外部条目同构。"""
    return [
        {"name": "alpha-skills", "repo": "alpha/one", "pinned_ref": "main",
         "pinned_sha": OLD_SHA},
        {"name": "beta-skills", "repo": "beta/two", "pinned_ref": None,
         "pinned_sha": None},
    ]


def make_update_seams(tar_path, validator_output=GATE_PASS_OUTPUT, head_map=None):
    """update 全套假接缝：head/版本号/默认分支/tarball/validator 全注入，调用可观测。

    返回 (calls, seams_dict)：seams_dict 的键与 plan_updates / cmd_update 的
    注入参数同名，可直接 ** 解包。
    """
    calls = {"tar": [], "validator": [], "symref": []}
    heads = head_map or {"alpha/one": NEW_SHA, "beta/two": BASE_SHA}

    def fetch_head(repo, ref):
        return heads[repo]

    def fetch_version(repo, sha):
        return "2.0.0" if repo == "alpha/one" else "0.9.0"

    def fetch_default_ref(repo):
        calls["symref"].append(repo)
        return "main"

    def get_tarball(repo, sha, dest_dir, timeout=120):
        calls["tar"].append((repo, sha))
        return tar_path

    def validator(tree):
        calls["validator"].append(tree)
        assert os.path.isdir(tree), "校验门拿到的应是解包后真实存在的树"
        return validator_output

    return calls, {"fetch_head": fetch_head, "fetch_version": fetch_version,
                   "fetch_default_ref": fetch_default_ref,
                   "get_tarball": get_tarball, "validator": validator}


def test_plan_updates_bump_and_baseline():
    """bump/建基线两类计划齐备：下载用新 head SHA、只有无 pin 条目查默认分支、全过校验门。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        calls, seams = make_update_seams(tar_path)
        plans, failures = plan_updates(make_update_entries(), today=NEW_DATE, **seams)
        assert failures == []
        by = {p["name"]: p for p in plans}
        assert by["alpha-skills"]["action"] == "bump"
        assert by["alpha-skills"]["new_sha"] == NEW_SHA
        assert by["alpha-skills"]["old_sha"] == OLD_SHA
        assert by["alpha-skills"]["version"] == "2.0.0"
        assert by["beta-skills"]["action"] == "baseline"
        assert by["beta-skills"]["new_sha"] == BASE_SHA
        assert by["beta-skills"]["new_ref"] == "main", "建基线要带默认分支"
        assert by["beta-skills"]["date"] == NEW_DATE
        assert calls["tar"] == [("alpha/one", OLD_SHA), ("alpha/one", NEW_SHA),
                                ("beta/two", BASE_SHA)], \
            "tarball 按新 head SHA 下载，且 bump 条目的旧 pin 树先落地（票 04：三方分类要在 bump 前拿到旧基线）"
        assert calls["symref"] == ["beta/two"], "只有无 pin 条目才查默认分支"
        assert len(calls["validator"]) == 2, "两条目都过同一校验门"


def test_plan_updates_gate_failure_isolated():
    """校验门未通过 -> 该条目进失败通道（N/A 项不算阻断），其余条目照常出计划。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        _calls, seams = make_update_seams(tar_path)
        gate_calls = {"n": 0}

        def fail_first_gate(tree):
            gate_calls["n"] += 1
            # alpha（第一个进门的）校验不过，beta 照常通过——混合结果
            return GATE_NA_OUTPUT if gate_calls["n"] == 1 else GATE_PASS_OUTPUT

        seams["validator"] = fail_first_gate
        plans, failures = plan_updates(make_update_entries(), today=NEW_DATE, **seams)
        assert [p["name"] for p in plans] == ["beta-skills"], \
            "单条目校验失败不中断其余条目的计划"
        assert len(failures) == 1 and failures[0]["stage"] == "gate"
        assert failures[0]["name"] == "alpha-skills"
        blocking = failures[0]["detail"]
        assert any("缺少 name" in e for e in blocking), "真实 error 进阻断清单"
        assert not any("缺少 .minimax-plugin" in e for e in blocking), \
            "「缺 .minimax-plugin」N/A 不进阻断清单"


def test_plan_updates_skips_up_to_date():
    """pin==head 的条目出 skip 计划：不下载 tarball、不过校验门（幂等重跑的基础）。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        calls, seams = make_update_seams(
            tar_path, head_map={"alpha/one": OLD_SHA, "beta/two": BASE_SHA})
        plans, failures = plan_updates(make_update_entries(), today=NEW_DATE, **seams)
        assert failures == []
        by = {p["name"]: p["action"] for p in plans}
        assert by["alpha-skills"] == "skip"
        assert by["beta-skills"] == "baseline"
        assert calls["tar"] == [("beta/two", BASE_SHA)], "已最新条目不下载"
        assert len(calls["validator"]) == 1, "已最新条目不过校验门"


def test_plan_updates_head_failure_isolated():
    """单条目 head 查询失败 -> 失败通道（stage=head），其余条目照常计划。"""
    with tempfile.TemporaryDirectory() as tmp:
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        calls, seams = make_update_seams(tar_path)

        def flaky_head(repo, ref):
            if repo == "alpha/one":
                raise RuntimeError("网络断了")
            return BASE_SHA

        seams["fetch_head"] = flaky_head
        plans, failures = plan_updates(make_update_entries(), today=NEW_DATE, **seams)
        assert [p["name"] for p in plans] == ["beta-skills"]
        assert len(failures) == 1 and failures[0]["stage"] == "head"
        assert failures[0]["name"] == "alpha-skills" and "网络断了" in failures[0]["error"]
        assert calls["tar"] == [("beta/two", BASE_SHA)], "失败条目不进入下载"


def test_normalize_tree_root_renames_to_plugin_name():
    """codeload 顶层目录是 <repo>-<sha>，校验门前把树根改名为 plugin.json 的
    name（对齐手动重 pin 先例里 git clone 的目录名），否则出假阻断 error。"""
    with tempfile.TemporaryDirectory() as tmp:
        top = os.path.join(tmp, "obsidian-skills-3ccff5338ea7")
        write_text(os.path.join(top, ".claude-plugin", "plugin.json"),
                   '{"name": "obsidian", "version": "1.0.1"}')
        write_text(os.path.join(top, "SKILL.md"), "---\nname: x\n---\nbody\n")
        renamed = normalize_tree_root(top)
        assert os.path.basename(renamed) == "obsidian"
        assert os.path.isdir(renamed) and not os.path.exists(top), "原目录已改名"
        assert os.path.isfile(os.path.join(renamed, ".claude-plugin", "plugin.json"))

        # 已对齐 / plugin.json 缺失 / 损坏 -> 原样返回（让校验门报真正的 error）
        assert normalize_tree_root(renamed) == renamed
        bare = os.path.join(tmp, "skills-49dd158d1076")
        os.makedirs(bare)
        assert normalize_tree_root(bare) == bare
        broken = os.path.join(tmp, "skills-broken")
        os.makedirs(broken)
        write_text(os.path.join(broken, ".claude-plugin", "plugin.json"), "<html>")
        assert normalize_tree_root(broken) == broken


def test_plan_updates_gate_receives_normalized_tree():
    """校验门拿到的树根目录名 == plugin.json 的 name（端到端走 tarball 解包链）。"""
    with tempfile.TemporaryDirectory() as tmp:
        # 仿 codeload 形态：顶层 <repo>-<sha>，内含 plugin.json(name=one) + skills/
        top = os.path.join(tmp, "one-abcdef1234")
        write_text(os.path.join(top, ".claude-plugin", "plugin.json"),
                   '{"name": "one", "version": "2.0.0"}')
        write_text(os.path.join(top, "skills", "engineering", "tdd", "SKILL.md"),
                   "---\nname: tdd\n---\nbody\n")
        tar_path = os.path.join(tmp, "new.tar.gz")
        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(top, arcname="one-abcdef1234")
        captured = []

        def validator(tree):
            captured.append(tree)
            return GATE_PASS_OUTPUT

        entries = [{"name": "alpha-skills", "repo": "alpha/one",
                    "pinned_ref": "main", "pinned_sha": OLD_SHA}]
        plans, failures = plan_updates(
            entries, fetch_head=lambda repo, ref: NEW_SHA,
            fetch_version=lambda repo, sha: "2.0.0",
            get_tarball=lambda repo, sha, dest_dir, timeout=120: tar_path,
            validator=validator, today=NEW_DATE)
        assert failures == [] and plans[0]["action"] == "bump"
        assert os.path.basename(captured[0]) == "one", \
            "校验门收到的是改名后的树根（name 与目录名一致，不出假阻断）"


# ---------------------------------------------------------------- update 计划扩展（票 04）

def make_plan_seams(tar_by_sha, validator_output=GATE_PASS_OUTPUT):
    """票 04 计划用假接缝：按 SHA 返回对应 tarball，调用可观测。"""
    calls = {"tar": [], "validator": []}

    def fetch_head(repo, ref):
        return {"alpha/one": NEW_SHA, "beta/two": BASE_SHA}[repo]

    def get_tarball(repo, sha, dest_dir, timeout=120):
        calls["tar"].append((repo, sha))
        return tar_by_sha[sha]

    def validator(tree):
        calls["validator"].append(tree)
        return validator_output

    return calls, {"fetch_head": fetch_head,
                   "fetch_version": lambda repo, sha: "2.0.0",
                   "fetch_default_ref": lambda repo: "main",
                   "get_tarball": get_tarball, "validator": validator}


def test_plan_updates_keep_trees_carries_old_and_new():
    """keep_trees=True：bump 计划携带 work/old_tree/new_tree 供下半链用；
    建基线条目没有旧树（old_tree=None）；两棵树都真实可派生族成员。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tar, _ = make_pin_tarball(tmp, top_name="tree-old-src",
                                      tar_name="old.tar.gz")
        new_tar, _ = make_pin_tarball(tmp, top_name="tree-new-src",
                                      tar_name="new.tar.gz")
        calls, seams = make_plan_seams({OLD_SHA: old_tar, NEW_SHA: new_tar,
                                        BASE_SHA: new_tar})
        work_root = os.path.join(tmp, "work")
        plans, failures = plan_updates(make_update_entries(), today=NEW_DATE,
                                       work_root=work_root, keep_trees=True,
                                       **seams)
        assert failures == []
        assert calls["tar"] == [("alpha/one", OLD_SHA), ("alpha/one", NEW_SHA),
                                ("beta/two", BASE_SHA)], \
            "旧 pin 树在 bump 前下载解包（bump 完就找不到旧基线了）"
        by = {p["name"]: p for p in plans}
        alpha = by["alpha-skills"]
        assert os.path.isdir(alpha["work"]) and os.path.isdir(alpha["old_tree"]) \
            and os.path.isdir(alpha["new_tree"]), "计划携带存活的树路径"
        assert derive_family_members(alpha["old_tree"]), "旧树可派生族成员"
        assert os.path.basename(alpha["new_tree"]) != os.path.basename(old_tar), \
            "新树经 normalize_tree_root（目录名=plugin.json name）"
        beta = by["beta-skills"]
        assert beta["old_tree"] is None and os.path.isdir(beta["new_tree"]), \
            "建基线只有新树"
        # 清理责任在调用方（cmd_update 收尾）：这里手工清，证明目录真实存在过
        shutil.rmtree(work_root, ignore_errors=True)


def test_plan_updates_default_no_keep_cleans_up():
    """keep_trees 缺省 False：票 03 语义不变——计划不带树路径、临时目录用完即清。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tar, _ = make_pin_tarball(tmp, top_name="tree-old-src",
                                      tar_name="old.tar.gz")
        new_tar, _ = make_pin_tarball(tmp, top_name="tree-new-src",
                                      tar_name="new.tar.gz")
        _calls, seams = make_plan_seams({OLD_SHA: old_tar, NEW_SHA: new_tar,
                                         BASE_SHA: new_tar})
        work_root = os.path.join(tmp, "work")
        plans, failures = plan_updates(make_update_entries(), today=NEW_DATE,
                                       work_root=work_root, **seams)
        assert failures == []
        assert all(p.get("old_tree") is None and p.get("new_tree") is None
                   for p in plans), "纯计划不携带树路径"
        assert os.listdir(work_root) == [], "临时工作目录用完即清"


def test_plan_updates_old_tarball_failure_isolated():
    """旧 pin tarball 拉取失败 -> stage=tarball 进失败通道，不出计划不写盘。"""
    with tempfile.TemporaryDirectory() as tmp:
        new_tar, _ = make_pin_tarball(tmp, top_name="tree-new-src",
                                      tar_name="new.tar.gz")

        def get_tarball(repo, sha, dest_dir, timeout=120):
            if sha == OLD_SHA:
                raise RuntimeError("旧 tarball 拉不动（网络抖动）")
            return new_tar

        plans, failures = plan_updates(
            make_update_entries()[:1], today=NEW_DATE,
            fetch_head=lambda repo, ref: NEW_SHA,
            fetch_version=lambda repo, sha: "2.0.0",
            get_tarball=get_tarball,
            validator=lambda tree: GATE_PASS_OUTPUT)
        assert plans == []
        assert len(failures) == 1 and failures[0]["stage"] == "tarball"
        assert "旧 tarball" in failures[0]["error"], "失败原因可读（定位是旧基线这步）"


# ---------------------------------------------------------------- update 写盘（票 03）

def make_bump_plans():
    """手搓两条计划（bump + 建基线），供 apply_updates 的产物用例复用。"""
    return [
        {"action": "bump", "name": "alpha-skills", "repo": "alpha/one", "ref": "main",
         "old_sha": OLD_SHA, "new_sha": NEW_SHA, "new_ref": None, "date": NEW_DATE,
         "version": "2.0.0", "waived": []},
        {"action": "baseline", "name": "beta-skills", "repo": "beta/two", "ref": "HEAD",
         "old_sha": None, "new_sha": BASE_SHA, "new_ref": "main", "date": NEW_DATE,
         "version": "0.9.0", "waived": []},
    ]


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def fake_repo_paths(root):
    return (os.path.join(root, ".claude-plugin", "marketplace.json"),
            os.path.join(root, "docs", "plugin-compatibility.md"))


def test_apply_updates_writes_both_files():
    """tmp 假仓库：双文件产物正确——双字段 bump + note 同步、基线三字段、
    compat 两行 pin 列同步；CRLF/LF 与 2 空格缩进保持；本地条目不受影响。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        mp_path, compat_path = fake_repo_paths(root)
        res = apply_updates(root, make_bump_plans())
        assert res["marketplace"]["written"] and res["compat"]["written"]

        mp_bytes = read_bytes(mp_path)
        assert b"\r\n" in mp_bytes and not mp_bytes.startswith(b"\xef\xbb\xbf"), \
            "marketplace.json 的 CRLF 行尾保持、不引入 BOM"
        assert mp_bytes.endswith(b"\r\n"), "文件末尾换行保持"
        assert b"\r\n  \"plugins\"" in mp_bytes, "2 空格缩进排版保持"
        data = json.loads(mp_bytes.decode("utf-8"))
        alpha = next(p for p in data["plugins"] if p["name"] == "alpha-skills")
        assert alpha["metadata"]["pinnedSha"] == NEW_SHA
        assert alpha["metadata"]["pinnedAt"] == NEW_DATE
        assert alpha["metadata"]["note"] == (f"外部聚合插件（引用式 + pin SHA）；"
                                             f"旧基线 {NEW_SHA[:7]}（{NEW_DATE}）重 pin，"
                                             f"校验 0 error")
        beta = next(p for p in data["plugins"] if p["name"] == "beta-skills")
        assert list(beta["metadata"].keys()) == ["pinnedRef", "pinnedSha", "pinnedAt"]
        assert beta["metadata"]["pinnedSha"] == BASE_SHA
        local = next(p for p in data["plugins"] if p["name"] == "local-plugin")
        assert "metadata" not in local, "本地条目不受影响"

        compat_text = read_bytes(compat_path).decode("utf-8")
        assert b"\r\n" not in read_bytes(compat_path), "compat 文档 LF 行尾保持"
        assert f"main `{NEW_SHA[:7]}`（{NEW_DATE}，v2.0.0）" in compat_text
        assert f"main `{BASE_SHA[:7]}`（{NEW_DATE}，v0.9.0）" in compat_text, \
            "建基线条目的 pin 列同步"
        assert "无 pin" not in compat_text.split("## 外部聚合插件")[1].split("\n\n")[1], \
            "表格里不再有未治理条目"


def test_apply_updates_dry_run_zero_write():
    """--dry-run 语义：算出将发生的变更但不落一个字节。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        mp_path, compat_path = fake_repo_paths(root)
        before = (read_bytes(mp_path), read_bytes(compat_path))
        res = apply_updates(root, make_bump_plans(), dry_run=True)
        assert res["marketplace"]["changed"] and not res["marketplace"]["written"]
        assert res["compat"]["changed"] and not res["compat"]["written"]
        assert (read_bytes(mp_path), read_bytes(compat_path)) == before, "零写入"


def test_apply_updates_idempotent_byte_level():
    """同一批计划重复 apply：第二遍算不出变更、不写盘、字节不变。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        mp_path, compat_path = fake_repo_paths(root)
        apply_updates(root, make_bump_plans())
        snapshot = (read_bytes(mp_path), read_bytes(compat_path))
        res2 = apply_updates(root, make_bump_plans())
        assert not res2["marketplace"]["changed"] and not res2["marketplace"]["written"]
        assert not res2["compat"]["changed"] and not res2["compat"]["written"]
        assert (read_bytes(mp_path), read_bytes(compat_path)) == snapshot, "字节级零改动"


# ---------------------------------------------------------------- update 命令层（票 03/04）

def hub_test_seams(tmp):
    """cmd_update 测试防误伤：枢纽/链接层指 tmp 空目录、链接层假件——
    票 04 起 update 全链会碰枢纽，测试绝不许碰真机 ~/.agents/skills。"""
    return {"hub_dir": os.path.join(tmp, "hub"),
            "link_dir": os.path.join(tmp, "cc-skills"),
            "run_link": lambda root: (True, "ok")}


def test_cmd_update_end_to_end_idempotent():
    """假仓库全链：成功 bump 双文件 -> 重跑已最新零下载零写入（命令级幂等）。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        calls, seams = make_update_seams(tar_path)
        rc = cmd_update(root, yes=True, today=NEW_DATE,
                        **hub_test_seams(tmp), **seams)
        assert rc == 0, "成功更新退出码 0"
        mp_path, compat_path = fake_repo_paths(root)
        assert NEW_SHA[:7] in read_bytes(compat_path).decode("utf-8")
        snapshot = (read_bytes(mp_path), read_bytes(compat_path))

        calls["tar"].clear()
        calls["validator"].clear()
        rc2 = cmd_update(root, yes=True, today=NEW_DATE,
                         **hub_test_seams(tmp), **seams)
        assert rc2 == 0, "重跑（已最新）也退出码 0"
        assert calls["tar"] == [] and calls["validator"] == [], \
            "已最新条目不下载、不校验"
        assert (read_bytes(mp_path), read_bytes(compat_path)) == snapshot, \
            "重跑零改动（幂等）"


def test_cmd_update_guard_noninteractive():
    """非交互环境无 --yes -> 退出码 2，拒绝执行任何变更（连网络都不碰）。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        calls, seams = make_update_seams(tar_path)
        mp_path, compat_path = fake_repo_paths(root)
        before = (read_bytes(mp_path), read_bytes(compat_path))
        rc = cmd_update(root, interactive=False, yes=False, today=NEW_DATE, **seams)
        assert rc == 2
        assert calls == {"tar": [], "validator": [], "symref": []}, \
            "守卫在任何外部访问之前触发"
        assert (read_bytes(mp_path), read_bytes(compat_path)) == before, "零写入"


def test_cmd_update_gate_failure_aborts_zero_write():
    """校验门有 error -> 退出码 1、全链中止：beta 即便过了门也不写（全或无）。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        _calls, seams = make_update_seams(tar_path)
        gate_calls = {"n": 0}

        def fail_first_gate(tree):
            gate_calls["n"] += 1
            # alpha（有 pin 的，第一个进门）校验不过；beta 过门
            return GATE_NA_OUTPUT if gate_calls["n"] == 1 else GATE_PASS_OUTPUT

        seams["validator"] = fail_first_gate
        mp_path, compat_path = fake_repo_paths(root)
        before = (read_bytes(mp_path), read_bytes(compat_path))
        rc = cmd_update(root, yes=True, today=NEW_DATE, **seams)
        assert rc == 1
        assert (read_bytes(mp_path), read_bytes(compat_path)) == before, \
            "任一校验失败 -> 全链中止、仓库文件零改动"
        data = json.loads(read_bytes(mp_path).decode("utf-8"))
        beta = next(p for p in data["plugins"] if p["name"] == "beta-skills")
        assert "metadata" not in beta, "其他条目即便过了门也不写（全或无）"


def test_cmd_update_dry_run_zero_write():
    """--dry-run 非交互可跑（不写入就不需要 --yes），退出码 0、零写入。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        calls, seams = make_update_seams(tar_path)
        mp_path, compat_path = fake_repo_paths(root)
        before = (read_bytes(mp_path), read_bytes(compat_path))
        rc = cmd_update(root, dry_run=True, interactive=False, today=NEW_DATE,
                        **hub_test_seams(tmp), **seams)
        assert rc == 0
        assert len(calls["validator"]) == 2, "dry-run 仍走完整校验门（报告才可信）"
        assert (read_bytes(mp_path), read_bytes(compat_path)) == before, "零写入"


def test_cmd_update_entry_filter():
    """--entry 只影响指定条目：alpha bump 落盘，beta 的 marketplace/compat 原样。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        _calls, seams = make_update_seams(tar_path)
        rc = cmd_update(root, entry="alpha-skills", yes=True, today=NEW_DATE,
                        **hub_test_seams(tmp), **seams)
        assert rc == 0
        mp_path, compat_path = fake_repo_paths(root)
        data = json.loads(read_bytes(mp_path).decode("utf-8"))
        alpha = next(p for p in data["plugins"] if p["name"] == "alpha-skills")
        beta = next(p for p in data["plugins"] if p["name"] == "beta-skills")
        assert alpha["metadata"]["pinnedSha"] == NEW_SHA
        assert "metadata" not in beta, "未指定条目不建基线"
        compat_beta = [ln for ln in read_bytes(compat_path).decode("utf-8").splitlines()
                       if ln.startswith("| beta-skills")]
        assert compat_beta == ["| beta-skills | [beta/two](https://github.com/beta/two) "
                               "| 无 pin | ✅✅✅ 纯 skills |"], "未指定条目的表格行原样"


def test_cmd_update_entry_unknown():
    """--entry 给了市场里不存在的名字 -> 退出码 2。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        tar_path, _tree = make_pin_tarball(tmp, top_name="skills-new")
        _calls, seams = make_update_seams(tar_path)
        rc = cmd_update(root, entry="no-such", yes=True, today=NEW_DATE, **seams)
        assert rc == 2


def test_build_update_report():
    """报告措辞：计划/跳过/失败（含阻断明细）/写入与 dry-run 标注。"""
    plans = make_bump_plans() + [
        {"action": "skip", "name": "gamma-skills", "repo": "g/h", "ref": "main",
         "old_sha": NEW_SHA, "new_sha": NEW_SHA, "new_ref": None, "date": None,
         "version": None, "waived": []}]
    text = "\n".join(build_update_report(plans, [], None, market_root="R"))
    assert "bump" in text and "建基线" in text and "已最新" in text
    assert "f6e5d4c" in text and "0f9e8d7" in text, "计划里给新旧短 SHA"

    failures = [{"name": "alpha-skills", "repo": "alpha/one", "stage": "gate",
                 "error": "校验门未通过（1 error）",
                 "detail": ["skills/x/SKILL.md frontmatter 缺少 name"]}]
    text2 = "\n".join(build_update_report(plans, failures, None, market_root="R"))
    assert "全链中止" in text2 and "零写入" in text2
    assert "缺少 name" in text2, "阻断 error 明细进报告"

    applied = {"marketplace": {"changed": True, "written": True},
               "compat": {"changed": True, "written": True, "skipped": []}}
    text3 = "\n".join(build_update_report(plans, [], applied, market_root="R"))
    assert "已写入" in text3
    text4 = "\n".join(build_update_report(plans, [], applied, dry_run=True,
                                          market_root="R"))
    assert "dry-run" in text4 and "未写入" in text4


# ---------------------------------------------------------------- update 全链（票 04）

def make_tar_of_tree(tmp, tree_root, tar_name):
    """把现成目录树打成 codeload 形态 tar.gz（单顶层目录=树根名）。"""
    tar_path = os.path.join(tmp, tar_name)
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(tree_root, arcname=os.path.basename(tree_root))
    return tar_path


def missing_copy_rows(names, root):
    """副本线假件：安装记录全缺 -> 全部未安装（避免测试读真机 home）。"""
    nope = os.path.join(root, "no-such-installed.json")
    return collect_copy_line(names, root, zcode_installed_path=nope,
                             zcode_known_path=nope,
                             claude_installed_path=nope,
                             claude_known_path=nope)


def test_cmd_update_full_chain_hub_sync():
    """update 全链端到端：仓库 bump + 枢纽四方分类落地 + 链接层被调 + 三段报告收尾。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        old_tree, new_tree = make_two_pin_trees(tmp)
        old_tar = make_tar_of_tree(tmp, old_tree, "old.tar.gz")
        new_tar = make_tar_of_tree(tmp, new_tree, "new.tar.gz")
        hub = make_hub_from_tree(tmp, old_tree)
        with open(os.path.join(hub, "grilling", "SKILL.md"), "a",
                  encoding="utf-8") as f:
            f.write("手改\n")
        link_dir = os.path.join(tmp, "cc-skills")
        os.makedirs(link_dir)
        link_calls = []
        tars = {OLD_SHA: old_tar, NEW_SHA: new_tar}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmd_update(
                root, entry="alpha-skills", yes=True, today=NEW_DATE,
                hub_dir=hub, link_dir=link_dir,
                fetch_head=lambda repo, ref: NEW_SHA,
                fetch_version=lambda repo, sha: "2.0.0",
                get_tarball=lambda repo, sha, dest_dir, timeout=120: tars[sha],
                validator=lambda tree: GATE_PASS_OUTPUT,
                run_link=lambda r: link_calls.append(r) or (True, "link-ok"),
                collect_copies=missing_copy_rows)
        assert rc == 0
        out = buf.getvalue()
        # 仓库写半链（票 03 回归）：pin bump 落盘
        data = json.loads(read_bytes(
            os.path.join(root, ".claude-plugin", "marketplace.json")).decode("utf-8"))
        alpha = next(p for p in data["plugins"] if p["name"] == "alpha-skills")
        assert alpha["metadata"]["pinnedSha"] == NEW_SHA
        # 枢纽四方分类落地
        with open(os.path.join(hub, "tdd", "SKILL.md"), "r", encoding="utf-8") as f:
            assert "v2" in f.read(), "干净落后已覆盖"
        assert os.path.isdir(os.path.join(hub, "teach")), "上游新增已装入"
        assert os.path.isfile(os.path.join(hub, "wizard", "SKILL.md")), \
            "已移除缺 --delete-removed 保留"
        with open(os.path.join(hub, "grilling", "SKILL.md"), "r",
                  encoding="utf-8") as f:
            assert "手改" in f.read(), "不一致默认保留"
        # 链接层：装入是结构变化 -> 被调且拿仓库根
        assert link_calls == [root]
        assert not os.path.exists(os.path.join(link_dir, "wizard")), \
            "未删（无 flag）时链接层也不动"
        # 报告三段：计划段 + 枢纽同步段 + 副本段
        assert "枢纽族实体同步" in out
        sync_section = out.split("枢纽族实体同步")[1].split("其他市场插件副本")[0]
        assert "覆盖" in sync_section and "装入" in sync_section \
            and "保留" in sync_section
        assert "删除 " not in sync_section, "无删除动作时不出删除清单"
        assert "其他市场插件副本" in out and "未安装" in out, "副本刷新命令段收尾"


def test_cmd_update_rerun_skip_zero_hub_actions():
    """全链幂等：更新后重跑（pin==head）-> 全部 skip、不碰枢纽、不调链接层。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        old_tree, new_tree = make_two_pin_trees(tmp)
        old_tar = make_tar_of_tree(tmp, old_tree, "old.tar.gz")
        new_tar = make_tar_of_tree(tmp, new_tree, "new.tar.gz")
        hub = make_hub_from_tree(tmp, old_tree)
        link_calls = []
        tars = {OLD_SHA: old_tar, NEW_SHA: new_tar}
        seams = dict(fetch_head=lambda repo, ref: NEW_SHA,
                     fetch_version=lambda repo, sha: "2.0.0",
                     get_tarball=lambda repo, sha, dest_dir, timeout=120: tars[sha],
                     validator=lambda tree: GATE_PASS_OUTPUT,
                     run_link=lambda r: link_calls.append(r) or (True, "ok"),
                     collect_copies=missing_copy_rows)
        with contextlib.redirect_stdout(io.StringIO()):
            assert cmd_update(root, entry="alpha-skills", yes=True,
                              today=NEW_DATE, hub_dir=hub,
                              link_dir=os.path.join(tmp, "cc"), **seams) == 0
        snapshot = sorted(os.listdir(hub))
        tar_calls = []
        seams2 = dict(seams)
        seams2["get_tarball"] = (
            lambda repo, sha, dest_dir, timeout=120:
            tar_calls.append(sha) or tars[sha])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc2 = cmd_update(root, entry="alpha-skills", yes=True,
                             today=NEW_DATE, hub_dir=hub,
                             link_dir=os.path.join(tmp, "cc"), **seams2)
        assert rc2 == 0
        assert tar_calls == [], "重跑不下载（skip 在下载之前）"
        assert sorted(os.listdir(hub)) == snapshot, "重跑零枢纽动作"
        assert len(link_calls) == 1, "重跑不再调链接层"
        assert "已最新" in buf.getvalue()


def test_cmd_update_sync_error_exit_code_one():
    """枢纽同步单项错误（junction 拒覆盖）-> 退出码 1，但已写入的仓库文件不回滚。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        old_tree, new_tree = make_two_pin_trees(tmp)
        old_tar = make_tar_of_tree(tmp, old_tree, "old.tar.gz")
        new_tar = make_tar_of_tree(tmp, new_tree, "new.tar.gz")
        hub = make_hub_from_tree(tmp, old_tree)
        target = os.path.join(tmp, "tdd-repo")
        shutil.copytree(os.path.join(old_tree, "skills", "engineering", "tdd"),
                        target)
        shutil.rmtree(os.path.join(hub, "tdd"))
        make_junction(os.path.join(hub, "tdd"), target)
        tars = {OLD_SHA: old_tar, NEW_SHA: new_tar}
        rc = cmd_update(
            root, entry="alpha-skills", yes=True, today=NEW_DATE,
            hub_dir=hub, link_dir=os.path.join(tmp, "cc"),
            fetch_head=lambda repo, ref: NEW_SHA,
            fetch_version=lambda repo, sha: "2.0.0",
            get_tarball=lambda repo, sha, dest_dir, timeout=120: tars[sha],
            validator=lambda tree: GATE_PASS_OUTPUT,
            run_link=lambda r: (True, "ok"),
            collect_copies=missing_copy_rows)
        assert rc == 1, "枢纽有错误项 -> 退出码 1"
        data = json.loads(read_bytes(
            os.path.join(root, ".claude-plugin", "marketplace.json")).decode("utf-8"))
        alpha = next(p for p in data["plugins"] if p["name"] == "alpha-skills")
        assert alpha["metadata"]["pinnedSha"] == NEW_SHA, \
            "pin bump 已写入不回滚（错误只在枢纽单项）"
        assert os.path.isdir(os.path.join(hub, "teach")), "其余成员照常落地"


def test_cmd_update_dry_run_hub_planned_not_executed():
    """dry-run 全链：枢纽同步段只出计划（零写入、不调链接层），仓库文件零改动。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_fake_repo(tmp)
        old_tree, new_tree = make_two_pin_trees(tmp)
        old_tar = make_tar_of_tree(tmp, old_tree, "old.tar.gz")
        new_tar = make_tar_of_tree(tmp, new_tree, "new.tar.gz")
        hub = make_hub_from_tree(tmp, old_tree)
        snapshot = sorted(os.listdir(hub))
        link_calls = []
        tars = {OLD_SHA: old_tar, NEW_SHA: new_tar}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmd_update(
                root, entry="alpha-skills", dry_run=True, interactive=False,
                today=NEW_DATE, hub_dir=hub, link_dir=os.path.join(tmp, "cc"),
                fetch_head=lambda repo, ref: NEW_SHA,
                fetch_version=lambda repo, sha: "2.0.0",
                get_tarball=lambda repo, sha, dest_dir, timeout=120: tars[sha],
                validator=lambda tree: GATE_PASS_OUTPUT,
                run_link=lambda r: link_calls.append(r) or (True, "ok"),
                collect_copies=missing_copy_rows)
        assert rc == 0
        assert sorted(os.listdir(hub)) == snapshot, "dry-run 枢纽零写入"
        assert link_calls == [], "dry-run 不调链接层"
        out = buf.getvalue()
        assert "dry-run" in out and "未执行" in out, "枢纽段标注 dry-run"
        assert "将做的动作" in out


def test_build_hub_sync_report():
    """枢纽同步段报告措辞：四类清单+保留原因、错误项、链接层状态与补救命令、dry-run。"""
    sync_res = {
        "entries": [
            {"name": "alpha-skills", "overwrite": ["tdd"],
             "install": ["pr", "teach"], "remove": ["wizard"],
             "keep": [{"name": "grilling", "reason": KEEP_MISMATCH}],
             "same": ["code-review"],
             "errors": [{"name": "tdd", "error": "拒绝覆盖：junction"}]},
            {"name": "beta-skills", "overwrite": [], "install": [], "remove": [],
             "keep": [], "same": ["a", "b"], "errors": []},
        ],
        "structure_changed": True,
        "link": {"ran": True, "ok": False, "output": "boom: link 失败"}}
    text = "\n".join(build_hub_sync_report(sync_res))
    assert "alpha-skills" in text and "beta-skills" in text
    assert "覆盖" in text and "tdd" in text
    assert "装入" in text and "teach" in text
    assert "删除" in text and "wizard" in text and "链接层" in text
    assert "grilling" in text and KEEP_MISMATCH in text, "保留带原因"
    assert "已同步 1 个" in text, "已同步成员给计数即可（不逐个列名）"
    assert "拒绝覆盖" in text, "错误项进报告"
    assert "skill_distributor.py link" in text, "链接层失败给手动补救命令"
    assert "boom" in text

    text_ok = "\n".join(build_hub_sync_report({**sync_res, "link": {
        "ran": True, "ok": True, "output": "ok"}}))
    assert "已同步" in text_ok

    text_dry = "\n".join(build_hub_sync_report(sync_res, dry_run=True))
    assert "dry-run" in text_dry and "未执行" in text_dry

    text_noop = "\n".join(build_hub_sync_report({
        "entries": [{"name": "g", "overwrite": [], "install": [], "remove": [],
                     "keep": [], "same": ["x"], "errors": []}],
        "structure_changed": False,
        "link": {"ran": False, "ok": None, "output": ""}}))
    assert "结构无变化" in text_noop or "未调用" in text_noop

# ---------------------------------------------------------------- update 下半链：三方分类（票 04）

SYNC_CATS = {"tdd": "engineering", "code-review": "engineering",
             "grilling": "productivity", "wizard": "misc",
             "teach": "productivity", "pr": "engineering"}


def make_two_pin_trees(tmp):
    """票 04 分类夹具：旧/新两棵 pin 树。
    tdd 上游改了内容（干净落后样本）；code-review / grilling 原样；
    teach / pr 仅新树有（上游新增）；wizard 仅旧树有（上游已移除）。
    返回 (old_tree, new_tree)。"""
    old_tree = os.path.join(tmp, "tree-old")
    new_tree = os.path.join(tmp, "tree-new")
    for name in ("tdd", "code-review", "grilling", "wizard"):
        write_text(os.path.join(old_tree, "skills", SYNC_CATS[name], name, "SKILL.md"),
                   f"---\nname: {name}\n---\nbody of {name}\n")
    for name in ("tdd", "code-review", "grilling", "teach", "pr"):
        body = f"body of {name} v2\n" if name == "tdd" else f"body of {name}\n"
        write_text(os.path.join(new_tree, "skills", SYNC_CATS[name], name, "SKILL.md"),
                   f"---\nname: {name}\n---\n{body}")
    return old_tree, new_tree


def crlf_tree(root):
    """把树里全部文本文件重写为 CRLF 行尾（内容行不变）。"""
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            with open(p, "rb") as f:
                data = f.read().replace(b"\r\n", b"\n")
            with open(p, "wb") as f:
                f.write(data.replace(b"\n", b"\r\n"))


def test_classify_family_sync_five_actions():
    """三方分类五动作：干净落后覆盖 / 已同步不动 / 不一致保留 / 新增装入 / 已移除删除。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tree, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, old_tree)  # 枢纽 = 旧树原样拷贝
        with open(os.path.join(hub, "grilling", "SKILL.md"), "a",
                  encoding="utf-8") as f:
            f.write("手改一行\n")  # grilling：枢纽 != 旧基线 -> 不一致
        rows = classify_family_sync(old_tree, new_tree, hub)
        by = {r["name"]: r["action"] for r in rows}
        assert by == {
            "tdd": "sync-overwrite",     # 枢纽==旧 pin 且 != 新 pin -> 干净落后
            "code-review": "sync-same",  # 枢纽==旧==新 -> 已同步，不动
            "grilling": "sync-keep",     # 枢纽!=旧 pin -> 与基线不一致，默认保留
            "teach": "sync-install",     # 仅新 pin 有，枢纽缺 -> 装入
            "pr": "sync-install",
            "wizard": "sync-remove",     # 仅旧 pin 有，枢纽还在 -> 删
        }, "三方分类（枢纽实体 × 旧 pin × 新 pin）必须精确落到五个动作"
        cats = {r["name"]: r["category"] for r in rows}
        assert cats["teach"] == "productivity" and cats["wizard"] == "misc", \
            "分类行带分类归属（删除/装入要知道来自哪棵树的哪个分类）"


def test_classify_family_sync_baseline_no_old_tree():
    """建基线（旧树=None）：没有「干净落后/已移除」概念；已同步/保留/装入三分。"""
    with tempfile.TemporaryDirectory() as tmp:
        _old, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, new_tree)  # 枢纽已等于新树
        with open(os.path.join(hub, "tdd", "SKILL.md"), "a",
                  encoding="utf-8") as f:
            f.write("手改\n")
        rows = classify_family_sync(None, new_tree, hub)
        by = {r["name"]: r["action"] for r in rows}
        assert by["code-review"] == "sync-same", "枢纽==新树 -> 已同步"
        assert by["tdd"] == "sync-keep", "无旧基线可比，枢纽!=新树只能保守保留"
        assert "wizard" not in by, "建基线不删任何实体（没有「上游已移除」基线依据）"
        assert by["teach"] == "sync-same" and by["pr"] == "sync-same", \
            "枢纽已有且与新树一致的成员不动"

        shutil.rmtree(os.path.join(hub, "grilling"))
        rows2 = classify_family_sync(None, new_tree, hub)
        by2 = {r["name"]: r["action"] for r in rows2}
        assert by2["grilling"] == "sync-install", "旧成员枢纽缺失同样补装入"


def test_classify_family_sync_missing_member_in_hub_installs():
    """旧 pin 就有、但枢纽一直缺的成员 -> 装入（check 报「缺失」的闭环）。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tree, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, old_tree, omit=("code-review",))
        rows = classify_family_sync(old_tree, new_tree, hub)
        by = {r["name"]: r["action"] for r in rows}
        assert by["code-review"] == "sync-install", \
            "枢纽缺的族成员装入新树版本（无论上游是否新增）"


def test_classify_family_sync_crlf_not_drift():
    """CRLF 不误判（复用票 02 的 compare_tree 归一，覆盖 update 分类路径）：
    枢纽实体 CRLF、pin 树 LF 时，干净落后仍判覆盖、已同步不误判为漂移。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tree, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, old_tree)
        crlf_tree(os.path.join(hub, "tdd"))
        crlf_tree(os.path.join(hub, "code-review"))
        rows = classify_family_sync(old_tree, new_tree, hub)
        by = {r["name"]: r["action"] for r in rows}
        assert by["tdd"] == "sync-overwrite", \
            "仅行尾不同的干净落后必须判覆盖，不得升格为「与基线不一致」"
        assert by["code-review"] == "sync-same", "仅行尾不同不得误判为漂移/覆盖"


# ---------------------------------------------------------------- 差异摘要（票 04）

def test_diff_tree_summary():
    """「看 diff」的数据源：仅枢纽有 / 仅基线有 / 内容不同（行尾归一后）三清单。"""
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "a")
        b = os.path.join(tmp, "b")
        write_text(os.path.join(a, "same.md"), "x\n")
        write_text(os.path.join(a, "changed.md"), "old\n")
        write_text(os.path.join(a, "sub", "only-hub.md"), "h\n")
        write_text(os.path.join(b, "same.md"), "x\n")
        write_text(os.path.join(b, "changed.md"), "new\n")
        write_text(os.path.join(b, "only-base.md"), "b\n")
        d = diff_tree_summary(a, b)
        assert d["only_hub"] == [os.path.join("sub", "only-hub.md")]
        assert d["only_base"] == ["only-base.md"]
        assert d["changed"] == ["changed.md"]

        write_text(os.path.join(a, "crlf.md"), "x\r\ny\r\n")
        write_text(os.path.join(b, "crlf.md"), "x\ny\n")
        d2 = diff_tree_summary(a, b)
        assert "crlf.md" not in d2["changed"], "仅行尾不同不算内容差异"

        d3 = diff_tree_summary(os.path.join(tmp, "no-such"), b)
        assert d3["only_base"] and not d3["only_hub"] and not d3["changed"], \
            "枢纽侧目录整个不存在 = 全部仅基线有（缺失成员的 diff 形态）"


# ---------------------------------------------------------------- 实体操作（票 04）

def make_junction(link, target):
    """Windows junction 夹具：mklink /J 只能在 cmd 里建；建好断言确实可识别。

    cmd 输出是本地代码页（GBK），text 解码用 errors=replace 防崩（内容不参与断言）。
    """
    proc = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                          capture_output=True, text=True, errors="replace")
    assert proc.returncode == 0, f"mklink /J 失败: {(proc.stderr or proc.stdout).strip()}"
    assert is_link_path(link), "测试前置：is_link_path 必须能识别 junction"
    return link


def test_overwrite_entity_replaces_tree():
    """覆盖 = 删旧实体树后拷入新树：旧多出的文件消失、新子目录结构完整进来。"""
    with tempfile.TemporaryDirectory() as tmp:
        hub_entity = os.path.join(tmp, "hub-entity")
        src = os.path.join(tmp, "src")
        write_text(os.path.join(hub_entity, "old-only.md"), "旧独有\n")
        write_text(os.path.join(hub_entity, "SKILL.md"), "旧版\n")
        write_text(os.path.join(src, "SKILL.md"), "新版\n")
        write_text(os.path.join(src, "references", "a.md"), "新子目录\n")
        overwrite_entity(hub_entity, src)
        assert not os.path.exists(os.path.join(hub_entity, "old-only.md")), \
            "旧树多出的文件不得残留"
        with open(os.path.join(hub_entity, "SKILL.md"), "rb") as f:
            assert f.read() == "新版\n".encode("utf-8")
        assert os.path.isfile(os.path.join(hub_entity, "references", "a.md"))


def test_overwrite_entity_refuses_junction():
    """枢纽实体是 junction -> 拒绝覆盖并报错（绝不写穿链接改到链接目标）。"""
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "real")
        write_text(os.path.join(target, "SKILL.md"), "正本\n")
        link = make_junction(os.path.join(tmp, "linked"), target)
        try:
            overwrite_entity(link, os.path.join(tmp, "src"))
            raise AssertionError("junction 实体必须拒绝覆盖")
        except HubSyncError:
            pass
        with open(os.path.join(target, "SKILL.md"), "r", encoding="utf-8") as f:
            assert f.read() == "正本\n", "链接目标内容不得被写穿"
        assert is_link_path(link), "junction 本身保留原样（错误由报告表达）"


def test_remove_path_safe_never_through_junction():
    """删除安全：实体树整删；junction 只删链接本身（os.rmdir），目标正本完好。"""
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "real")
        write_text(os.path.join(target, "SKILL.md"), "正本\n")
        link = make_junction(os.path.join(tmp, "link"), target)
        remove_path_safe(link)
        assert not os.path.exists(link), "junction 已删"
        assert os.path.isfile(os.path.join(target, "SKILL.md")), \
            "junction 的目标正本必须完好无损（绝不递归删穿链接）"

        entity = os.path.join(tmp, "entity")
        write_text(os.path.join(entity, "sub", "f.md"), "x\n")
        remove_path_safe(entity)
        assert not os.path.exists(entity), "实体目录树整删"

        lonely = os.path.join(tmp, "lonely.txt")
        write_text(lonely, "x")
        remove_path_safe(lonely)
        assert not os.path.exists(lonely), "散文件也按删除处理"

        remove_path_safe(os.path.join(tmp, "no-such")), "不存在的路径静默跳过"


# ---------------------------------------------------------------- 枢纽同步编排（票 04）

def make_sync_plans(old_tree, new_tree, name="alpha-skills"):
    """手搓带树路径的 bump 计划（sync_hub_families 的输入形态）。"""
    return [{"action": "bump", "name": name, "repo": "alpha/one", "ref": "main",
             "old_sha": OLD_SHA, "new_sha": NEW_SHA, "new_ref": None,
             "date": NEW_DATE, "version": "2.0.0", "waived": [],
             "old_tree": old_tree, "new_tree": new_tree}]


def seq_input(answers):
    """应答序列 -> input 假件（逐个弹出，供交互函数测试）。"""
    it = iter(answers)
    return lambda _prompt: next(it)


def test_sync_hub_yes_mode_policy():
    """--yes 批量语义：干净落后自动覆盖、不一致默认保留、新增自动装入、
    已移除缺 --delete-removed 时保留并标注原因；结构变化触发链接层同步。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tree, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, old_tree)
        with open(os.path.join(hub, "grilling", "SKILL.md"), "a",
                  encoding="utf-8") as f:
            f.write("手改\n")
        link_calls = []

        def fake_link(root):
            link_calls.append(root)
            return True, "link ok"

        res = sync_hub_families(make_sync_plans(old_tree, new_tree), hub, tmp,
                                yes=True, run_link=fake_link)
        e = res["entries"][0]
        assert set(e["overwrite"]) == {"tdd"}, "干净落后自动覆盖"
        assert set(e["same"]) == {"code-review"}
        assert e["keep"] == [{"name": "grilling", "reason": KEEP_MISMATCH},
                             {"name": "wizard", "reason": KEEP_NO_FLAG}], \
            "不一致默认保留并标注原因；已移除缺 --delete-removed 保留并标注"
        assert set(e["install"]) == {"teach", "pr"}, "新增自动装入"
        assert e["remove"] == []
        assert e["errors"] == []
        # 产物核验
        with open(os.path.join(hub, "tdd", "SKILL.md"), "r", encoding="utf-8") as f:
            assert "v2" in f.read(), "tdd 覆盖为新版内容"
        assert os.path.isdir(os.path.join(hub, "teach"))
        assert os.path.isdir(os.path.join(hub, "pr"))
        assert os.path.isfile(os.path.join(hub, "wizard", "SKILL.md")), "wizard 保留"
        with open(os.path.join(hub, "grilling", "SKILL.md"), "r", encoding="utf-8") as f:
            assert "手改" in f.read(), "grilling 手改保留"
        assert res["structure_changed"] is True
        assert res["link"] == {"ran": True, "ok": True, "output": "link ok"}
        assert link_calls == [tmp], "链接层同步拿仓库根调用"


def test_sync_hub_delete_removed_with_flag():
    """--delete-removed：已移除成员连枢纽实体与链接层 junction 一起删，目标正本完好。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tree, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, old_tree)
        link_dir = os.path.join(tmp, "cc-skills")
        os.makedirs(link_dir)
        target = os.path.join(tmp, "wizard-backup")
        shutil.copytree(os.path.join(hub, "wizard"), target)
        make_junction(os.path.join(link_dir, "wizard"), target)

        res = sync_hub_families(make_sync_plans(old_tree, new_tree), hub, tmp,
                                yes=True, delete_removed=True, link_dir=link_dir,
                                run_link=lambda root: (True, "ok"))
        e = res["entries"][0]
        assert set(e["remove"]) == {"wizard"}
        assert not os.path.exists(os.path.join(hub, "wizard")), "枢纽实体已删"
        assert not os.path.lexists(os.path.join(link_dir, "wizard")), \
            "链接层同名 junction 一并删"
        assert os.path.isfile(os.path.join(target, "SKILL.md")), \
            "junction 目标正本完好（绝不递归删穿）"


def test_sync_hub_adopt_overrides_mismatch():
    """--adopt：声明枢纽无手改，不一致实体全部按干净落后处理直接覆盖。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tree, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, old_tree)
        with open(os.path.join(hub, "grilling", "SKILL.md"), "a",
                  encoding="utf-8") as f:
            f.write("手改\n")
        res = sync_hub_families(make_sync_plans(old_tree, new_tree), hub, tmp,
                                yes=True, adopt=True,
                                run_link=lambda root: (True, "ok"))
        e = res["entries"][0]
        assert set(e["overwrite"]) == {"tdd", "grilling"}, "--adopt 后不一致实体覆盖"
        assert e["keep"] == [{"name": "wizard", "reason": KEEP_NO_FLAG}], \
            "--adopt 只影响不一致实体，已移除仍按删除纪律保留"
        with open(os.path.join(hub, "grilling", "SKILL.md"), "r", encoding="utf-8") as f:
            assert "手改" not in f.read(), "grilling 被覆盖为新树内容"


def test_sync_hub_interactive_injected_deciders():
    """交互模式注入决策序列：不一致逐个 覆盖/保留（decider 收到 diff 行）、
    新增批量确认可拒、已移除逐个确认后删（交互同意即删，无需 --delete-removed）。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tree, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, old_tree)
        with open(os.path.join(hub, "grilling", "SKILL.md"), "a",
                  encoding="utf-8") as f:
            f.write("手改\n")
        mismatch_asked, install_asked, remove_asked = [], [], []

        def decide_mismatch(name, diff_lines):
            mismatch_asked.append((name, diff_lines))
            return "overwrite" if name == "grilling" else "keep"

        def confirm_installs(names):
            install_asked.append(list(names))
            return False  # 用户拒绝装入

        def decide_removals(names):
            remove_asked.append(list(names))
            return ["wizard"]

        res = sync_hub_families(make_sync_plans(old_tree, new_tree), hub, tmp,
                                yes=False, interactive=True,
                                decide_mismatch=decide_mismatch,
                                confirm_installs=confirm_installs,
                                decide_removals=decide_removals,
                                run_link=lambda root: (True, "ok"))
        e = res["entries"][0]
        assert [n for n, _ in mismatch_asked] == ["grilling"], "只有不一致实体被逐个问"
        assert any("SKILL.md" in ln for ln in mismatch_asked[0][1]), \
            "decider 拿到文件级差异摘要"
        assert install_asked == [["pr", "teach"]], "新增批量确认一次"
        # tdd 是干净落后：自动覆盖，不进交互
        assert set(e["overwrite"]) == {"tdd", "grilling"}
        assert {"name": "teach", "reason": KEEP_USER} in e["keep"]
        assert {"name": "pr", "reason": KEEP_USER} in e["keep"]
        assert set(e["remove"]) == {"wizard"}, "交互逐个同意后删除"
        assert not os.path.exists(os.path.join(hub, "wizard"))
        assert res["structure_changed"] is True


def test_sync_hub_link_only_on_structure_change():
    """链接层同步时机：纯覆盖（无新增/删除）不调用；仅当结构变化才调用。"""
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "t")
        old_tree = os.path.join(base, "old")
        new_tree = os.path.join(base, "new")
        for name, ver in (("tdd", "v1"), ("code-review", "v1")):
            write_text(os.path.join(old_tree, "skills", "engineering", name,
                                    "SKILL.md"),
                       f"---\nname: {name}\n---\nbody {ver}\n")
        write_text(os.path.join(new_tree, "skills", "engineering", "tdd",
                                "SKILL.md"), "---\nname: tdd\n---\nbody v2\n")
        write_text(os.path.join(new_tree, "skills", "engineering", "code-review",
                                "SKILL.md"), "---\nname: code-review\n---\nbody v1\n")
        hub = make_hub_from_tree(tmp, old_tree)
        hub = os.path.join(tmp, "hub")
        link_calls = []
        res = sync_hub_families(make_sync_plans(old_tree, new_tree), hub, tmp,
                                yes=True, run_link=lambda r: link_calls.append(r) or (True, "x"))
        assert res["entries"][0]["overwrite"] == ["tdd"]
        assert res["structure_changed"] is False
        assert res["link"]["ran"] is False and link_calls == [], \
            "纯覆盖不触发链接层同步"


def test_sync_hub_link_failure_reported_not_fatal():
    """链接层同步失败不回滚已写入、不抛异常：结果标 ok=False 供报告给手动补救命令。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tree, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, old_tree)
        res = sync_hub_families(make_sync_plans(old_tree, new_tree), hub, tmp,
                                yes=True,
                                run_link=lambda root: (False, "boom: link 失败"))
        assert res["link"]["ran"] is True and res["link"]["ok"] is False
        assert "boom" in res["link"]["output"]
        assert os.path.isdir(os.path.join(hub, "teach")), "装入产物不回滚"


def test_sync_hub_junction_aborts_single_member():
    """枢纽实体是 junction -> 该项报错中止且目标不被写穿；其余成员照常落地。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tree, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, old_tree)
        target = os.path.join(tmp, "tdd-repo")
        shutil.copytree(os.path.join(old_tree, "skills", "engineering", "tdd"),
                        target)
        shutil.rmtree(os.path.join(hub, "tdd"))
        make_junction(os.path.join(hub, "tdd"), target)  # 内容==旧树 -> 干净落后分类
        res = sync_hub_families(make_sync_plans(old_tree, new_tree), hub, tmp,
                                yes=True, run_link=lambda root: (True, "ok"))
        e = res["entries"][0]
        assert [err["name"] for err in e["errors"]] == ["tdd"], "junction 项进错误清单"
        assert "拒绝覆盖" in e["errors"][0]["error"] or "junction" in e["errors"][0]["error"]
        assert "tdd" not in e["overwrite"]
        with open(os.path.join(target, "SKILL.md"), "r", encoding="utf-8") as f:
            assert "v2" not in f.read(), "junction 目标绝不被写穿"
        assert os.path.isdir(os.path.join(hub, "teach")), "其余成员不受影响照常装入"


def test_sync_hub_idempotent_second_run_zero_actions():
    """同一状态重跑零动作：全 same、无结构变化、不再调链接层。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tree, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, old_tree)
        sync_hub_families(make_sync_plans(old_tree, new_tree), hub, tmp,
                          yes=True, delete_removed=True,
                          run_link=lambda root: (True, "ok"))
        link_calls = []
        res2 = sync_hub_families(make_sync_plans(old_tree, new_tree), hub, tmp,
                                 yes=True, delete_removed=True,
                                 run_link=lambda r: link_calls.append(r) or (True, "ok"))
        e = res2["entries"][0]
        assert e["overwrite"] == [] and e["install"] == [] and e["remove"] == []
        assert e["keep"] == [] and e["errors"] == []
        assert len(e["same"]) == 5, "全部成员已同步"
        assert res2["structure_changed"] is False and res2["link"]["ran"] is False
        assert link_calls == []


def test_sync_hub_dry_run_plans_only():
    """dry-run：分类与计划照出，但零写入、不调链接层。"""
    with tempfile.TemporaryDirectory() as tmp:
        old_tree, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, old_tree)
        before = sorted(os.listdir(hub))
        with open(os.path.join(hub, "grilling", "SKILL.md"), "a",
                  encoding="utf-8") as f:
            f.write("手改\n")
        res = sync_hub_families(make_sync_plans(old_tree, new_tree), hub, tmp,
                                yes=True, delete_removed=True, dry_run=True,
                                run_link=lambda root: (_ for _ in ()).throw(AssertionError("不该调用")))
        e = res["entries"][0]
        assert set(e["overwrite"]) == {"tdd"} and set(e["install"]) == {"teach", "pr"}
        assert set(e["remove"]) == {"wizard"}
        assert sorted(os.listdir(hub)) == before, "枢纽零写入"
        assert os.path.isdir(os.path.join(hub, "wizard")), "dry-run 不删"
        assert res["structure_changed"] is False and res["link"]["ran"] is False


def test_sync_hub_baseline_plan_no_old_tree():
    """建基线计划（old_tree=None）：不覆盖不删除，保留+装入照常。"""
    with tempfile.TemporaryDirectory() as tmp:
        _old, new_tree = make_two_pin_trees(tmp)
        hub = make_hub_from_tree(tmp, new_tree)
        with open(os.path.join(hub, "tdd", "SKILL.md"), "a",
                  encoding="utf-8") as f:
            f.write("手改\n")
        shutil.rmtree(os.path.join(hub, "grilling"))
        plans = [{"action": "baseline", "name": "beta-skills", "repo": "beta/two",
                  "ref": "HEAD", "old_sha": None, "new_sha": BASE_SHA,
                  "new_ref": "main", "date": NEW_DATE, "version": "0.9.0",
                  "waived": [], "old_tree": None, "new_tree": new_tree}]
        res = sync_hub_families(plans, hub, tmp, yes=True,
                                run_link=lambda root: (True, "ok"))
        e = res["entries"][0]
        assert e["overwrite"] == [] and e["remove"] == [], "无旧基线，不覆盖不删"
        assert set(e["install"]) == {"grilling"}
        assert {"name": "tdd", "reason": KEEP_MISMATCH} in e["keep"]


def test_prompt_mismatch_answer_sequences():
    """真实交互函数按应答序列工作：d 看 diff 后重问、非法答重问、o/k 生效。"""
    lines = ["内容不同: SKILL.md"]
    p = prompt_mismatch("x", lines, input_fn=seq_input(["d", "o"]))
    assert p == "overwrite", "d 先看 diff 再重问，o 覆盖"
    assert prompt_mismatch("x", lines, input_fn=seq_input(["k"])) == "keep"
    assert prompt_mismatch("x", lines, input_fn=seq_input(["bogus", "保留"])) == "keep", \
        "非法答重问，中文答也认"

    assert prompt_batch_install(["a", "b"], input_fn=seq_input(["y"])) is True
    assert prompt_batch_install(["a"], input_fn=seq_input(["n"])) is False
    assert prompt_removals(["a", "b"], input_fn=seq_input(["y", "n"])) == ["a"], \
        "已移除逐个确认，只删同意的"


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


def make_pin_tarball(tmp, top_name="skills-49dd158d", tar_name="pin.tar.gz"):
    """把上游树打成 codeload 形态的 tar.gz（单顶层目录），返回 (tar_path, tree_root)。"""
    tree_root = os.path.join(tmp, top_name)
    make_upstream_tree(tree_root)
    tar_path = os.path.join(tmp, tar_name)
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


def make_fake_repo(tmp):
    """tmp 假 market 仓库：marketplace.json（CRLF、2 空格缩进，带 pin/无 pin/本地
    三种条目）+ compat 文档（LF，外部聚合插件表格）+ plugins/ 目录
    （repo_root 的定位判据是 marketplace.json + plugins/，形态对齐真实仓库）。
    行尾形态对齐真实仓库（marketplace.json CRLF / compat LF）。"""
    root = os.path.join(tmp, "market")
    os.makedirs(os.path.join(root, ".claude-plugin"))
    os.makedirs(os.path.join(root, "docs"))
    os.makedirs(os.path.join(root, "plugins"))
    mp = {
        "name": "fake-market",
        "plugins": [
            alpha_entry(),
            {"name": "beta-skills", "description": "外部聚合无 pin",
             "source": {"source": "github", "repo": "beta/two"}},
            {"name": "local-plugin", "description": "本地条目",
             "source": "./plugins/local-plugin"},
        ],
    }
    body = json.dumps(mp, ensure_ascii=False, indent=2) + "\n"
    with open(os.path.join(root, ".claude-plugin", "marketplace.json"), "wb") as f:
        f.write(body.replace("\n", "\r\n").encode("utf-8"))
    with open(os.path.join(root, "docs", "plugin-compatibility.md"), "wb") as f:
        f.write(make_compat_text().encode("utf-8"))
    return root


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
    test_judge_validator_output,
    test_parse_symref_output,
    test_apply_pin_bump_syncs_note_and_idempotent,
    test_apply_pin_bump_baseline_creates_metadata,
    test_render_pin_cell,
    test_sync_compat_table,
    test_plan_updates_bump_and_baseline,
    test_plan_updates_gate_failure_isolated,
    test_plan_updates_skips_up_to_date,
    test_plan_updates_head_failure_isolated,
    test_plan_updates_keep_trees_carries_old_and_new,
    test_plan_updates_default_no_keep_cleans_up,
    test_plan_updates_old_tarball_failure_isolated,
    test_normalize_tree_root_renames_to_plugin_name,
    test_plan_updates_gate_receives_normalized_tree,
    test_apply_updates_writes_both_files,
    test_apply_updates_dry_run_zero_write,
    test_apply_updates_idempotent_byte_level,
    test_cmd_update_end_to_end_idempotent,
    test_cmd_update_guard_noninteractive,
    test_cmd_update_gate_failure_aborts_zero_write,
    test_cmd_update_dry_run_zero_write,
    test_cmd_update_entry_filter,
    test_cmd_update_entry_unknown,
    test_build_update_report,
    test_classify_family_sync_five_actions,
    test_classify_family_sync_baseline_no_old_tree,
    test_classify_family_sync_missing_member_in_hub_installs,
    test_classify_family_sync_crlf_not_drift,
    test_diff_tree_summary,
    test_overwrite_entity_replaces_tree,
    test_overwrite_entity_refuses_junction,
    test_remove_path_safe_never_through_junction,
    test_sync_hub_yes_mode_policy,
    test_sync_hub_delete_removed_with_flag,
    test_sync_hub_adopt_overrides_mismatch,
    test_sync_hub_interactive_injected_deciders,
    test_sync_hub_link_only_on_structure_change,
    test_sync_hub_link_failure_reported_not_fatal,
    test_sync_hub_junction_aborts_single_member,
    test_sync_hub_idempotent_second_run_zero_actions,
    test_sync_hub_dry_run_plans_only,
    test_sync_hub_baseline_plan_no_old_tree,
    test_prompt_mismatch_answer_sequences,
    test_cmd_update_full_chain_hub_sync,
    test_cmd_update_rerun_skip_zero_hub_actions,
    test_cmd_update_sync_error_exit_code_one,
    test_cmd_update_dry_run_hub_planned_not_executed,
    test_build_hub_sync_report,
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
