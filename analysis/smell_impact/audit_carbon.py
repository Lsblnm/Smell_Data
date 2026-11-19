# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy==2.2.6", "pandas==2.2.3", "scipy==1.15.3"]
# ///
"""Recheck the presence, severity and window claims in smell_paper, without editing its artifacts."""

import json
import re

import numpy as np
import pandas as pd
from scipy.stats import t as student

from inference import DRAWS, SEED, cluster_interval
from measure import OUT, ROOT, SMELLS, TRACES
from static_metrics import MAY_WRITE


KEYWORDS = re.compile(r"\b(if|else|elif|elsif|for|foreach|while|switch|case|catch|except|match)\b")
BINS = ["≤15", "16–45", "46–150", ">150"]


def growth(values):
    return np.round(100 * np.expm1(values), 2).tolist()


def onset(group):
    task = group.groupby(["repo", "task", "level"]).log_ratio.mean().unstack()
    # Follow the author's marginal estimates, retaining all available smells for each task/level.
    by_repo = task.groupby(level="repo")[["S0", "S2"]]
    weights = np.random.default_rng(SEED).multinomial(
        len(by_repo), np.full(len(by_repo), 1 / len(by_repo)), size=DRAWS
    )
    avg = np.einsum("br,rk->bk", weights, by_repo.sum()) / np.einsum(
        "br,rk->bk", weights, by_repo.count()
    )
    point = task.S0.mean() / task.S2.mean()
    if (avg[:, 1] <= 0).any():
        raise ValueError(
            "A bootstrap denominator crossed zero; the share interval needs separate treatment."
        )
    share = avg[:, 0] / avg[:, 1]
    matched = group.pivot(index=["task", "repo", "smell"], columns="level", values="log_ratio")
    delta = (matched.S2 - matched.S0).dropna().groupby(level=["task", "repo"]).mean()
    return dict(
        more_token_pct=round(100 * (group.log_ratio > 0).mean(), 2),
        s0=growth(task.S0.mean()),
        s2=growth(task.S2.mean()),
        onset_log_share_pct=np.round(
            100 * np.r_[point, np.quantile(share, [0.025, 0.975])], 1
        ).tolist(),
        s2_vs_s0=growth(cluster_interval(delta, delta.index.get_level_values("repo"))),
    )


def patch_bins(meta, valid):
    records = []
    for row in meta.itertuples(index=False):
        path = ROOT / "smell-patch" / row.level / SMELLS[row.smell] / f"{row.task}-{row.smell}.patch"
        added = (
            line[1:]
            for line in path.read_text(errors="replace").splitlines()
            if line.startswith("+") and not line.startswith("+++ ")
        )
        count = sum(len(KEYWORDS.findall(line)) for line in added)
        records.append((row.smell, row.level, row.task, count))
    keys = ["smell", "level", "task"]
    features = pd.DataFrame(records, columns=[*keys, "keywords"])
    features["bin"] = pd.cut(features.keywords, [-1, 15, 45, 150, 10000], labels=BINS)
    assert features.bin.notna().all()
    data = valid.merge(features, on=keys, validate="many_to_one")

    def composition(d):
        return pd.crosstab(d.bin, d.smell).reindex(BINS).T.to_dict()

    curves = {}
    for (model, bin_name), sub in data.groupby(["model", "bin"], observed=True):
        curves.setdefault(model, {})[bin_name] = growth(sub.groupby("task").log_ratio.mean().mean())
    return dict(variants=composition(features), pairs=composition(data), curves_pct=curves)


def topology(meta):
    result = {}
    for smell, g in meta.groupby("smell"):
        cols = {}
        for col in ["rad_files", "rad_modules", "target"]:
            levels = g.pivot(index="task", columns="level", values=col)
            paired = levels[["S0", "S2"]].dropna()
            cols[col] = {"paired": len(paired), "s0_equals_s2": int(paired.S0.eq(paired.S2).sum())}
        result[smell] = cols
    return result


def middle_severity(valid):
    g = valid[valid.model.eq("glm") & valid.smell.eq("GC")]
    levels = g.pivot(index=["task", "repo"], columns="level", values="v_tokens")
    results = {}
    for left, right in (("S0", "S1"), ("S1", "S2"), ("S0", "S2")):
        delta = np.log(levels[right] / levels[left]).dropna()
        results[f"{left}_to_{right}"] = {
            "n": len(delta),
            "pct": growth(cluster_interval(delta, delta.index.get_level_values("repo"))),
        }
    return results


