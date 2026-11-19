"""Continuous dose response. Effects are within-issue associations, with repository-clustered errors."""

from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import t as student

from measure import MODELS, OUT
from static_metrics import METRICS, RAD
from inference import KNOWN, cluster_interval


LABEL = {
    "loc": "有效代码行数 LOC",
    "wmc": "类方法复杂度之和 WMC",
    "tcc": "类内聚度 TCC",
    "cc": "方法圈复杂度 CC",
    "depth": "最大嵌套层数",
    "atfd": "外部属性数 ATFD",
    "laa": "本类属性占比 LAA",
    "fdp": "外部数据提供类数 FDP",
    "rad_files": "相关文件数",
    "rad_modules": "相关模块数",
    "rad_distance": "平均结构距离",
    "target_file_delta": "目标文件净增物理行",
}
UNITS = {
    k: ("×2" if k in ("loc", "wmc", "cc") else "+0.10" if k in ("laa", "tcc") else "+1") for k in LABEL
}
UNITS["target_file_delta"] = "+100"


def transform(values, key):
    if key in ("loc", "wmc", "cc"):
        return np.log2(values)
    if key in ("laa", "tcc"):
        return values * 10
    return values / 100 if key == "target_file_delta" else values


def prepare(frame):
    f = frame[frame.b_usable.eq(1) & frame.v_usable.eq(1) & frame.prompt_matched.eq(1)].copy()
    f["tokens"] = np.log(f.v_tokens / f.b_tokens)
    f["seconds"] = np.log(f.v_seconds / f.b_seconds)
    q = frame[(frame.model == "gpt") & frame.v_grade.isin(KNOWN) & frame.b_grade.isin(KNOWN)].copy()
    q["success"] = (q.v_grade == "resolved").astype(float) - (q.b_grade == "resolved").astype(float)
    return f, q


def three_models(f):
    keys = ["task", "smell", "level"]
    counts = f.groupby(keys).model.transform("size")
    f = f[counts == len(MODELS)]
    avg = f.groupby(keys, as_index=False)[["tokens", "seconds"]].mean()
    return (
        f[f.model == "gpt"]
        .drop(columns=["tokens", "seconds"])
        .merge(avg, on=keys, validate="one_to_one")
    )


def fixed_effects(f, columns, outcome, spec):
    same_target = spec == "same_unit"
    identifiers = ["task", "target", "target_unit"] if same_target else ["task"]
    d = f.dropna(subset=columns + [outcome]).copy()
    d = d[d.groupby(identifiers)[outcome].transform("size") >= 2].reset_index(drop=True)
    groups = d.groupby(identifiers, sort=False).ngroup().to_numpy()
    x = pd.DataFrame({c: transform(d[c], c) for c in columns})
    if spec == "within_level":
        x = pd.concat([x, pd.get_dummies(d.level, drop_first=True, dtype=float)], axis=1)
    x = (x - x.groupby(groups).transform("mean")).to_numpy(dtype=float)
    y = (d[outcome] - d[outcome].groupby(groups).transform("mean")).to_numpy()
    beta, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    if rank != x.shape[1]:
        raise ValueError(f"Underidentified specification: {spec}, {columns}, {outcome}")
    res = y - np.einsum("ij,j->i", x, beta)
    repos, code = np.unique(d.repo, return_inverse=True)
    n = len(x)
    k = rank + len(np.unique(groups))
    clusters = len(repos)
    scores = np.zeros((clusters, len(beta)))
    np.add.at(scores, code, x * res[:, None])
    # The CR1 finite-sample correction counts the absorbed issue intercepts.
    bread = np.linalg.inv(np.einsum("ni,nj->ij", x, x))
    influences = np.einsum("gi,ij->gj", scores, bread)
    if not np.isfinite(influences).all():
        raise ValueError("Nonfinite cluster influence")
    se = np.sqrt(np.square(influences).sum(axis=0) * (clusters / (clusters - 1)) * ((n - 1) / (n - k)))
    crit = student.ppf(0.975, clusters - 1)
    vifs = np.diag(bread) * np.square(x).sum(axis=0)
    rows = []
    for i, m in enumerate(columns):
        interval = np.array([beta[i], beta[i] - crit * se[i], beta[i] + crit * se[i]])
        vals = 100 * interval if outcome == "success" else 100 * np.expm1(interval)
        rows.append(
            dict(
                metric=m,
                unit=UNITS[m],
                effect=vals[0],
                lo=vals[1],
                hi=vals[2],
                p=2 * student.sf(abs(beta[i] / se[i]), clusters - 1) if se[i] else float(beta[i] == 0),
                vif=vifs[i],
                n=n,
                tasks=d.task.nunique(),
                repos=clusters,
            )
        )
    return rows


