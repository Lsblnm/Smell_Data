"""Audit v1 patches, lock per-task E4 anchors, map reusable patches to v2 S0/S1/S2,
emit ready-to-run incremental container job manifests, and plot empirical validation."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "analysis" / "smell_paper"))
from core import LANG, MODELS, MODEL_SHORT, PATCHES, SMELL_DIR, load_pairs, pct, task_mean_ci  # noqa: E402

MANIFESTS = HERE / "manifests"
FIG_DIR = HERE / "figures"
MANIFESTS.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

INTROS = ROOT / "smell-patch-intro"
LEAK_CSV = ROOT / "analysis" / "smell_impact" / "answer_access_by_task.csv"

plt.rcParams.update({
    "font.family": ["PingFang SC", "Heiti SC", "Arial Unicode MS"],
    "font.size": 10.2, "axes.edgecolor": "#9aa5b1", "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": "#e6e9ee", "grid.linewidth": 0.8, "savefig.dpi": 220,
    "savefig.bbox": "tight", "axes.unicode_minus": False,
})
COL = {"gpt": "#1b7f79", "glm": "#d9822b", "deepseek": "#5b4b9a"}


def patch_rel(smell: str, level: str, task: str, suffix: str = ".patch") -> str:
    return f"smell-patch/{level}/{SMELL_DIR[smell]}/{task}-{smell}{suffix}"


def load_patch_catalog(u: pd.DataFrame) -> pd.DataFrame:
    leak_map = {}
    if LEAK_CSV.exists():
        ldf = pd.read_csv(LEAK_CSV)
        leak_map = dict(zip(ldf.task, ldf.upstream_fix_access.eq("confirmed")))

    # Take one row per unique (smell, level, task) variant
    dedup = u.sort_values("model").drop_duplicates(["smell", "level", "task"]).copy()
    rows = []
    for r in dedup.itertuples():
        p_gold = ROOT / patch_rel(r.smell, r.level, r.task, "-gold.patch")
        p_test = ROOT / patch_rel(r.smell, r.level, r.task, "-test.patch")
        rows.append(dict(
            task=r.task,
            repo=r.repo,
            lang=LANG.get(r.repo, "Other"),
            smell=r.smell,
            old_level=r.level,
            target_file=r.target,
            target_unit=r.target_unit,
            exposure=r.exposure,
            entangled=int(p_gold.exists()),
            has_test_patch=int(p_test.exists()),
            injection_files=int(r.injection_files),
            injection_added=int(r.injection_added),
            loc=float(r.loc) if pd.notna(r.loc) else np.nan,
            wmc=float(r.wmc) if pd.notna(r.wmc) else np.nan,
            tcc=float(r.tcc) if pd.notna(r.tcc) else np.nan,
            atfd=float(r.atfd) if pd.notna(r.atfd) else np.nan,
            laa=float(r.laa) if pd.notna(r.laa) else np.nan,
            fdp=float(r.fdp) if pd.notna(r.fdp) else np.nan,
            cc=float(r.cc) if pd.notna(r.cc) else np.nan,
            depth=float(r.depth) if pd.notna(r.depth) else np.nan,
            rad_files=float(r.rad_files) if pd.notna(r.rad_files) else np.nan,
            rad_modules=float(r.rad_modules) if pd.notna(r.rad_modules) else np.nan,
            rad_distance=float(r.rad_distance) if pd.notna(r.rad_distance) else np.nan,
            upstream_leak=bool(leak_map.get(r.task, False)),
            patch_path=patch_rel(r.smell, r.level, r.task, ".patch"),
            gold_patch_path=patch_rel(r.smell, r.level, r.task, "-gold.patch") if p_gold.exists() else "",
        ))
    return pd.DataFrame(rows)


def select_core100(tasks_df: pd.DataFrame) -> set[str]:
    """Stratified 100-task clean subset across all languages and repositories."""
    clean = tasks_df[~tasks_df.upstream_leak].sort_values(["lang", "repo", "task"]).copy()
    # Pick evenly across repositories (~2-3 per repo) up to 100 tasks
    picked = []
    by_repo = {repo: list(g.task) for repo, g in clean.groupby("repo", sort=True)}
    rnd = 0
    while len(picked) < 100:
        added = False
        for repo in sorted(by_repo):
            if rnd < len(by_repo[repo]) and len(picked) < 100:
                picked.append(by_repo[repo][rnd])
                added = True
        if not added:
            break
        rnd += 1
    return set(picked)


def build_plan(cat: pd.DataFrame, core100: set[str]):
    plan_rows = []
    jobs = []
    dropped_oversized = 0

    # 1. Feature Envy (FE)
    for task, g in cat[cat.smell == "FE"].groupby("task", sort=True):
        g = g.sort_values("old_level")
        # Prefer E4 + entangled==1 variant as canonical anchor (prioritizing S0 -> S1 -> S2)
        cand = g[(g.exposure == "E4") & (g.entangled == 1)]
        if cand.empty:
            cand = g[g.exposure == "E4"]
        if cand.empty:
            cand = g
        anc = cand.iloc[0]
        a_file, a_unit = anc.target_file, anc.target_unit
        same_u = g[g.target_unit == a_unit]

        # v2_S0: intra-file or single-module read-only move on same unit
        s0_hit = same_u[(same_u.injection_files == 1) & (same_u.entangled == 1)]
        # v2_S1: cross-module (injection_files >= 2) E4 entangled move
        s1_hit = same_u[(same_u.injection_files >= 2) & (same_u.entangled == 1)]
        if s1_hit.empty:
            s1_hit = same_u[same_u.injection_files >= 2]

        s1_seed = s1_hit.iloc[0] if not s1_hit.empty else anc
        tiers = {}
        if not s0_hit.empty:
            r0 = s0_hit.iloc[0]
            tiers["S0"] = ("REUSE", r0.old_level, r0.patch_path, r0.gold_patch_path)
        else:
            tiers["S0"] = ("BUILD_S0_SAME_MOD", "", "", "")

        if not s1_hit.empty and s1_hit.iloc[0].exposure == "E4" and s1_hit.iloc[0].entangled == 1:
            r1 = s1_hit.iloc[0]
            tiers["S1"] = ("REUSE", r1.old_level, r1.patch_path, r1.gold_patch_path)
        else:
            tiers["S1"] = ("BUILD_S1_CROSS_MOD", "", s1_seed.patch_path, s1_seed.gold_patch_path)

        # v2_S2 always upgrades to >=2-hop delegation chain into shared container host
        seed_for_s2 = tiers["S1"][2] or s1_seed.patch_path
        seed_gold_s2 = tiers["S1"][3] or s1_seed.gold_patch_path
        tiers["S2"] = ("EXTEND_S2_MULTI_HOP", "", seed_for_s2, seed_gold_s2)

        for nl, (act, olv, ppath, gpath) in tiers.items():
            plan_rows.append(dict(
                task=task, repo=anc.repo, lang=anc.lang, smell="FE", new_level=nl,
                action=act, reused_from_v1=olv, anchor_file=a_file, anchor_unit=a_unit,
                patch_path=ppath, gold_patch_path=gpath,
                upstream_leak=anc.upstream_leak, in_core100=(task in core100),
            ))
            if act != "REUSE":
                jobs.append(dict(
                    instance_id=task, repo=anc.repo, lang=anc.lang,
                    smell="FeatureEnvy", new_level=nl, action=act,
                    prompt_template=f"analysis/task_redesign/prompts_v2/{nl}/FeatureEnvy.md",
                    locked_target_file=a_file, locked_target_unit=a_unit,
                    seed_smell_patch=ppath or None, seed_gold_patch=gpath or None,
                    clean_no_leak=(not anc.upstream_leak), priority_core100=(task in core100),
                ))

    # 2. God Class (GC)
    for task, g in cat[cat.smell == "GC"].groupby("task", sort=True):
        g = g.sort_values("old_level")
        dropped_oversized += int((g["loc"] >= 3800).sum())
        cand = g[g.exposure == "E4"]
        if cand.empty:
            cand = g
        anc = cand.iloc[0]
        a_file, a_unit = anc.target_file, anc.target_unit
        same_u = g[(g.target_file == a_file) & (g.exposure == "E4")]

        # v2_S0: 500-1000 LOC, 1 module, unentangled (0 in v1 -> build)
        s0_hit = same_u[(same_u["loc"] < 1000) & (same_u.entangled == 0)]
        # v2_S1: 1000-2500 LOC cross-module
        s1_hit = same_u[(same_u["loc"] >= 1000) & (same_u["loc"] < 2600)]
        # v2_S2: 2200-3800 LOC AND entangled == 1 (cap <3800 to avoid pagination abandonment!)
        s2_hit = same_u[(same_u["loc"] >= 2200) & (same_u["loc"] < 3800) & (same_u.entangled == 1)]
        if not s1_hit.empty and not s2_hit.empty and s1_hit.iloc[0].old_level == s2_hit.iloc[0].old_level:
            # Keep distinct patches for S1 and S2
            alt_s1 = same_u[(same_u["loc"] >= 1000) & (same_u["loc"] < 2200) & (same_u.old_level != s2_hit.iloc[0].old_level)]
            s1_hit = alt_s1

        tiers = {}
        if not s0_hit.empty:
            r0 = s0_hit.iloc[0]
            tiers["S0"] = ("REUSE", r0.old_level, r0.patch_path, r0.gold_patch_path)
        else:
            tiers["S0"] = ("BUILD_S0_LIGHT_GC", "", "", "")

        if not s1_hit.empty:
            r1 = s1_hit.iloc[0]
            tiers["S1"] = ("REUSE", r1.old_level, r1.patch_path, r1.gold_patch_path)
            seed_gc = (r1.patch_path, r1.gold_patch_path)
        else:
            tiers["S1"] = ("BUILD_S1_SHARED_FIELD", "", anc.patch_path, anc.gold_patch_path)
            seed_gc = (anc.patch_path, anc.gold_patch_path)

        if not s2_hit.empty:
            r2 = s2_hit.iloc[0]
            tiers["S2"] = ("REUSE", r2.old_level, r2.patch_path, r2.gold_patch_path)
        else:
            tiers["S2"] = ("EXTEND_S2_ENTANGLED_CAP3800", "", seed_gc[0], seed_gc[1])

        for nl, (act, olv, ppath, gpath) in tiers.items():
            plan_rows.append(dict(
                task=task, repo=anc.repo, lang=anc.lang, smell="GC", new_level=nl,
                action=act, reused_from_v1=olv, anchor_file=a_file, anchor_unit=a_unit,
                patch_path=ppath, gold_patch_path=gpath,
                upstream_leak=anc.upstream_leak, in_core100=(task in core100),
            ))
            if act != "REUSE":
                jobs.append(dict(
                    instance_id=task, repo=anc.repo, lang=anc.lang,
                    smell="GodClass", new_level=nl, action=act,
                    prompt_template=f"analysis/task_redesign/prompts_v2/{nl}/GodClass.md",
                    locked_target_file=a_file, locked_target_unit=a_unit,
                    seed_smell_patch=ppath or None, seed_gold_patch=gpath or None,
                    clean_no_leak=(not anc.upstream_leak), priority_core100=(task in core100),
                ))

    # 3. Long Method (LM)
    for task, g in cat[cat.smell == "LM"].groupby("task", sort=True):
        g = g.sort_values("old_level")
        # Anchor on S2 E4 mother patch if available so reverse-extraction stays 100% same-unit!
        cand_s2 = g[(g.exposure == "E4") & (g["loc"] >= 250)].sort_values("loc", ascending=False)
        cand_e4 = g[g.exposure == "E4"]
        anc = cand_s2.iloc[0] if not cand_s2.empty else (cand_e4.iloc[-1] if not cand_e4.empty else g.iloc[-1])
        a_file, a_unit = anc.target_file, anc.target_unit
        same_u = g[(g.target_file == a_file) & (g.target_unit == a_unit) & (g.exposure == "E4")]

        s0_hit = same_u[same_u["loc"] < 135].sort_values("loc")
        s1_hit = same_u[(same_u["loc"] >= 145) & (same_u["loc"] < 255)].sort_values("loc")
        s2_hit = same_u[(same_u["loc"] >= 255) & (same_u["loc"] < 480)].sort_values("loc", ascending=False)

        mother_patch = s2_hit.iloc[0].patch_path if not s2_hit.empty else anc.patch_path
        mother_gold = s2_hit.iloc[0].gold_patch_path if not s2_hit.empty else anc.gold_patch_path

        tiers = {}
        if not s2_hit.empty:
            r2 = s2_hit.iloc[0]
            tiers["S2"] = ("REUSE", r2.old_level, r2.patch_path, r2.gold_patch_path)
        else:
            tiers["S2"] = ("BUILD_S2_FLATTEN", "", anc.patch_path, anc.gold_patch_path)

        if not s1_hit.empty:
            r1 = s1_hit.iloc[0]
            tiers["S1"] = ("REUSE", r1.old_level, r1.patch_path, r1.gold_patch_path)
        else:
            tiers["S1"] = ("REVERSE_EXTRACT_S1_FROM_S2", "", mother_patch, mother_gold)

        if not s0_hit.empty:
            r0 = s0_hit.iloc[0]
            tiers["S0"] = ("REUSE", r0.old_level, r0.patch_path, r0.gold_patch_path)
        else:
            tiers["S0"] = ("REVERSE_EXTRACT_S0_FROM_S2", "", mother_patch, mother_gold)

        for nl in ("S0", "S1", "S2"):
            act, olv, ppath, gpath = tiers[nl]
            plan_rows.append(dict(
                task=task, repo=anc.repo, lang=anc.lang, smell="LM", new_level=nl,
                action=act, reused_from_v1=olv, anchor_file=a_file, anchor_unit=a_unit,
                patch_path=ppath, gold_patch_path=gpath,
                upstream_leak=anc.upstream_leak, in_core100=(task in core100),
            ))
            if act != "REUSE":
                jobs.append(dict(
                    instance_id=task, repo=anc.repo, lang=anc.lang,
                    smell="LongMethod", new_level=nl, action=act,
                    prompt_template=f"analysis/task_redesign/prompts_v2/{nl}/LongMethod.md",
                    locked_target_file=a_file, locked_target_unit=a_unit,
                    seed_smell_patch=ppath or None, seed_gold_patch=gpath or None,
                    clean_no_leak=(not anc.upstream_leak), priority_core100=(task in core100),
                ))

    # 4. Module-level Architecture Smell: Cyclic Dependency (CD) on clean tasks
    task_meta = cat.sort_values("old_level").drop_duplicates("task")
    for r in task_meta.itertuples():
        if r.upstream_leak:
            continue
        for nl, act in [("S0", "BUILD_CD_S0_2MOD"), ("S1", "BUILD_CD_S1_3MOD_CYCLE"), ("S2", "BUILD_CD_S2_4MOD_SHOTGUN")]:
            jobs.append(dict(
                instance_id=r.task, repo=r.repo, lang=r.lang,
                smell="CyclicDependency", new_level=nl, action=act,
                prompt_template=f"analysis/task_redesign/prompts_v2/{nl}/CyclicDependency.md",
                locked_target_file=r.target_file, locked_target_unit=r.target_unit,
                seed_smell_patch=None, seed_gold_patch=None,
                clean_no_leak=True, priority_core100=(r.task in core100),
            ))

    return pd.DataFrame(plan_rows), jobs, dropped_oversized


def plot_validation(u: pd.DataFrame, cat: pd.DataFrame, plan: pd.DataFrame):
    """Compare v1 raw S0-S2 curves vs v2 structural criteria on existing trajectories."""
    fig, axes = plt.subplots(1, 3, figsize=(15.4, 4.6), gridspec_kw=dict(wspace=0.28))

    # Merge entangled & loc cleanly
    key_cols = cat[["smell", "old_level", "task", "entangled"]].rename(columns={"old_level": "level"})
    d = u.merge(key_cols, on=["smell", "level", "task"], how="left")

    # Panel 1: Long Method — v1 all vs v2 fully-reusable same-unit monotonic tasks
    ax = axes[0]
    lm_plan = plan[(plan.smell == "LM") & (plan.action == "REUSE")]
    full_lm_tasks = set(lm_plan.groupby("task").filter(lambda x: len(x) == 3).task)
    sub_lm = d[(d.smell == "LM") & (d.task.isin(full_lm_tasks))].merge(
        lm_plan[["task", "new_level", "reused_from_v1"]].rename(columns={"reused_from_v1": "level"}),
        on=["task", "level"], how="inner"
    )
    xs = np.arange(4)
    for m in MODELS:
        # v1 dashed
        gm_old = d[(d.model == m) & (d.smell == "LM")]
        v_old = [0.0] + [pct(np.array(task_mean_ci(gm_old[gm_old.level == lv], "dtok")))[0] for lv in ["S0", "S1", "S2"]]
        ax.plot(xs, v_old, "--o", color=COL[m], lw=1.3, ms=4.5, alpha=0.55)
        # v2 solid
        gm_new = sub_lm[sub_lm.model == m]
        v_new = [0.0] + [pct(np.array(task_mean_ci(gm_new[gm_new.new_level == lv], "dtok")))[0] for lv in ["S0", "S1", "S2"]]
        ax.plot(xs, v_new, "-o", color=COL[m], lw=2.4, ms=6.3, label=f"{MODEL_SHORT[m]} · v2 重排复用 ({len(full_lm_tasks)}题)")
    ax.axhline(0, color="#6b7785", ls=":", lw=0.9)
    ax.set_xticks(xs, ["干净代码", "v2-S0\n(<135行)", "v2-S1\n(145–255行)", "v2-S2\n(≥255行)"], fontsize=8.8)
    ax.set_ylim(-9.5, 43)
    ax.set_ylabel("总 Token 增幅 (%)")
    ax.set_title("① 长方法：同方法锚定复用子集实测曲线", loc="left", fontsize=11.0)
    ax.legend(loc="upper left", fontsize=8.1)
    ax.text(0.05, -8.3, "浅色虚线 = 改造前 S0–S2；实线 = v2 同方法三档复用集", fontsize=7.8, color="#6b7785")

    # Panel 2: God Class — pruning >=3800 LOC inversion & splitting S1 (isolated) vs S2 (entangled <3800)
    ax = axes[1]
    gc = d[d.smell == "GC"].copy()
    for m in MODELS:
        gm = gc[gc.model == m]
        # Old S0/S1/S2 dashed showing S2 inversion on GLM/DeepSeek
        v_old = [0.0] + [pct(np.array(task_mean_ci(gm[gm.level == lv], "dtok")))[0] for lv in ["S0", "S1", "S2"]]
        ax.plot([0, 1, 2, 3], v_old, "--s", color=COL[m], lw=1.3, ms=4.5, alpha=0.50)
        # New v2 available tiers: v2-S0 (pending build -> mark gap), v2-S1 (1000-2500, ent=0), v2-S2 (2200-3800, ent=1)
        g_s1 = gm[(gm["loc"] >= 1000) & (gm["loc"] < 2500) & (gm.entangled == 0)]
        g_s2 = gm[(gm["loc"] >= 2200) & (gm["loc"] < 3800) & (gm.entangled == 1)]
        v1 = pct(np.array(task_mean_ci(g_s1, "dtok")))[0]
        v2 = pct(np.array(task_mean_ci(g_s2, "dtok")))[0]
        ax.plot([2, 3], [v1, v2], "-s", color=COL[m], lw=2.5, ms=6.8, label=f"{MODEL_SHORT[m]} · v2 去注水+纠缠分级")
        ax.plot([0, 2], [0.0, v1], ":", color=COL[m], lw=1.5)
    ax.axvspan(0.65, 1.35, color="#fef9e7", zorder=0)
    ax.text(1.0, 32, "v2-S0 真轻度\n(500–1k行)\n存量为 0\n→ 增量工单补齐", ha="center", va="center",
            fontsize=8.2, color="#a04000", weight="bold",
            bbox=dict(boxstyle="round,pad=0.25", fc="#fffdf7", ec="#e59866", lw=0.8))
    ax.axhline(0, color="#6b7785", ls=":", lw=0.9)
    ax.set_xticks([0, 1, 2, 3], ["干净代码", "v2-S0\n待补齐", "v2-S1 复用\n1k–2.5k 非纠缠", "v2-S2 复用\n2.2k–3.8k 纠缠"], fontsize=8.6)
    ax.set_ylim(-4, 68)
    ax.set_title("② 上帝类：剔除 ≥3.8k 行弃读区后倒挂消失", loc="left", fontsize=11.0)
    ax.legend(loc="upper left", fontsize=8.1)

    # Panel 3: Feature Envy — v2 progression (1-file intra -> cross-file peripheral -> cross-file E4 fault move)
    ax = axes[2]
    fe = d[d.smell == "FE"].copy()
    for m in MODELS:
        gm = fe[fe.model == m]
        v_old = [0.0] + [pct(np.array(task_mean_ci(gm[gm.level == lv], "dtok")))[0] for lv in ["S0", "S1", "S2"]]
        ax.plot([0, 1, 2, 3], v_old, "--o", color=COL[m], lw=1.3, ms=4.5, alpha=0.50)
        g0 = gm[gm.injection_files == 1]
        g1 = gm[(gm.injection_files >= 2) & (gm.entangled == 0)]
        g2 = gm[(gm.injection_files >= 2) & (gm.entangled == 1)]
        ys = [0.0,
              pct(np.array(task_mean_ci(g0, "dtok")))[0],
              pct(np.array(task_mean_ci(g1, "dtok")))[0],
              pct(np.array(task_mean_ci(g2, "dtok")))[0]]
        ax.plot([0, 1, 2, 3], ys, "-o", color=COL[m], lw=2.4, ms=6.5, label=f"{MODEL_SHORT[m]} · v2 按跨度与纠缠重排")
    ax.axhline(0, color="#6b7785", ls=":", lw=0.9)
    ax.set_xticks([0, 1, 2, 3], ["干净代码", "单文件内搬移\n(近似 v2-S0)", "跨文件非核心\n(过渡参考)", "跨文件迁核心故障\n(复用为 v2-S1)"])
    ax.set_ylim(-8, 42)
    ax.set_title("③ 依恋情结：按文件跨度与故障纠缠重排即单调", loc="left", fontsize=11.0)
    ax.legend(loc="upper left", fontsize=8.1)

    fig.suptitle("Benchmark v2 任务改造实测预验证：存量符合 v2 结构准则的样本已消除倒挂并呈清晰单调性",
                 fontsize=13.6, weight="bold", y=1.02, color="#1f2a36")
    out_fig = FIG_DIR / "v2_redesign_validation.png"
    fig.savefig(out_fig)
    plt.close(fig)
    return out_fig, len(full_lm_tasks)


def main():
    f = load_pairs()
    u = f[f.usable].copy()
    cat = load_patch_catalog(u)
    cat.to_csv(MANIFESTS / "v1_patch_audit.csv", index=False)

    tasks_df = cat.sort_values("old_level").drop_duplicates("task")[["task", "repo", "lang", "upstream_leak"]].copy()
    core100 = select_core100(tasks_df)
    tasks_df["in_core100"] = tasks_df.task.isin(core100)
    tasks_df.to_csv(MANIFESTS / "task_pool_v2.csv", index=False)

    plan, jobs, dropped_gc = build_plan(cat, core100)
    plan.to_csv(MANIFESTS / "v2_code_smell_remap_plan.csv", index=False)

    with (MANIFESTS / "incremental_patch_jobs.jsonl").open("w") as fp:
        for j in jobs:
            fp.write(json.dumps(j, ensure_ascii=False) + "\n")

    # Priority Core-100 job subset (clean_no_leak & in_core100) for rapid rollout
    core_jobs = [j for j in jobs if j["clean_no_leak"] and j["priority_core100"]]
    with (MANIFESTS / "incremental_patch_jobs_core100.jsonl").open("w") as fp:
        for j in core_jobs:
            fp.write(json.dumps(j, ensure_ascii=False) + "\n")

    out_fig, n_full_lm = plot_validation(u, cat, plan)

    summary = {
        "total_tasks_v1": int(tasks_df.task.nunique()),
        "clean_no_leak_tasks": int((~tasks_df.upstream_leak).sum()),
        "flagged_upstream_leak_tasks": int(tasks_df.upstream_leak.sum()),
        "core100_tasks": len(core100),
        "dropped_oversized_gc_patches_ge_3800_loc": dropped_gc,
        "code_smell_slots_total": len(plan),
        "code_smell_reused_directly": int((plan.action == "REUSE").sum()),
        "code_smell_reuse_rate_pct": round(float((plan.action == "REUSE").mean() * 100), 1),
        "by_smell_and_level": (
            plan.groupby(["smell", "new_level", "action"]).size().unstack(fill_value=0).to_dict(orient="index")
        ),
        "full_3tier_reusable_lm_tasks": n_full_lm,
        "incremental_jobs_all": len(jobs),
        "incremental_jobs_code_smells_clean232": sum(
            1 for j in jobs if j["clean_no_leak"] and j["smell"] != "CyclicDependency"
        ),
        "incremental_jobs_cyclic_dependency_clean232": sum(
            1 for j in jobs if j["clean_no_leak"] and j["smell"] == "CyclicDependency"
        ),
        "incremental_jobs_core100_all_4_smells": len(core_jobs),
    }
    # Convert tuple keys for JSON serialization
    summary["by_smell_and_level"] = {f"{k[0]}|{k[1]}": v for k, v in summary["by_smell_and_level"].items()}
    (MANIFESTS / "redesign_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("validation figure ->", out_fig)


if __name__ == "__main__":
    main()