def tail_reads(valid):
    runs = valid[valid.model.eq("gpt") & valid.smell.eq("GC") & valid.level.eq("S2")]
    hits = 0
    early = 0
    for run in runs.itertuples():
        pre_edit = True
        path = TRACES / "gpt" / "GC-S2" / run.task / "trajectory.jsonl"
        with path.open("rb") as handle:
            for line in handle:
                event = json.loads(line)
                if event["type"] != "tool_use":
                    continue
                part = event["part"]
                tool = part["tool"]
                state = part.get("state", {})
                args = state.get("input", {})
                file = args.get("filePath") or ""
                if (
                    tool == "read"
                    and state.get("status") == "completed"
                    and (file == run.target or file.endswith("/" + run.target))
                ):
                    source = (
                        (state.get("output") or "").partition("<content>")[2].partition("</content>")[0]
                    )
                    if any(2000 <= int(n) <= 6500 for n in re.findall(r"^(\d+):", source, re.M)):
                        hits += 1
                        early += pre_edit
                        break
                if tool in ("edit", "write", "apply_patch", "multiedit") or (
                    tool == "bash" and MAY_WRITE.search(args.get("command") or "")
                ):
                    pre_edit = False
    return dict(runs=len(runs), any_returned_in_range=hits, before_detected_edit=early)


def threshold_sensitivity(valid):
    """Estimate a 160-line jump on top of smooth log-size change and level effects, within issue."""
    lm = valid[valid.model.eq("gpt") & valid.smell.eq("LM")].copy()
    lm = lm[lm.groupby("task").task.transform("size").ge(2)]
    x = pd.DataFrame({"size": np.log2(lm["loc"]), "jump": lm["loc"].gt(160).astype(float)})
    x = pd.concat([x, pd.get_dummies(lm.level, drop_first=True, dtype=float)], axis=1)
    x = (x - x.groupby(lm.task).transform("mean")).to_numpy()
    y = (lm.log_ratio - lm.groupby("task").log_ratio.transform("mean")).to_numpy()
    beta, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    assert rank == x.shape[1]
    residual = y - np.einsum("ij,j->i", x, beta)
    repo, code = np.unique(lm.repo, return_inverse=True)
    scores = np.zeros((len(repo), rank))
    np.add.at(scores, code, x * residual[:, None])
    inv = np.linalg.inv(np.einsum("ki,kj->ij", x, x))
    influence = np.einsum("gi,ij->gj", scores, inv)[:, 1]
    correction = len(repo) / (len(repo) - 1) * (len(y) - 1) / (len(y) - rank - lm.task.nunique())
    half = student.ppf(0.975, len(repo) - 1) * np.sqrt(correction * np.sum(influence**2))
    return dict(
        pairs=len(lm),
        tasks=lm.task.nunique(),
        jump_pct=growth(np.array([beta[1], beta[1] - half, beta[1] + half])),
    )


def direct_success():
    records = []
    for s in SMELLS:
        states = {}
        for level in ["S0", "S2"]:
            (path,) = (ROOT / "bench_result").glob(f"*-gpt-{s.lower()}-{level.lower()}.json")
            report = json.loads(path.read_bytes())
            states[level] = {
                i: k == "resolved" for k in ("resolved", "unresolved") for i in report[k + "_ids"]
            }
        for task in sorted(states["S0"].keys() & states["S2"].keys()):
            records.append(
                (task, task.rsplit("-", 1)[0], int(states["S2"][task]) - int(states["S0"][task]))
            )
    obs = pd.DataFrame(records, columns=["task", "repo", "delta"])
    task = obs.groupby(["task", "repo"], as_index=False).delta.mean()
    return dict(
        pairs=len(obs),
        tasks=len(task),
        pp=np.round(100 * np.array(cluster_interval(task.delta, task.repo)), 2).tolist(),
    )


if __name__ == "__main__":
    data = pd.read_csv(OUT / "paired_tasks.csv.gz")
    valid = data[data.b_usable.eq(1) & data.v_usable.eq(1) & data.prompt_matched.eq(1)].copy()
    valid["log_ratio"] = np.log(valid.v_tokens / valid.b_tokens)
    meta = data.drop_duplicates(["smell", "level", "task"])
    audit = dict(
        onset={m: onset(g) for m, g in valid.groupby("model")},
        topology=topology(meta),
        branch_bins=patch_bins(meta, valid),
        glm_gc_levels=middle_severity(valid),
        gpt_gc_tail=tail_reads(valid),
        gpt_lm_160=threshold_sensitivity(valid),
        gpt_direct_success=direct_success(),
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False, default=lambda x: x.item()))
