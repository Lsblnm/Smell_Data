# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.2.6", "pandas==2.2.3", "scipy==1.15.3", "matplotlib==3.10.3", "reportlab==4.4.1", "pdfrw==0.4"]
# ///
"""Reproduce the tables and figures with: uv run --python 3.12 study.py"""

from hashlib import sha256
import json

import numpy as np
import pandas as pd
from scipy.stats import binomtest, spearmanr

from inference import KNOWN, cluster_interval
from measure import MODELS, OUT, collect


def percent_ratio(log_values):
    return (100 * np.expm1(log_values)).tolist()


def task_means(frame, columns):
    return frame.groupby(["task", "repo"], as_index=False)[list(columns)].mean()


def ratios(frame):
    f = frame.copy()
    for k in (
        "tokens",
        "seconds",
        "steps",
        "result_chars",
        "inspect_chars",
        "inspects",
        "calls",
        "touched_chars",
        "touched_reads",
        "output",
        "reasoning",
        "cache_read",
    ):
        offset = 0 if k in ("tokens", "seconds", "steps") else 1
        f["log_" + k] = np.log((f["v_" + k] + offset) / (f["b_" + k] + offset))
    f["log_per_step"] = f.log_tokens - f.log_steps
    f["log_sec_step"] = f.log_seconds - f.log_steps
    for k in (
        "calls",
        "inspects",
        "test_calls",
        "tool_error",
        "result_chars",
        "inspect_chars",
        "touched_reads",
        "touched_chars",
        "touched_distinct",
        "touched_revisits",
        "structured_edits",
    ):
        f["diff_" + k] = f["v_" + k] - f["b_" + k]
    f["diff_repeated_target"] = (f.v_touched_reads >= 2).astype(int) - (f.b_touched_reads >= 2).astype(
        int
    )
    f["diff_touched_any"] = (f.v_touched_reads > 0).astype(int) - (f.b_touched_reads > 0).astype(int)
    f["log_nocache"] = np.log((f.v_tokens - f.v_cache_read) / (f.b_tokens - f.b_cache_read))
    return f


def aggregate(f):
    columns = [c for c in f if c.startswith(("log_", "diff_"))]
    a = task_means(f, columns)
    result = {"pairs": len(f), "tasks": len(a), "repos": a.repo.nunique()}
    for k in columns:
        estimate = cluster_interval(a[k], a.repo)
        result[k] = percent_ratio(estimate) if k.startswith("log_") else estimate
    return result


def paired_cost_cells(f):
    rows = []
    for (model, smell, level), g in f.groupby(["model", "smell", "level"], sort=False):
        row = dict(model=model, smell=smell, level=level, n=len(g), repos=g.repo.nunique())
        for k in ("tokens", "seconds"):
            ratios_ = g["v_" + k].to_numpy() / g["b_" + k].to_numpy()
            ratio, low, high = cluster_interval(ratios_, g.repo, "median")
            row.update(
                {
                    k + "_ratio": ratio,
                    k + "_lo": low,
                    k + "_hi": high,
                    k + "_median_diff": float(np.median(g["v_" + k] - g["b_" + k])),
                    k + "_higher": float(np.mean(ratios_ > 1)),
                }
            )
        rows.append(row)
    return rows


def outcomes(frame):
    gpt = frame[(frame.model == "gpt") & (frame.level != "S1")].copy()
    gpt["base_pass"] = (gpt.b_grade == "resolved").astype(int)
    gpt["variant_pass"] = (gpt.v_grade == "resolved").astype(int)
    gpt["diff"] = gpt.variant_pass - gpt.base_pass
    gpt["judged"] = gpt.b_grade.isin(KNOWN) & gpt.v_grade.isin(KNOWN)
    rows = []
    for (smell, level), g in gpt.groupby(["smell", "level"], sort=False):
        a = g[g.judged]
        gain, loss = int((a["diff"] > 0).sum()), int((a["diff"] < 0).sum())
        est, lo, hi = cluster_interval(a["diff"], a.repo)
        # Treat every ID without a binary verdict as unknown, including empty patches.
        lower = (g["diff"] - (~g.b_grade.isin(KNOWN)).astype(int)).mean()
        upper = (g["diff"] + (~g.v_grade.isin(KNOWN)).astype(int)).mean()
        rows.append(
            dict(
                smell=smell,
                level=level,
                intended=len(g),
                n=len(a),
                base_pass=int(a.base_pass.sum()),
                variant_pass=int(a.variant_pass.sum()),
                gain=gain,
                loss=loss,
                pp=100 * est,
                lo=100 * lo,
                hi=100 * hi,
                p=binomtest(gain, gain + loss).pvalue if gain + loss else 1,
                base_known=int(g.b_grade.isin(KNOWN).sum()),
                variant_known=int(g.v_grade.isin(KNOWN).sum()),
                base_all_pass=int(g.base_pass.sum()),
                variant_all_pass=int(g.variant_pass.sum()),
                bound_lo=100 * lower,
                bound_hi=100 * upper,
            )
        )
    order = sorted(range(len(rows)), key=lambda i: rows[i]["p"])
    high = 0.0
    for rank, index in enumerate(order):
        high = max(high, min(1.0, (len(rows) - rank) * rows[index]["p"]))
        rows[index]["p_holm"] = high
    a = task_means(gpt[gpt.judged], ["diff"])
    pooled = dict(
        tasks=len(a),
        pairs=int(gpt.judged.sum()),
        same_edit_flips=int((gpt.judged & gpt["diff"].ne(0) & gpt.same_changed_lines.eq(1)).sum()),
        pp=(100 * np.array(cluster_interval(a["diff"], a.repo))).tolist(),
    )
    return rows, pooled