def slopes(frame, graded, pooled):
    rows = []
    for smell, local in METRICS.items():
        factors = [*local, *RAD]
        datasets = [
            ("three", pooled),
            *((m, frame[frame.model == m]) for m in MODELS),
            ("graded_gpt", graded),
        ]
        for name, full in datasets:
            sub = full[full.smell == smell]
            for outcome in ["success"] if name == "graded_gpt" else ["tokens", "seconds"]:
                for spec in ("single", "joint", "within_level", "same_unit"):
                    lists = (
                        ([c] for c in [*factors, "target_file_delta"])
                        if spec == "single"
                        else [factors]
                    )
                    for cols in lists:
                        for result in fixed_effects(sub, cols, outcome, spec):
                            rows.append(
                                dict(smell=smell, model=name, outcome=outcome, spec=spec, **result)
                            )
    results = pd.DataFrame(rows)
    results["p_holm"] = np.nan
    # Each primary family has 18 coefficients, six per smell.
    for outcome in ("tokens", "seconds", "success"):
        subset = results[
            (results.outcome == outcome)
            & results.model.isin(["three", "graded_gpt"])
            & (results.spec == "joint")
        ].sort_values("p")
        results.loc[subset.index, "p_holm"] = np.minimum(
            1, np.maximum.accumulate(subset.p.to_numpy() * np.arange(len(subset), 0, -1))
        )
    return results


def fixed_bins(series):
    values = series.dropna().to_numpy()
    unique = np.unique(values)
    if len(unique) <= 12:
        return unique[:-1]
    return np.unique(np.quantile(values, np.arange(1, 7) / 7, method="inverted_cdf"))


def bin_points(f, metric, outcome, cuts):
    d = f.dropna(subset=[metric, outcome]).copy()
    d["bin"] = np.searchsorted(cuts, d[metric].to_numpy(), side="left")
    rows = []
    for _, b in d.groupby("bin"):
        a = b.groupby(["task", "repo"], as_index=False)[outcome].mean()
        if len(a) < 15 or a.repo.nunique() < 5:
            continue
        ci = np.array(cluster_interval(a[outcome], a.repo))
        vals = 100 * ci if outcome == "success" else 100 * np.expm1(ci)
        rows.append(
            dict(
                x=float(b[metric].median()),
                min=float(b[metric].min()),
                max=float(b[metric].max()),
                estimate=vals[0],
                lo=vals[1],
                hi=vals[2],
                n=len(b),
                tasks=len(a),
                repos=a.repo.nunique(),
            )
        )
    return rows


def support_audit(meta):
    out = {}
    for smell, local in METRICS.items():
        m = meta[meta.smell == smell]
        factors = [*local, *RAD]
        within = m[list(local)] - m.groupby("task")[list(local)].transform("mean")
        comparisons = {k: 0 for k in local}
        only_rad = {k: 0 for k in RAD}
        fixed_unit = 0
        for _, group in m.groupby("task"):
            for a, b in combinations(group.to_dict("records"), 2):
                if (a["target"], a["target_unit"]) != (b["target"], b["target_unit"]):
                    continue
                fixed_unit += 1
                for k in local:
                    if a[k] != b[k] and all(a[j] == b[j] for j in local if j != k):
                        comparisons[k] += 1
                for k in RAD:
                    if (
                        all(pd.notna(a[j]) and pd.notna(b[j]) for j in RAD)
                        and a[k] != b[k]
                        and all(a[j] == b[j] for j in factors if j != k)
                    ):
                        only_rad[k] += 1
        out[smell] = dict(
            variants=len(m),
            fixed_unit_pairs=fixed_unit,
            single_local=comparisons,
            single_rad_with_all_other_equal=only_rad,
            within_cor=within.corr().round(5).to_dict(),
            support={
                c: dict(
                    n=int(m[c].count()),
                    distinct=int(m[c].nunique()),
                    low=float(m[c].min()),
                    high=float(m[c].max()),
                )
                for c in factors
            },
            distance_at_floor=int(m.rad_distance.eq(2).sum()),
        )
    return out


