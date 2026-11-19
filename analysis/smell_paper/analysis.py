"""Main analysis for the paper. Produces data/results.json and intermediate tables used by figures/report.

Run (from repo root):
    python analysis/smell_paper/parse_traces.py
    python analysis/smell_paper/analysis.py
    python analysis/smell_paper/figures.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats

from accounting import CATS, fit_rates, pair_accounting
from core import (DATA, KNOWN, LEVELS, MODELS, SMELLS, TRACES, cluster_boot, injection_paths, load_calls,
                  load_pairs, load_runs, pct, task_mean_ci)
from structural import compute_deep_structure

R = {}


def ci_pct(frame, col):
    return [round(x, 2) for x in pct(np.array(task_mean_ci(frame, col)))]


def ci_raw(frame, col, scale=1.0):
    return [round(scale * x, 3) for x in task_mean_ci(frame, col)]


def main():
    f = load_pairs()
    u = f[f.usable].copy()
    runs = load_runs()
    calls = load_calls()
    R["inventory"] = dict(pairs_intended=len(f), pairs_usable=len(u), tasks=int(f.task.nunique()),
                          repos=int(f.repo.nunique()), langs=int(f.lang.nunique()),
                          tasks_by_smell={s: int(f[f.smell == s].task.nunique()) for s in SMELLS},
                          runs=len(runs), calls=len(calls))

    # ---------- RQ1 overall ----------
    R["overall"] = {}
    for m in MODELS:
        g = u[u.model == m]
        R["overall"][m] = dict(pairs=len(g), tasks=int(g.task.nunique()),
                               tokens=ci_pct(g, "dtok"), seconds=ci_pct(g, "dsec"), steps=ci_pct(g, "dstep"),
                               per_step=ci_pct(g, "dper"), more_tokens_share=round(float((g.dtok > 0).mean()), 3),
                               base_tokens_median=float(g.drop_duplicates(["smell", "task"]).b_tokens.median()),
                               abs_delta_median=float((g.v_tokens - g.b_tokens).median()))

    # ---------- RQ2 dose cells ----------
    cells = []
    for (m, s, lv), g in u.groupby(["model", "smell", "level"]):
        cells.append(dict(model=m, smell=s, level=lv, n=len(g), tokens=ci_pct(g, "dtok"), steps=ci_pct(g, "dstep"),
                          seconds=ci_pct(g, "dsec"),
                          added_median=float(g.injection_added.median()),
                          target_delta_median=float(g.target_file_delta.median())))
    for (m, lv), g in u.groupby(["model", "level"]):
        cells.append(dict(model=m, smell="ALL", level=lv, n=len(g), tokens=ci_pct(g, "dtok"), steps=ci_pct(g, "dstep"),
                          seconds=ci_pct(g, "dsec"), added_median=float(g.injection_added.median()),
                          target_delta_median=float(g.target_file_delta.median())))
    R["dose_cells"] = cells

    # within-task escalation S2 vs S0, onset share, DiD LM-FE
    esc = {}
    for m in MODELS:
        g = u[u.model == m]
        piv = g.pivot_table(index=["task", "repo"], columns=["smell", "level"], values="dtok")
        esc[m] = {}
        for s in SMELLS + ["ALL"]:
            if s == "ALL":
                d0 = g[g.level == "S0"].groupby(["task", "repo", "smell"]).dtok.mean()
                d2 = g[g.level == "S2"].groupby(["task", "repo", "smell"]).dtok.mean()
                d = (d2 - d0).dropna().groupby(level=[0, 1]).mean().reset_index(name="d")
            else:
                d = (piv[(s, "S2")] - piv[(s, "S0")]).dropna().reset_index(name="d")
            e = [round(x, 2) for x in pct(np.array(cluster_boot(d.d, d.repo)))]
            s0 = g[(g.level == "S0") & ((g.smell == s) | (s == "ALL"))]
            s2 = g[(g.level == "S2") & ((g.smell == s) | (s == "ALL"))]
            a0, a2 = task_mean_ci(s0, "dtok")[0], task_mean_ci(s2, "dtok")[0]
            esc[m][s] = dict(s2_vs_s0=e, n=len(d), onset_share=round(float(a0 / a2), 3) if a2 > 0 else None)
        did = ((piv[("LM", "S2")] - piv[("LM", "S0")]) - (piv[("FE", "S2")] - piv[("FE", "S0")])).dropna().reset_index(name="d")
        esc[m]["did_LM_minus_FE"] = dict(pp=[round(100 * x, 2) for x in cluster_boot(did.d, did.repo)], n=len(did))
    R["escalation"] = esc

    # concurrent cross-smell contrasts (same batch, same task, same level)
    conc = {}
    for m in MODELS:
        g = u[u.model == m]
        v = g.pivot_table(index=["task", "repo", "level"], columns="smell", values="v_tokens").dropna()
        conc[m] = {}
        for a, b in [("GC", "FE"), ("GC", "LM"), ("LM", "FE")]:
            d = np.log(v[a] / v[b]).groupby(level=[0, 1]).mean().reset_index(name="d")
            conc[m][f"{a}_vs_{b}"] = [round(x, 2) for x in pct(np.array(cluster_boot(d.d, d.repo)))]
    R["concurrent_contrasts"] = conc

    # ---------- tail risk vs repeat noise ----------
    c = runs[runs.group.str.startswith("None")].copy()
    c = c[(c.status == "COMPLETED") & (c.end_reason == "stop")]
    rep = []
    for (m, t), g in c.groupby(["model", "task"]):
        vals = g.drop_duplicates("tokens_all")
        if len(vals) >= 2:
            rep.append(dict(model=m, task=t, repo=t.rsplit("-", 1)[0],
                            d=np.log(vals.iloc[1].tokens_all / vals.iloc[0].tokens_all)))
    rep = pd.DataFrame(rep)
    tail = {}
    for m in MODELS:
        rr = rep[rep.model == m]
        g = u[u.model == m]
        tail[m] = dict(noise_n=len(rr), noise_sd=round(float(rr.d.std()), 3), smell_sd=round(float(g.dtok.std()), 3),
                       noise_abs_median_pct=round(float(pct(np.median(np.abs(rr.d)))), 1))
        for thr in (1.5, 2.0):
            key = str(thr)
            ind = (np.abs(rr.d) >= np.log(thr)).astype(float) / 2
            tail[m]["noise_p" + key] = [round(100 * x, 1) for x in cluster_boot(ind, rr.repo)]
            for lv in LEVELS + ["ALL"]:
                x = g if lv == "ALL" else g[g.level == lv]
                x = x.assign(ind=(x.dtok >= np.log(thr)).astype(float))
                tail[m][f"{lv}_p{key}"] = ci_raw(x, "ind", 100)
    R["tail"] = tail

    # ---------- RQ3 accounting ----------
    rates = fit_rates(runs, calls)
    R["rates"] = rates
    acc = pair_accounting(u, runs, calls, rates)
    acc.to_csv(DATA / "accounting.csv.gz", index=False)
    accr = {}
    for keys, g in list(acc.groupby(["model", "smell"])) + [((m, "ALL"), acc[acc.model == m]) for m in MODELS]:
        base = g.b_total.sum()
        dt = (g.v_total - g.b_total).sum()
        accr["|".join(keys)] = dict(extra_over_base=round(100 * dt / base, 2),
                                    contrib_pp={k: round(100 * (g["v_" + k] - g["b_" + k]).sum() / base, 2) for k in CATS},
                                    base_share={k: round(100 * g["b_" + k].sum() / base, 2) for k in CATS})
    for (m, lv), g in acc.groupby(["model", "level"]):
        base = g.b_total.sum()
        accr[f"{m}|L{lv}"] = dict(extra_over_base=round(100 * (g.v_total - g.b_total).sum() / base, 2),
                                  contrib_pp={k: round(100 * (g["v_" + k] - g["b_" + k]).sum() / base, 2) for k in CATS})
    # per-category ratio, task-equal
    for k in ["inj_read", "other_read", "overhead", "gen_carried", "test_build"]:
        acc["r_" + k] = np.log((acc["v_" + k].clip(lower=0) + 5000) / (acc["b_" + k].clip(lower=0) + 5000))
    accr["category_ratio"] = {f"{m}|{lv}": {k: ci_pct(g, "r_" + k) for k in ["inj_read", "other_read"]}
                              for (m, lv), g in acc.groupby(["model", "level"])}
    # conservative lower bound: attribute to smell only injected content beyond a uniform drift proxied by other reading
    lb = {}
    for m in MODELS:
        g = acc[acc.model == m]
        base = g.b_total.sum()
        drift = max(0.0, (g.v_other_read - g.b_other_read).sum() / g.b_other_read.sum())
        lb[m] = dict(drift_proxy_pct=round(100 * drift, 2),
                     lower_bound_pct=round(100 * ((g.v_inj_read - g.b_inj_read).sum() - drift * g.b_inj_read.sum()) / base, 2),
                     naive_volume_pct=round(100 * (g.v_total - g.b_total).sum() / base, 2))
    R["accounting"] = accr
    R["lower_bound"] = lb

    # ---------- mechanisms ----------
    mech = {}
    # footprint
    rix = runs.set_index(["model", "group", "task"])
    u["b_ctx_last"] = [rix.ctx_last.get((m, "None-" + s, t)) for m, s, t in zip(u.model, u.smell, u.task)]
    u["v_ctx_last"] = [rix.ctx_last.get((m, f"{s}-{lv}", t)) for m, s, lv, t in zip(u.model, u.smell, u.level, u.task)]
    u["dctx"] = np.log(u.v_ctx_last / u.b_ctx_last)
    mech["footprint"] = {f"{m}|{s}|{lv}": ci_pct(g, "dctx") for (m, s, lv), g in u.groupby(["model", "smell", "level"])}
    # LM localization
    lm = u[u.smell == "LM"].copy()
    mech["lm_multi_window"] = {}
    for (m, lv), g in lm.groupby(["model", "level"]):
        mech["lm_multi_window"][f"{m}|{lv}"] = dict(base=round(float((g.b_target_offsets >= 2).mean()), 3),
                                                     smell=round(float((g.v_target_offsets >= 2).mean()), 3))
    bins = [0, 120, 160, 200, 240, 320, 500]
    lm["lb"] = pd.cut(lm["loc"], bins)
    lm["multi"] = (lm.v_target_offsets >= 2).astype(float)
    lm_bins = []
    for (m, b), g in lm.groupby(["model", "lb"], observed=True):
        lm_bins.append(dict(model=m, lo=b.left, hi=b.right, n=len(g), tokens=ci_pct(g, "dtok"), multi=ci_raw(g, "multi", 100),
                            base_multi=round(100 * float((g.b_target_offsets >= 2).mean()), 1)))
    mech["lm_bins"] = lm_bins
    thr = {}
    for m, g in lm.groupby("model"):
        thr[m] = dict(le160=ci_pct(g[g["loc"] <= 160], "dtok"), gt160=ci_pct(g[g["loc"] > 160], "dtok"),
                      n_le=int((g["loc"] <= 160).sum()), n_gt=int((g["loc"] > 160).sum()))
        s1 = g[g.level == "S1"]
        thr[m]["s1_le160"] = ci_pct(s1[s1["loc"] <= 160], "dtok")
        thr[m]["s1_gt160"] = ci_pct(s1[s1["loc"] > 160], "dtok")
        thr[m]["s1_n"] = [int((s1["loc"] <= 160).sum()), int((s1["loc"] > 160).sum())]
        thr[m]["multi_le160"] = round(100 * float((g[g["loc"] <= 160].v_target_offsets >= 2).mean()), 1)
        thr[m]["multi_gt160"] = round(100 * float((g[g["loc"] > 160].v_target_offsets >= 2).mean()), 1)
    mech["lm_threshold"] = thr
    gc = u[u.smell == "GC"].copy()
    gc["lb"] = pd.cut(gc["loc"], [0, 1500, 3000, 4000, 5000, 6000, 7100])
    mech["gc_bins"] = [dict(model=m, lo=b.left, hi=b.right, n=len(g), tokens=ci_pct(g, "dtok"))
                       for (m, b), g in gc.groupby(["model", "lb"], observed=True) if len(g) >= 20]
    fe = u[u.smell == "FE"].copy()
    fe["ab"] = fe.atfd.round()
    mech["fe_bins"] = [dict(model=m, atfd=float(a), n=len(g), tokens=ci_pct(g, "dtok"))
                       for (m, a), g in fe.groupby(["model", "ab"]) if len(g) >= 20]
    # FE both owners
    z = u[(u.smell == "FE") & u.b_both_owners.notna()]
    mech["fe_both_owners"] = {f"{m}|{lv}": dict(base=round(float(g.b_both_owners.mean()), 3), smell=round(float(g.v_both_owners.mean()), 3), n=len(g))
                              for (m, lv), g in z.groupby(["model", "level"])}
    # same open request chars ratio
    w = u[u.same_open_request == 1].copy()
    w["rc"] = np.log(w.v_first_target_chars / w.b_first_target_chars)
    mech["same_request_ratio"] = {f"{m}|{s}|{lv}": dict(n=len(g), median_x=round(float(np.exp(g.rc.median())), 2))
                                  for (m, s, lv), g in w.groupby(["model", "smell", "level"]) if len(g) >= 15}
    # phase split
    p = u.dropna(subset=["b_tokens_through_edit", "v_tokens_through_edit"]).copy()
    p["lpre"] = np.log(p.v_tokens_through_edit / p.b_tokens_through_edit)
    p["lpost"] = np.log((p.v_tokens - p.v_tokens_through_edit) / (p.b_tokens - p.b_tokens_through_edit))
    p = p.replace([np.inf, -np.inf], np.nan).dropna(subset=["lpre", "lpost"])
    mech["phase"] = {f"{m}|{s}": dict(pre=ci_pct(g, "lpre"), post=ci_pct(g, "lpost"), n=len(g))
                     for (m, s), g in p.groupby(["model", "smell"])}
    # reading style (baseline runs)
    bc = calls[calls.group.str.startswith("None")].drop_duplicates(["model", "task", "k", "chars", "tool"])
    style = {}
    for m, g in bc.groupby("model"):
        rd = g[g.tool == "read"]
        reading = g[g.cat.isin(["read", "search", "shell_inspect"])]
        style[m] = dict(read_calls=len(rd), bounded_share=round(float(rd.limit.notna().mean()), 3),
                        median_limit=float(rd.limit.median()),
                        shell_share_of_reading_chars=round(float(reading[reading.cat == "shell_inspect"].chars.sum() / reading.chars.sum()), 3),
                        read_share_of_reading_chars=round(float(reading[reading.cat == "read"].chars.sum() / reading.chars.sum()), 3))
    mech["reading_style"] = style
    R["mechanism"] = mech

    # ---------- validity: pre-contact negative control ----------
    idx = defaultdict(list)
    for cc in calls.itertuples():
        if isinstance(cc.attributed, str) and cc.attributed:
            idx[(cc.model, cc.group, cc.task)].append((cc.k, [i.rpartition("=")[0] for i in cc.attributed.split(";")]))
    rows = []
    for q in u.itertuples():
        paths = injection_paths(q.smell, q.level, q.task)
        row = dict(model=q.model, task=q.task, repo=q.repo, level=q.level)
        for side, grp in (("b", "None-" + q.smell), ("v", f"{q.smell}-{q.level}")):
            key = (q.model, grp, q.task)
            k = next((kk for kk, ps in idx.get(key, ()) if any(pp in paths for pp in ps)), None)
            r = rix.loc[key]
            ctx = np.fromstring(r.ctx_series, sep=" ")
            o = np.fromstring(r.out_series, sep=" ")
            du = np.fromstring(r.dur_series, sep=" ")
            if k is None:
                row[side + "_k"] = np.nan
                continue
            row.update({side + "_k": k, side + "_pre_tok": (ctx[:k + 1] + o[:k + 1]).sum(), side + "_pre_out": o[:k + 1].mean(),
                        side + "_pre_lat": du[:k + 1].mean(), side + "_post_out": o[k + 1:].mean() if len(o) > k + 1 else np.nan})
        rows.append(row)
    nc = pd.DataFrame(rows).dropna(subset=["b_k", "v_k"])
    nc["dk"] = np.log((nc.v_k + 1) / (nc.b_k + 1))
    nc["dpre"] = np.log(nc.v_pre_tok / nc.b_pre_tok)
    nc["dpreout"] = np.log(nc.v_pre_out.clip(lower=1) / nc.b_pre_out.clip(lower=1))
    nc["dpostout"] = np.log(nc.v_post_out.clip(lower=1) / nc.b_post_out.clip(lower=1))
    nc["dlat"] = np.log(nc.v_pre_lat.clip(lower=0.05) / nc.b_pre_lat.clip(lower=0.05))
    R["negative_control"] = {m: dict(n=len(g), steps_to_contact=ci_pct(g, "dk"), tokens_before_contact=ci_pct(g, "dpre"),
                                     out_per_step_before=ci_pct(g, "dpreout"),
                                     out_per_step_after=ci_pct(g.dropna(subset=["dpostout"]), "dpostout"),
                                     latency_per_step_before=ci_pct(g, "dlat"),
                                     total_tokens_same_subset=ci_pct(u[(u.model == m) & u.task.isin(g.task)], "dtok"))
                             for m, g in nc.groupby("model")}
    R["repeat_noise"] = {m: dict(n=int((rep.model == m).sum())) for m in MODELS}

    # ---------- RQ4 success (GPT) ----------
    g = f[(f.model == "gpt") & (f.level != "S1")].copy()
    g["bp"] = (g.b_grade == "resolved").astype(int)
    g["vp"] = (g.v_grade == "resolved").astype(int)
    g["judged"] = g.b_grade.isin(KNOWN) & g.v_grade.isin(KNOWN)
    k = g[g.judged].copy()
    k["diff"] = k.vp - k.bp
    succ = {"cells": []}
    for (s, lv), x in k.groupby(["smell", "level"]):
        gain, loss = int((x["diff"] > 0).sum()), int((x["diff"] < 0).sum())
        succ["cells"].append(dict(smell=s, level=lv, n=len(x), base_rate=round(100 * x.bp.mean(), 1), smell_rate=round(100 * x.vp.mean(), 1),
                                  gain=gain, loss=loss, pp=[round(100 * v, 2) for v in cluster_boot(x["diff"], x.repo)],
                                  p_mcnemar=round(float(stats.binomtest(gain, gain + loss).pvalue), 3)))
    for lv in ["S0", "S2"]:
        x = k[k.level == lv]
        t = x.groupby(["task", "repo"], as_index=False)["diff"].mean()
        succ[lv] = dict(n=len(x), base_rate=round(100 * x.bp.mean(), 1), smell_rate=round(100 * x.vp.mean(), 1),
                        pp=[round(100 * v, 2) for v in cluster_boot(t["diff"], t.repo)])
    t = k.groupby(["task", "repo"], as_index=False)["diff"].mean()
    succ["pooled"] = dict(pairs=len(k), tasks=len(t), pp=[round(100 * v, 2) for v in cluster_boot(t["diff"], t.repo)],
                          gains=int((k["diff"] > 0).sum()), losses=int((k["diff"] < 0).sum()),
                          same_patch_flips=int((k["diff"].ne(0) & k.same_changed_lines.eq(1)).sum()))
    # repeat flips (GPT, None dirs with different sessions)
    gr = {}
    for path in sorted((DATA.parents[2] / "bench_result").glob("*none-*.json")):
        raw = json.loads(path.read_bytes())
        gr[path.stem.rsplit("-", 1)[-1].upper()] = {t: s for s in ("resolved", "unresolved") for t in raw[s + "_ids"]}
    gpt_rep = rep[rep.model == "gpt"]
    flips = 0
    judged = 0
    cg = c[c.model == "gpt"]
    for t in gpt_rep.task:
        rr = cg[cg.task == t].drop_duplicates("tokens_all")
        smells_ = [grp.split("-")[1] for grp in rr.group]
        vals = [gr.get(s_, {}).get(t) for s_ in smells_[:2]]
        if all(vals):
            judged += 1
            flips += vals[0] != vals[1]
    succ["repeat_flip"] = dict(judged=judged, flips=flips)
    # failure mode: within task, failing vs passing variants
    gv = f[(f.model == "gpt") & f.usable & f.v_grade.isin(KNOWN)].copy()
    gv["vp"] = (gv.v_grade == "resolved").astype(int)
    rows = []
    for t, x in gv.groupby("task"):
        if x.vp.nunique() == 2:
            a, b = x[x.vp == 0], x[x.vp == 1]
            rows.append(dict(task=t, repo=x.repo.iloc[0], dtok=np.log(a.v_tokens).mean() - np.log(b.v_tokens).mean(),
                             dstep=np.log(a.v_steps).mean() - np.log(b.v_steps).mean(),
                             dtest=a.v_test_calls.mean() - b.v_test_calls.mean(),
                             dedit=a.v_structured_edits.mean() - b.v_structured_edits.mean()))
    fm = pd.DataFrame(rows)
    succ["failure_mode"] = dict(tasks=len(fm), tokens=[round(x, 2) for x in pct(np.array(cluster_boot(fm.dtok, fm.repo)))],
                                steps=[round(x, 2) for x in pct(np.array(cluster_boot(fm.dstep, fm.repo)))],
                                tests=[round(x, 2) for x in cluster_boot(fm.dtest, fm.repo)],
                                edits=[round(x, 2) for x in cluster_boot(fm.dedit, fm.repo)],
                                p_tokens=float(stats.wilcoxon(fm.dtok).pvalue), p_tests=float(stats.wilcoxon(fm.dtest).pvalue))
    kk = k.copy()
    kk = kk[kk.usable]
    succ["flip_vs_tokens"] = {str(fl): dict(n=int((kk["diff"] == fl).sum()), dtok_median=round(float(pct(kk[kk["diff"] == fl].dtok.median())), 1))
                              for fl in (-1, 0, 1)}
    succ["flip_vs_tokens"]["p_loss_vs_tie"] = float(stats.mannwhitneyu(kk[kk["diff"] == -1].dtok, kk[kk["diff"] == 0].dtok).pvalue)
    succ["flip_vs_tokens"]["p_gain_vs_tie"] = float(stats.mannwhitneyu(kk[kk["diff"] == 1].dtok, kk[kk["diff"] == 0].dtok).pvalue)
    R["success"] = succ

    # ---------- RQ5 moderators ----------
    base = u.drop_duplicates(["model", "smell", "task"]).groupby(["model", "task"]).b_tokens.first().apply(np.log).unstack(0)
    u["xdiff"] = [base[[o for o in MODELS if o != m]].loc[t].mean() for m, t in zip(u.model, u.task)]
    u["tercile"] = u.groupby("model")["xdiff"].transform(lambda s: pd.qcut(s, 3, labels=["易", "中", "难"]))
    u["dabs"] = u.v_tokens - u.b_tokens
    R["difficulty"] = {f"{m}|{q}": dict(rel=ci_pct(g, "dtok"), abs_median=float(g.dabs.median()), base_median=float(g.b_tokens.median()), n=len(g))
                       for (m, q), g in u.groupby(["model", "tercile"], observed=True)}
    R["exposure"] = {f"{m}|{e}": dict(n=len(g), tokens=ci_pct(g, "dtok")) for (m, e), g in u.groupby(["model", "exposure"])}
    R["language"] = {f"{m}|{l}": dict(n=len(g), tokens=ci_pct(g, "dtok")) for (m, l), g in u.groupby(["model", "lang"])}
    # absolute deltas by smell
    R["abs_delta"] = {f"{m}|{s}": dict(median=float(g.dabs.median()), mean=float(g.dabs.mean()), base_median=float(g.b_tokens.median()))
                      for (m, s), g in u.groupby(["model", "smell"])}
    R["deep_structure"] = compute_deep_structure(u, runs, calls)
    u.to_csv(DATA / "pairs_enriched.csv.gz", index=False)
    rep.to_csv(DATA / "repeats.csv.gz", index=False)
    with open(DATA / "results.json", "w") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1, default=lambda x: x.item() if hasattr(x, "item") else str(x))
    print("done", len(u), "pairs")


if __name__ == "__main__":
    main()