def graded_effort(f):
    known = f[f.b_grade.isin(KNOWN) & f.v_grade.isin(KNOWN)]
    rows = {}
    for (base, variant), group in known.groupby(["b_grade", "v_grade"]):
        by_task = task_means(group, ["log_tokens", "log_seconds", "diff_touched_reads"])
        rows[base + "_to_" + variant] = dict(
            pairs=len(group),
            tasks=len(by_task),
            tokens=percent_ratio(cluster_interval(by_task.log_tokens, by_task.repo)),
            seconds=percent_ratio(cluster_interval(by_task.log_seconds, by_task.repo)),
            reads=cluster_interval(by_task.diff_touched_reads, by_task.repo),
        )
    return rows


def mechanism(g):
    equal = g[g.v_steps == g.b_steps]
    tracked = g[(g.b_preedit_calls >= 0) & (g.v_preedit_calls >= 0)]
    return dict(
        same_step_n=len(equal),
        same_step_median_pct=100 * np.expm1(equal.log_tokens.median()),
        step_spearman=spearmanr(g.log_steps, g.log_tokens).statistic,
        tool_text_spearman=spearmanr(g.log_result_chars, g.log_tokens).statistic,
        pct_earlier=100 * (g.v_first_ts < g.b_first_ts).mean(),
        median_days_earlier=(g.b_first_ts - g.v_first_ts).median() / 86400000,
        pct_same_first_context=100 * (g.v_first_context == g.b_first_context).mean(),
        median_first_context_diff=(g.v_first_context - g.b_first_context).median(),
        base_cache_share=100 * (g.b_cache_read / g.b_tokens).median(),
        variant_cache_share=100 * (g.v_cache_read / g.v_tokens).median(),
        reads_base=g.b_touched_reads.mean(),
        reads_variant=g.v_touched_reads.mean(),
        reread_base=100 * (g.b_touched_reads >= 2).mean(),
        reread_variant=100 * (g.v_touched_reads >= 2).mean(),
        same_file_repeat_base=100 * (g.b_touched_revisits > 0).mean(),
        same_file_repeat_variant=100 * (g.v_touched_revisits > 0).mean(),
        inspect_base=g.b_inspects.mean(),
        inspect_variant=g.v_inspects.mean(),
        test_base=g.b_test_calls.mean(),
        test_variant=g.v_test_calls.mean(),
        structured_first_edit_pairs=len(tracked),
        preedit_median_diff=(tracked.v_preedit_calls - tracked.b_preedit_calls).median(),
        delegate_pairs=int(((g.b_delegates + g.v_delegates) > 0).sum()),
        web_pairs=int(((g.b_web_calls + g.v_web_calls) > 0).sum()),
        more_tokens=100 * (g.log_tokens > 0).mean(),
        slower=100 * (g.log_seconds > 0).mean(),
        median_abs_pct=100 * np.expm1(np.abs(g.log_tokens).median()),
    )


def severity(g):
    key = ["smell", "task", "repo"]
    v = g[g.level == "S2"].merge(g[g.level == "S0"], on=key, suffixes=("_2", "_0"))
    rows = {}
    for label, a in [("all", v), *v.groupby("smell")]:
        endpoints = ["log_tokens", "log_seconds"]
        a = a.assign(**{k: a[k + "_2"] - a[k + "_0"] for k in endpoints})
        t = task_means(a, endpoints)
        rows[label] = dict(
            n=len(a),
            tasks=len(t),
            **{k: percent_ratio(cluster_interval(t[k], t.repo)) for k in endpoints},
        )
    return rows


