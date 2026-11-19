"""Exact token accounting: total = N*ctx_0 + sum_j delta_j*(N-1-j) + sum out.

Each context increment delta_j (between consecutive model calls) is split across what produced it
(tool output by category, injected-file content, carried model output) in proportion to the
fitted contribution  alpha*out_j + chars_j/rho  (R^2 = 0.94-0.97 per model)."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from core import injection_paths

CATS = ["overhead", "inj_read", "other_read", "test_build", "other_tool", "gen_carried", "gen"]
READ_CATS = {"read", "search", "shell_inspect"}


def fit_rates(runs, calls):
    """Per model: d ctx = alpha*out + chars/rho + c, OLS on positive increments."""
    per_step = calls.groupby(["model", "group", "task", "k"]).chars.sum()
    rates = {}
    for model, rs in runs.groupby("model"):
        rows = []
        for r in rs.sample(min(len(rs), 2500), random_state=7).itertuples():
            if not isinstance(r.ctx_series, str):
                continue
            c = np.fromstring(r.ctx_series, sep=" ")
            o = np.fromstring(r.out_series, sep=" ")
            try:
                ch = per_step.loc[(r.model, r.group, r.task)]
            except KeyError:
                ch = pd.Series(dtype=float)
            for j in range(len(c) - 1):
                rows.append((c[j + 1] - c[j], o[j], ch.get(j, 0)))
        x = np.array(rows)
        x = x[(x[:, 0] > 0) & (x[:, 0] < 60000)]
        a = np.c_[x[:, 1], x[:, 2], np.ones(len(x))]
        beta = np.linalg.lstsq(a, x[:, 0], rcond=None)[0]
        r2 = np.corrcoef(a @ beta, x[:, 0])[0, 1] ** 2
        rates[model] = dict(alpha=float(beta[0]), rho=float(1 / beta[1]), const=float(beta[2]), r2=float(r2), n=len(x))
    return rates


class RunIndex:
    def __init__(self, runs, calls):
        self.runs = {(r.model, r.group, r.task): r for r in runs.itertuples()}
        self.steps = defaultdict(list)
        for c in calls.itertuples():
            inj = {}
            if isinstance(c.attributed, str) and c.attributed:
                for item in c.attributed.split(";"):
                    p, _, v = item.rpartition("=")
                    inj[p] = int(v)
            self.steps[(c.model, c.group, c.task)].append((c.k, c.cat, c.chars, inj))

    def account(self, model, group, task, paths, rate):
        r = self.runs.get((model, group, task))
        if r is None or not isinstance(r.ctx_series, str):
            return None
        ctx = np.fromstring(r.ctx_series, sep=" ")
        out = np.fromstring(r.out_series, sep=" ")
        n = len(ctx)
        comp = np.zeros((n, 5))  # inj, other_read, test_build, other_tool, gen_carried (predicted tokens)
        comp[:, 4] = rate["alpha"] * out
        for k, cat, chars, inj in self.steps.get((model, group, task), ()):
            if k >= n:
                continue
            ij = sum(v for p, v in inj.items() if p in paths)
            ij = min(ij, chars)
            rest = chars - ij
            comp[k, 0] += ij / rate["rho"]
            if cat in READ_CATS:
                comp[k, 1] += rest / rate["rho"]
            elif cat in ("test", "build"):
                comp[k, 2] += rest / rate["rho"]
            else:
                comp[k, 3] += rest / rate["rho"]
        res = dict.fromkeys(CATS, 0.0)
        res["overhead"] = n * ctx[0]
        res["gen"] = out.sum()
        for j in range(n - 1):
            d = ctx[j + 1] - ctx[j]
            carry = n - 1 - j
            tot = comp[j].sum()
            if tot <= 0:
                res["other_tool"] += d * carry
                continue
            share = comp[j] / tot
            for i, name in enumerate(["inj_read", "other_read", "test_build", "other_tool", "gen_carried"]):
                res[name] += share[i] * d * carry
        res["total"] = float(sum(res[c] for c in CATS))
        res["steps"] = n
        res["inj_chars"] = sum(min(sum(v for p, v in inj.items() if p in paths), ch)
                               for _, _, ch, inj in self.steps.get((model, group, task), ()))
        return res


def pair_accounting(pairs, runs, calls, rates):
    idx = RunIndex(runs, calls)
    rows = []
    for p in pairs.itertuples():
        paths = injection_paths(p.smell, p.level, p.task)
        b = idx.account(p.model, "None-" + p.smell, p.task, paths, rates[p.model])
        v = idx.account(p.model, f"{p.smell}-{p.level}", p.task, paths, rates[p.model])
        if b is None or v is None:
            continue
        row = dict(model=p.model, smell=p.smell, level=p.level, task=p.task, repo=p.repo)
        row.update({"b_" + k: b[k] for k in b})
        row.update({"v_" + k: v[k] for k in v})
        rows.append(row)
    return pd.DataFrame(rows)
