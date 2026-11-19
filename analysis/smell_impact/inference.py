"""Shared repository-level bootstrap used by the paired and continuous analyses."""

import numpy as np


SEED = 20261118
DRAWS = 5000
KNOWN = {"resolved", "unresolved"}


def cluster_interval(values, repos, statistic="mean", alpha=0.05):
    """Resample repositories and retain all their observations and original weights."""
    x = np.asarray(values, dtype=float)
    groups, codes = np.unique(repos, return_inverse=True)
    size = len(groups)
    rng = np.random.default_rng(SEED)
    counts = rng.multinomial(size, np.full(size, 1 / size), size=DRAWS)
    if statistic == "mean":
        numerators = (counts * np.bincount(codes, weights=x)).sum(axis=1)
        denominators = (counts * np.bincount(codes)).sum(axis=1)
        draws = numerators / denominators
        point = x.mean()
    else:
        order = np.argsort(x)
        ordered = x[order]
        cum = np.cumsum(counts[:, codes[order]], axis=1)
        last = cum[:, -1] - 1
        lo = (cum > (last // 2)[:, None]).argmax(axis=1)
        hi = (cum > ((last + 1) // 2)[:, None]).argmax(axis=1)
        draws = (ordered[lo] + ordered[hi]) / 2
        point = np.median(x)
    if not np.isfinite(draws).all():
        raise ValueError("A bootstrap replicate is not finite.")
    lo, hi = np.quantile(draws, [alpha / 2, 1 - alpha / 2])
    return [float(point), float(lo), float(hi)]