def observed_mechanisms(f):
    rows = []
    for (smell, model), g in f.groupby(["smell", "model"]):
        for label, mask in [
            ("identical_first", g.same_first_request.eq(1)),
            ("default_first", g.same_open_request.eq(1)),
            ("fixed_first", g.same_bounded_request.eq(1)),
            ("cross_file", g.cross_file_move.eq(1)),
            ("target_read_both", g.b_target_windows.gt(0) & g.v_target_windows.gt(0)),
            ("hit_to_miss", g.b_first_window_hit.eq(1) & g.v_first_window_hit.eq(0)),
            ("hit_to_hit", g.b_first_window_hit.eq(1) & g.v_first_window_hit.eq(1)),
            ("miss_to_hit", g.b_first_window_hit.eq(0) & g.v_first_window_hit.eq(1)),
            ("miss_to_miss", g.b_first_window_hit.eq(0) & g.v_first_window_hit.eq(0)),
        ]:
            z = g[mask]
            if not len(z):
                continue
            a = z.groupby(["task", "repo"], as_index=False).tokens.mean()
            entry = dict(
                smell=smell,
                model=model,
                group=label,
                n=len(z),
                tasks=z.task.nunique(),
                repos=z.repo.nunique(),
                token_pct=100 * np.expm1(a.tokens.mean()),
            )
            if label in ("identical_first", "default_first", "fixed_first"):
                u = z[(z.b_first_target_chars > 0) & (z.v_first_target_chars > 0)]
                ctrl = u[u.b_comparison_chars.gt(0) & u.v_comparison_chars.gt(0)]
                entry.update(
                    paired_char_median_delta=float(
                        (u.v_first_target_chars - u.b_first_target_chars).median()
                    ),
                    paired_char_median_ratio=float(
                        (u.v_first_target_chars / u.b_first_target_chars).median()
                    ),
                    n_positive_chars=len(u),
                    with_unchanged_file=len(ctrl),
                )
                if u.repo.nunique() >= 5:
                    entry["char_ratio_ci"] = cluster_interval(
                        u.v_first_target_chars / u.b_first_target_chars, u.repo, "median"
                    )
                if len(ctrl):
                    entry.update(
                        control_source_ratio=float(
                            (ctrl.v_comparison_chars / ctrl.b_comparison_chars).median()
                        ),
                        same_subset_target_ratio=float(
                            (ctrl.v_first_target_chars / ctrl.b_first_target_chars).median()
                        ),
                        control_equal=int(ctrl.b_comparison_chars.eq(ctrl.v_comparison_chars).sum()),
                    )
            if label == "cross_file":
                entry.update(
                    base_both_pct=100 * z.b_both_owners.mean(),
                    variant_both_pct=100 * z.v_both_owners.mean(),
                )
            if label == "target_read_both":
                entry.update(
                    base_multi_pct=100 * z.b_target_offsets.gt(1).mean(),
                    variant_multi_pct=100 * z.v_target_offsets.gt(1).mean(),
                )
            rows.append(entry)
    return rows


def line_audit(f):
    results = {}
    flagged = set()
    for sm, group in f.groupby("smell"):
        keys = ["level", "task"]
        totals = (
            group[group.v_first_target_file_lines.notna()]
            .groupby(keys)
            .agg(file_lines=("v_first_target_file_lines", "max"), loc=("loc", "first"))
        )
        bad = totals[totals["loc"] > totals.file_lines]
        paired = group.dropna(subset=["v_first_target_file_lines", "b_first_target_file_lines"]).copy()
        paired["match"] = (paired.v_first_target_file_lines - paired.b_first_target_file_lines).eq(
            paired.target_file_delta
        )
        check = paired.groupby(keys)["match"].all()
        results[sm] = dict(
            observed=len(totals),
            reported_loc_over_file=len(bad),
            compared_deltas=len(check),
            all_observed_deltas_agree=int(check.sum()),
            flagged=[f"{level}/{task}" for level, task in bad.index],
        )
        flagged.update((sm, level, task) for level, task in bad.index)
    return results, flagged


def owner_comparison(pooled):
    subset = pooled[
        pooled.smell.eq("FE") & (pooled.cross_file_move.eq(1) | pooled.source.eq(pooled.target))
    ]
    matched = subset.groupby(["task", "repo", "cross_file_move"]).tokens.mean().unstack().dropna()
    delta = matched[1] - matched[0]
    return dict(
        tasks=len(matched),
        repos=matched.index.get_level_values("repo").nunique(),
        token_pct=(
            100 * np.expm1(cluster_interval(delta, matched.index.get_level_values("repo")))
        ).tolist(),
    )


def analyze(frame):
    f, g = prepare(frame)
    pooled = three_models(f)
    meta = frame.drop_duplicates(["smell", "level", "task"])
    effects = slopes(f, g, pooled)
    aud, flags = line_audit(f)
    gc = pooled[pooled.smell.eq("GC")]
    verified = gc.loc[[("GC", r.level, r.task) not in flags for r in gc.itertuples()]]
    audit_slope = fixed_effects(verified, [*METRICS["GC"], *RAD], "tokens", "joint")
    effects.to_csv(OUT / "metric-effects.csv", index=False, float_format="%.9g")
    bins = {}
    for smell, local in METRICS.items():
        for key in [*local, *RAD, "target_file_delta"]:
            cuts = fixed_bins(meta.loc[meta.smell.eq(smell), key])
            for model in MODELS:
                sub = f[f.smell.eq(smell) & f.model.eq(model)]
                for outcome in ("tokens", "seconds"):
                    bins[smell, model, key, outcome] = bin_points(sub, key, outcome, cuts)
            bins[smell, "gpt", key, "success"] = bin_points(g[g.smell.eq(smell)], key, "success", cuts)
    summary = dict(
        support=support_audit(meta),
        mechanisms=observed_mechanisms(f),
        common_variants=len(pooled),
        paired_owner_location=owner_comparison(pooled),
        line_audit=aud,
        gc_excluding_flagged=audit_slope,
        bins={"|".join(k): v for k, v in bins.items()},
    )
    return f, g, bins, summary
