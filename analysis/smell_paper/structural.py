"""Deep structural-logic dimensions (from smell-patch & intros) and 4-stage cognitive trajectory decomposition."""

from __future__ import annotations

import json
import re
from collections import defaultdict

import numpy as np
import pandas as pd

from core import MODELS, PATCHES, ROOT, SMELL_DIR, SMELLS, cluster_boot, pct, task_mean_ci

CF_KW = re.compile(r"\b(if|else|elif|elsif|for|foreach|while|switch|case|catch|except|match)\b")
INTROS = ROOT / "smell-patch-intro"


def compute_deep_structure(u: pd.DataFrame, runs: pd.DataFrame, calls: pd.DataFrame) -> dict:
    # 1. Extract universal patch-level structural features per (smell, level, task)
    pmeta = {}
    for (smell, level, task), _ in u.groupby(["smell", "level", "task"]):
        dname = SMELL_DIR[smell]
        stub = f"{task}-{smell}"
        raw = (PATCHES / level / dname / f"{stub}.patch").read_text(errors="ignore")
        p_gold = PATCHES / level / dname / f"{stub}-gold.patch"
        plus_lines = [l[1:] for l in raw.splitlines() if l.startswith("+") and not l.startswith("+++ ")]
        cf_added = len(CF_KW.findall("\n".join(plus_lines)))
        txt = (INTROS / level / dname / f"{stub}.json").read_text(errors="ignore")
        info = json.JSONDecoder().raw_decode(txt[txt.index("{"):])[0]
        src = info["注入位置"].get("来源文件")
        src_list = src if isinstance(src, list) else ([src] if src else [])
        target = info["注入位置"]["目标文件"]
        pmeta[(smell, level, task)] = dict(
            entangled=int(p_gold.exists()),
            cf_added=cf_added,
            n_src_files=len(set(src_list) - {target}),
        )
    pf = pd.DataFrame.from_dict(pmeta, orient="index")
    pf.index.names = ["smell", "level", "task"]
    d = u.merge(pf.reset_index(), on=["smell", "level", "task"], how="left")

    # 2. Index calls per (model, group, task) to extract 4 cognitive stages
    by_run = defaultdict(list)
    for c in calls.itertuples():
        att = c.attributed if isinstance(c.attributed, str) else ""
        by_run[(c.model, c.group, c.task)].append((c.k, c.tool, c.cat, c.status, c.matches, att))
    step_counts = {(r.model, r.group, r.task): r.steps for r in runs.itertuples()}

    def run_stages(model, group, task, target):
        key = (model, group, task)
        n_steps = step_counts.get(key, 0)
        seq = by_run.get(key, ())
        first_target_k = None
        first_edit_k = None
        edit_err = 0
        grep_matches = 0
        tbase = target.rsplit("/", 1)[-1]
        for k, tool, cat, status, matches, att in seq:
            if first_target_k is None and att:
                for item in att.split(";"):
                    fp = item.rpartition("=")[0]
                    if fp == target or fp.endswith("/" + tbase):
                        first_target_k = k
                        break
            if cat == "edit":
                if status == "completed" and first_edit_k is None:
                    first_edit_k = k
                elif status == "error":
                    edit_err += 1
            if tool == "grep":
                grep_matches += int(matches or 0)
        nav = float(first_target_k) if first_target_k is not None else np.nan
        slc = float(max(0, first_edit_k - first_target_k)) if (first_edit_k is not None and first_target_k is not None and first_edit_k >= first_target_k) else np.nan
        post = float(max(0, n_steps - first_edit_k)) if first_edit_k is not None else np.nan
        return nav, slc, post, int(edit_err > 0), grep_matches

    b_cols = [run_stages(r.model, "None-" + r.smell, r.task, r.target) for r in d.itertuples()]
    v_cols = [run_stages(r.model, f"{r.smell}-{r.level}", r.task, r.target) for r in d.itertuples()]
    stage_df = pd.DataFrame({
        "b_nav": [x[0] for x in b_cols], "b_slice": [x[1] for x in b_cols], "b_post": [x[2] for x in b_cols],
        "b_edit_err": [x[3] for x in b_cols], "b_grep_m": [x[4] for x in b_cols],
        "v_nav": [x[0] for x in v_cols], "v_slice": [x[1] for x in v_cols], "v_post": [x[2] for x in v_cols],
        "v_edit_err": [x[3] for x in v_cols], "v_grep_m": [x[4] for x in v_cols],
    }, index=d.index)
    d = pd.concat([d, stage_df], axis=1)
    d["d_nav"] = d.v_nav - d.b_nav
    d["d_slice"] = d.v_slice - d.b_slice
    d["d_post"] = d.v_post - d.b_post
    d["d_edit_err"] = (d.v_edit_err - d.b_edit_err) * 100.0

    def ci_pct(frame, col):
        return [round(x, 2) for x in pct(np.array(task_mean_ci(frame, col)))]

    def ci_num(frame, col):
        return [round(x, 2) for x in task_mean_ci(frame, col)]

    out = {}

    # A. Topology vs Volume across levels (using unique variants on GPT subset)
    one = d[d.model == "gpt"]
    topo = {}
    for (sm, lv), g in one.groupby(["smell", "level"]):
        topo[f"{sm}|{lv}"] = dict(
            rad_files=float(g.rad_files.median()),
            rad_modules=float(g.rad_modules.median()),
            rad_distance=round(float(g.rad_distance.median()), 2),
            patch_files=float(g.injection_files.median()),
            added_lines=float(g.injection_added.median()),
            cf_added=float(g.cf_added.median()),
            entangled_share=round(float(g.entangled.mean()), 3),
            tcc=round(float(g.tcc.median()), 4) if sm == "GC" else None,
            laa=round(float(g.laa.median()), 3) if sm == "FE" else None,
            cc=float(g.cc.median()) if sm == "LM" else None,
            depth=float(g.depth.median()) if sm == "LM" else None,
        )
    for lv, g in one.groupby("level"):
        topo[f"ALL|{lv}"] = dict(
            rad_files=float(g.rad_files.median()),
            rad_modules=float(g.rad_modules.median()),
            rad_distance=round(float(g.rad_distance.median()), 2),
            added_lines=float(g.injection_added.median()),
            cf_added=float(g.cf_added.median()),
        )
    out["topology_by_level"] = topo

    # B. Universal control-flow branch complexity bins across all 7,223 pairs
    bins = [-1, 15, 45, 150, 10000]
    blabs = ["≤15", "16–45", "46–150", ">150"]
    d["cf_bin"] = pd.cut(d.cf_added, bins, labels=blabs)
    cf_res = []
    for m in MODELS:
        gm = d[d.model == m]
        for lb in blabs:
            gb = gm[gm.cf_bin == lb]
            cf_res.append(dict(
                model=m, bin=lb, pairs=len(gb), tasks=int(gb.task.nunique()),
                tokens=ci_pct(gb, "dtok"), steps=ci_pct(gb, "dstep"),
            ))
    out["branch_bins"] = cf_res

    # LM nesting depth & CC bins
    lm = d[d.smell == "LM"].copy()
    lm["depth_grp"] = pd.cut(lm.depth, [0, 4, 6, 10], labels=["3–4层", "5–6层", "7–8层"])
    out["lm_depth"] = {
        f"{m}|{dg}": dict(n=len(g), tokens=ci_pct(g, "dtok"), steps=ci_pct(g, "dstep"))
        for (m, dg), g in lm.groupby(["model", "depth_grp"], observed=True)
    }

    # C. Four trajectory stages
    stages = {}
    for m in MODELS:
        gm = d[d.model == m]
        for sm in SMELLS + ["ALL"]:
            gs = gm if sm == "ALL" else gm[gm.smell == sm]
            valid = gs.dropna(subset=["d_nav", "d_slice", "d_post"])
            stages[f"{m}|{sm}"] = dict(
                n=len(valid),
                nav_steps=ci_num(valid, "d_nav"),
                slice_steps=ci_num(valid, "d_slice"),
                post_steps=ci_num(valid, "d_post"),
                base_slice_mean=round(float(valid.b_slice.mean()), 2),
                smell_slice_mean=round(float(valid.v_slice.mean()), 2),
                edit_err_base=round(100 * float(gs.b_edit_err.mean()), 2),
                edit_err_smell=round(100 * float(gs.v_edit_err.mean()), 2),
                edit_err_diff_pp=ci_num(gs, "d_edit_err"),
                grep_match_ratio=round(float((gs.v_grep_m.sum() + 1) / (gs.b_grep_m.sum() + 1)), 3),
            )
    out["four_stages"] = stages

    # D. Fault-site direct entanglement / separation (entangled=1 vs 0)
    ent_res = {}
    for m in MODELS:
        gm = d[d.model == m]
        for sm in SMELLS + ["ALL"]:
            gs = gm if sm == "ALL" else gm[gm.smell == sm]
            for ent in (0, 1):
                ge = gs[gs.entangled == ent]
                ent_res[f"{m}|{sm}|{ent}"] = dict(
                    pairs=len(ge), tasks=int(ge.task.nunique()),
                    tokens=ci_pct(ge, "dtok"), steps=ci_pct(ge, "dstep"),
                )
            t0 = gs[gs.entangled == 0].groupby(["task", "repo"], as_index=False)["dtok"].mean()
            t1 = gs[gs.entangled == 1].groupby(["task", "repo"], as_index=False)["dtok"].mean()
            both = t0.merge(t1, on=["task", "repo"], suffixes=("_0", "_1"))
            if len(both) >= 10:
                ent_res[f"{m}|{sm}|within_task_diff"] = dict(
                    tasks=len(both),
                    tokens=[round(x, 2) for x in pct(np.array(cluster_boot(both.dtok_1 - both.dtok_0, both.repo)))],
                )
    out["fault_entanglement"] = ent_res

    # E. Controlled-variable & read-saturation check across S0 / S1 / S2
    cv = {"target_consistency": {}, "read_saturation": {}}
    for sm in SMELLS:
        sub = one[one.smell == sm]
        piv_t = sub.pivot(index="task", columns="level", values="target").dropna()
        piv_u = sub.pivot(index="task", columns="level", values="target_unit").dropna()
        cv["target_consistency"][sm] = dict(
            common_tasks=len(piv_t),
            same_file_pct=round(float(((piv_t.S0 == piv_t.S1) & (piv_t.S1 == piv_t.S2)).mean() * 100), 1),
            same_unit_pct=round(float(((piv_u.S0 == piv_u.S1) & (piv_u.S1 == piv_u.S2)).mean() * 100), 1),
        )
    for (m, sm, lv), g in d.groupby(["model", "smell", "level"]):
        cv["read_saturation"][f"{m}|{sm}|{lv}"] = dict(
            e4_pct=round(float((g.exposure == "E4").mean() * 100), 1),
            added_lines_med=float(g.injection_added.median()),
            base_chars_med=float(g.b_touched_chars.median()),
            var_chars_med=float(g.v_touched_chars.median()),
            delta_chars_med=float((g.v_touched_chars - g.b_touched_chars).median()),
            reads_mean=round(float(g.v_touched_reads.mean()), 2),
        )
    out["controlled_variables"] = cv

    # F. Production-file span curves (all smells, within FE/LM, and censored static RAD) + within-task horse race
    import statsmodels.formula.api as smf

    ibins, ilabs = [0, 1, 2, 5, 100], ["1 个文件", "2 个文件", "3–5 个文件", "≥6 个文件"]
    d["if_bin"] = pd.cut(d.injection_files, ibins, labels=ilabs)
    fcurves = {"all_smells": [], "fe_by_files": [], "lm_by_files": [], "rad_censored": [],
               "rad_below_3_count": int((one.rad_files < 3).sum())}
    for m in MODELS:
        gm = d[d.model == m]
        for lb in ilabs:
            gb = gm[gm.if_bin == lb]
            fcurves["all_smells"].append(dict(
                model=m, bin=lb, pairs=len(gb), tasks=int(gb.task.nunique()),
                tokens=ci_pct(gb, "dtok"), steps=ci_pct(gb, "dstep"),
                reads_mean=round(float(gb.v_touched_reads.mean()), 2),
            ))
        for sm_key, sm_code in [("fe_by_files", "FE"), ("lm_by_files", "LM")]:
            gs = gm[gm.smell == sm_code].copy()
            gs["fb3"] = pd.cut(gs.injection_files, [0, 1, 2, 100], labels=["1 个文件", "2 个文件", "≥3 个文件"])
            for lb3 in ["1 个文件", "2 个文件", "≥3 个文件"]:
                gb = gs[gs.fb3 == lb3]
                fcurves[sm_key].append(dict(
                    model=m, bin=lb3, pairs=len(gb), tasks=int(gb.task.nunique()),
                    tokens=ci_pct(gb, "dtok"), steps=ci_pct(gb, "dstep"),
                ))
        gr = gm.dropna(subset=["rad_files"]).copy()
        gr["rb"] = pd.cut(gr.rad_files, [0, 3, 5, 8, 100], labels=["3 个文件", "4–5 个文件", "6–8 个文件", "≥9 个文件"])
        for rlb in ["3 个文件", "4–5 个文件", "6–8 个文件", "≥9 个文件"]:
            gb = gr[gr.rb == rlb]
            fcurves["rad_censored"].append(dict(
                model=m, bin=rlb, pairs=len(gb), tokens=ci_pct(gb, "dtok"),
            ))
    out["file_span_curves"] = fcurves

    d["lv_num"] = d.level.map({"S0": 0.0, "S1": 1.0, "S2": 2.0})
    hr = {}
    for m in MODELS:
        gm = d[d.model == m].dropna(subset=["dtok", "injection_files", "cf_added", "lv_num", "entangled"]).copy()
        for col, expr in [
            ("y", gm.dtok),
            ("lv", gm.lv_num),
            ("files", np.log2(gm.injection_files)),
            ("cf", np.log2(gm.cf_added + 1.0)),
            ("ent", gm.entangled.astype(float)),
        ]:
            gm[col] = expr - expr.groupby(gm.task).transform("mean")
        for col in ["lv", "files", "cf", "ent"]:
            gm[col + "_z"] = gm[col] / gm[col].std()
        res_m = smf.ols("y ~ lv_z + files_z + cf_z + ent_z - 1", data=gm).fit(
            cov_type="cluster", cov_kwds={"groups": gm.repo}
        )
        hr[m] = {}
        for col in ["lv", "files", "cf", "ent"]:
            res_u = smf.ols(f"y ~ {col}_z - 1", data=gm).fit(cov_type="cluster", cov_kwds={"groups": gm.repo})
            k = col + "_z"
            ci_m = res_m.conf_int().loc[k]
            hr[m][col] = dict(
                uni_pct=round(float(pct(res_u.params.iloc[0])), 2),
                uni_p=round(float(res_u.pvalues.iloc[0]), 4),
                multi_pct=round(float(pct(res_m.params[k])), 2),
                multi_ci=[round(float(pct(ci_m.iloc[0])), 2), round(float(pct(ci_m.iloc[1])), 2)],
                multi_p=round(float(res_m.pvalues[k]), 4),
            )
    out["within_task_horserace"] = hr
    return out