def concurrent_variants(g):
    """Compare only treated variants of the same issue/level started within an hour."""
    keys = ["task", "repo", "level"]
    starts = g.pivot(index=keys, columns="smell", values="v_first_ts").dropna()
    selected = starts.index[(starts.max(axis=1) - starts.min(axis=1)) <= 3_600_000]
    values = g.pivot(index=keys, columns="smell", values="v_tokens").loc[selected]
    comparisons = {}
    for left, right in [("GC", "FE"), ("GC", "LM"), ("LM", "FE")]:
        diffs = np.log(values[left] / values[right]).rename("value").reset_index()
        by_task = task_means(diffs, ["value"])
        comparisons[left + "_vs_" + right] = percent_ratio(
            cluster_interval(by_task.value, by_task.repo)
        )
    return dict(
        task_levels=len(selected), tasks=len(selected.unique(level="task")), contrasts=comparisons
    )


def baselines(repeat, g):
    same = repeat[(repeat.b_usable == 1) & (repeat.v_usable == 1)]
    graded = repeat[repeat.left_grade.isin(KNOWN) & repeat.right_grade.isin(KNOWN)]
    matched = g[g.task.isin(same.task)]
    return dict(
        recorded=len(repeat),
        n=len(same),
        judged=len(graded),
        flips=int((graded.left_grade != graded.right_grade).sum()),
        treated_on_repeat_tasks=len(matched),
        **{
            k + "_abs_pct": 100 * np.expm1(np.abs(np.log(same["v_" + k] / same["b_" + k])).median())
            for k in ("tokens", "seconds")
        },
        treated_token_abs_pct=100 * np.expm1(np.abs(matched.log_tokens).median()),
        repeat_twofold_pct=100 * (np.abs(np.log(same.v_tokens / same.b_tokens)) >= np.log(2)).mean(),
    )


def save(pairs, repeats, inventory):
    from figures import render
    from continuous_figures import render_continuous
    from dimensions import analyze

    frame = pd.DataFrame(pairs)
    assert not frame.duplicated(["model", "smell", "level", "task"]).any()
    usable = frame.b_usable.eq(1) & frame.v_usable.eq(1) & frame.prompt_matched.eq(1)
    f = ratios(frame[usable])
    r = pd.DataFrame(repeats)
    cost = paired_cost_cells(f)
    success, pooled = outcomes(frame)
    models = {}
    all_repos = sorted(
        frame.repo.unique(), key=lambda s: sha256(("smell-study/" + s).encode()).hexdigest()
    )
    holdout = all_repos[::3]
    common = set(frame.groupby("task").smell.nunique().loc[lambda x: x == 3].index)
    for m in MODELS:
        g = f[f.model == m]
        models[m] = dict(
            overall=aggregate(g),
            behavior=mechanism(g),
            concurrent=concurrent_variants(g),
            severity=severity(g),
            repeats=baselines(r[r.model == m], g),
        )
        models[m]["by_smell"] = {}
        for smell, group in g.groupby("smell"):
            per_smell = aggregate(group)
            models[m]["by_smell"][smell] = {
                k: per_smell[k]
                for k in (
                    "pairs",
                    "tasks",
                    "log_tokens",
                    "log_steps",
                    "log_per_step",
                    "diff_touched_reads",
                    "diff_touched_distinct",
                    "diff_touched_revisits",
                    "diff_touched_chars",
                )
            }
        for label, subset in [
            ("discovery", g[~g.repo.isin(holdout)]),
            ("holdout", g[g.repo.isin(holdout)]),
            ("shared_tasks", g[g.task.isin(common)]),
            ("no_delegation", g[(g.b_delegates + g.v_delegates) == 0]),
            ("no_reference_flag", g[(g.b_reference_calls + g.v_reference_calls) == 0]),
            ("strict_step_counts", g[(g.b_orphan_start == 0) & (g.v_orphan_start == 0)]),
        ]:
            ag = aggregate(subset)
            models[m][label] = {
                k: ag[k]
                for k in (
                    "pairs",
                    "tasks",
                    "repos",
                    "log_tokens",
                    "log_seconds",
                    "log_steps",
                    "log_per_step",
                    "diff_touched_reads",
                )
            }
    report = dict(
        inventory=inventory,
        holdout_repos=holdout,
        cost_cells=cost,
        success_cells=success,
        pooled_success=pooled,
        graded_effort=graded_effort(f),
        models=models,
    )
    resources, graded, bins, continuous = analyze(frame)
    continuous["localization_cases"] = render_continuous(frame, resources, graded, bins)
    report["continuous"] = continuous
    frame.to_csv(OUT / "paired_tasks.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    with (OUT / "estimates.json").open("w") as handle:
        json.dump(
            report, handle, ensure_ascii=False, indent=2, default=lambda x: x.item(), allow_nan=False
        )
        handle.write("\n")
    render(f, success)
    print(
        f"{len(frame)} intended contrasts, {len(f)} usable resource pairs, {len(success)} graded contrasts."
    )


if __name__ == "__main__":
    save(*collect())
