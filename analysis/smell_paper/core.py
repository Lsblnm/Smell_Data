"""Shared data assembly and statistics for the paper analysis."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = HERE / "data"
PAIRED = ROOT / "analysis" / "smell_impact" / "paired_tasks.csv.gz"
PATCHES = ROOT / "smell-patch"
TRACES = ROOT / "traj_results" / "opencode"

MODELS = ["gpt", "glm", "deepseek"]
MODEL_NAME = {"gpt": "GPT-5.6-Terra", "glm": "GLM-5.3-Flash", "deepseek": "DeepSeek-V4.1-Flash"}
MODEL_SHORT = {"gpt": "GPT", "glm": "GLM", "deepseek": "DeepSeek"}
SMELLS = ["FE", "GC", "LM"]
SMELL_DIR = {"FE": "FeatureEnvy", "GC": "GodClass", "LM": "LongMethod"}
SMELL_NAME = {"FE": "Feature Envy", "GC": "God Class", "LM": "Long Method"}
LEVELS = ["S0", "S1", "S2"]
KNOWN = {"resolved", "unresolved"}
SEED = 20261118
DRAWS = 4000
# chars-per-token and carried share of generated tokens, estimated in mechanism() from context increments
FILE_HEADER = re.compile(rb"^diff --git a/.*? b/(.+)$", re.M)

LANG = {
    "apache__druid": "Java", "apache__lucene": "Java", "google__gson": "Java", "javaparser__javaparser": "Java",
    "projectlombok__lombok": "Java", "reactivex__rxjava": "Java",
    "mrdoob__three.js": "JS/TS", "preactjs__preact": "JS/TS", "axios__axios": "JS/TS", "facebook__docusaurus": "JS/TS",
    "immutable-js__immutable-js": "JS/TS", "babel__babel": "JS/TS", "vuejs__core": "JS/TS",
    "caddyserver__caddy": "Go", "gohugoio__hugo": "Go", "hashicorp__terraform": "Go", "gin-gonic__gin": "Go",
    "prometheus__prometheus": "Go",
    "nushell__nushell": "Rust", "sharkdp__bat": "Rust", "tokio-rs__tokio": "Rust", "tokio-rs__axum": "Rust",
    "astral-sh__ruff": "Rust", "burntsushi__ripgrep": "Rust", "uutils__coreutils": "Rust", "tokio-rs__bytes": "Rust",
    "laravel__framework": "PHP", "phpoffice__phpspreadsheet": "PHP", "php-cs-fixer__php-cs-fixer": "PHP",
    "briannesbitt__carbon": "PHP",
    "rubocop__rubocop": "Ruby", "fluent__fluentd": "Ruby", "jekyll__jekyll": "Ruby", "fastlane__fastlane": "Ruby",
    "faker-ruby__faker": "Ruby", "jordansissel__fpm": "Ruby",
    "redis__redis": "C/C++", "jqlang__jq": "C/C++", "micropython__micropython": "C/C++", "fmtlib__fmt": "C/C++",
    "nlohmann__json": "C/C++", "valkey-io__valkey": "C/C++",
}


def cluster_boot(values, clusters, stat=np.mean, draws=DRAWS, seed=SEED):
    """Percentile cluster bootstrap (resample repositories). Returns (point, lo, hi)."""
    x = np.asarray(values, float)
    c = np.asarray(clusters)
    keys, codes = np.unique(c, return_inverse=True)
    rng = np.random.default_rng(seed)
    point = float(stat(x))
    if stat is np.mean:
        sums = np.bincount(codes, weights=x)
        cnts = np.bincount(codes)
        w = rng.multinomial(len(keys), np.full(len(keys), 1 / len(keys)), size=draws)
        reps = (w @ sums) / (w @ cnts)
    else:
        idx_by = [np.where(codes == i)[0] for i in range(len(keys))]
        reps = np.empty(draws)
        for d in range(draws):
            pick = rng.integers(0, len(keys), len(keys))
            reps[d] = stat(x[np.concatenate([idx_by[i] for i in pick])])
    lo, hi = np.quantile(reps, [0.025, 0.975])
    return point, float(lo), float(hi)


def pct(logv):
    return 100 * np.expm1(logv)


def task_mean_ci(frame, col, key=("task", "repo")):
    """Average within task first (equal task weight), then cluster bootstrap by repo."""
    t = frame.groupby(list(key), as_index=False)[col].mean()
    return cluster_boot(t[col], t.repo)


@lru_cache(maxsize=None)
def injection_paths(smell, level, task):
    p = PATCHES / level / SMELL_DIR[smell] / f"{task}-{smell}.patch"
    return frozenset(x.decode() for x in FILE_HEADER.findall(p.read_bytes()))


def load_pairs():
    f = pd.read_csv(PAIRED)
    with np.errstate(divide="ignore", invalid="ignore"):
        extra = pd.DataFrame({
            "lang": f.repo.map(LANG).fillna("Other"),
            "usable": f.b_usable.eq(1) & f.v_usable.eq(1) & f.prompt_matched.eq(1),
            "dtok": np.log(f.v_tokens / f.b_tokens),
            "dsec": np.log(f.v_seconds / f.b_seconds),
            "dstep": np.log(f.v_steps / f.b_steps),
        })
    extra["dper"] = extra.dtok - extra.dstep
    extra["dsecstep"] = extra.dsec - extra.dstep
    return pd.concat([f, extra], axis=1)


def load_runs():
    return pd.read_csv(DATA / "runs.csv.gz")


def load_calls():
    return pd.read_csv(DATA / "calls.csv.gz")
