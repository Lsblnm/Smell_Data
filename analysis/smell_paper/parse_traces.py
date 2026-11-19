"""Step-level parser for the OpenCode trajectories.

Produces two tables used by the paper analysis:
  runs.csv.gz   one row per (model, group, task) run: per-step context sizes and token totals
  calls.csv.gz  one row per tool call: step index, tool, category, returned chars,
                chars attributable to each injected file (union of all smell patches of that task)

Commands found inside transcripts are treated as data and never executed.
Run:  python parse_traces.py   (≈3-5 min on 8 cores for 2 GB of traces)
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TRACES = ROOT / "traj_results" / "opencode"
PATCHES = ROOT / "smell-patch"
OUT = HERE / "data"

ABS_TESTBED = re.compile(r"(?:/[\w.\-]+)*/testbed/")
FILE_HEADER = re.compile(rb"^diff --git a/.*? b/(.+)$", re.M)
TEST = re.compile(
    r"\b(?:pytest|phpunit|rspec|ctest|jest|vitest|mocha|sbt\s+test|cargo\s+(?:nextest|test)|go\s+test|dotnet\s+test|"
    r"(?:npm|yarn|pnpm|bundle\s+exec)\s+(?:run\s+)?test)\b|(?:\bmvnw?\b|\bgradlew?\b)[^\n]{0,220}?(?:\btest\b|Test|--tests)|"
    r"(?:\bbin/rails\s+test|\bmake\s+(?:check|test))",
    re.I,
)
BUILD = re.compile(r"\b(?:mvnw?|gradlew?|cargo\s+(?:build|check)|go\s+(?:build|vet)|make|cmake|npm\s+run|tsc|composer)\b", re.I)
INSPECT = re.compile(
    r"(?:^|[;&|\n'\"(]\s*|\s-?lc\s+)(?:\s*)(?:rg|grep|ag|sed|cat|head|tail|awk|less|nl|find|ls|wc|git\s+(?:show|grep|log|diff|blame))\s"
)
GREP_BLOCK = re.compile(r"^(?P<path>/[^\n]*?):\n", re.M)
GREP_COUNT = re.compile(r"^Found (\d+) matches", re.M)
CAPPED = re.compile(r"\(Output capped at|Use offset=\d+ to continue")


def injection_universe() -> dict[str, set[str]]:
    universe: dict[str, set[str]] = defaultdict(set)
    for patch in PATCHES.glob("S*/*/*.patch"):
        name = patch.name
        if name.endswith(("-gold.patch", "-test.patch")):
            continue
        task = name.rsplit("-", 1)[0]
        for p in FILE_HEADER.findall(patch.read_bytes()):
            universe[task].add(p.decode())
    return universe


def norm(path: str) -> str:
    return ABS_TESTBED.sub("", path or "").removeprefix("./")


def parse_run(job):
    model, group, task, paths = job
    folder = TRACES / model / group / task
    traj = folder / "trajectory.jsonl"
    res = {}
    rpath = folder / "result.json"
    if rpath.exists():
        res = json.loads(rpath.read_bytes())
    run = dict(model=model, group=group, task=task, status=res.get("status", "missing"),
               seconds=res.get("agent_seconds"))
    calls = []
    if not traj.exists():
        return run, calls
    matcher = re.compile(
        r"(?<![\w./-])(?:\./)?(" + "|".join(re.escape(p) for p in sorted(paths, key=len, reverse=True)) + r")(?![\w./-])"
    ) if paths else None
    main = None
    seen_finish, seen_calls = set(), set()
    ctx, out, tot, dur = [], [], [], []
    step_start_ts = None
    all_tokens = 0
    step = 0
    end_reason = ""
    with traj.open("rb") as fh:
        for line in fh:
            if not line.strip():
                continue
            evt = json.loads(line)
            kind, part = evt["type"], evt.get("part", {})
            sess = evt.get("sessionID")
            if main is None:
                main = sess
            if kind == "step_start" and sess == main:
                step_start_ts = evt.get("timestamp")
            elif kind == "step_finish":
                key = (sess, part.get("id"))
                if key in seen_finish:
                    continue
                seen_finish.add(key)
                tok = part.get("tokens") or {}
                total = tok.get("total")
                if not isinstance(total, (int, float)):
                    continue
                all_tokens += total
                if sess != main:
                    continue
                cache = tok.get("cache") or {}
                ctx.append(tok.get("input", 0) + cache.get("read", 0) + cache.get("write", 0))
                out.append(tok.get("output", 0) + tok.get("reasoning", 0))
                tot.append(total)
                ts = evt.get("timestamp")
                dur.append((ts - step_start_ts) / 1000 if ts and step_start_ts else -1)
                end_reason = part.get("reason") or ""
                step += 1
            elif kind == "tool_use":
                key = (sess, part.get("callID") or part.get("id"))
                if key in seen_calls or sess != main:
                    continue
                seen_calls.add(key)
                tool = part.get("tool")
                state = part.get("state") or {}
                args = state.get("input") or {}
                output = state.get("output") or state.get("error") or ""
                chars = len(output)
                cat, attributed, capped, matches = "other", {}, 0, 0
                offset = limit = None
                if tool == "read":
                    cat = "read"
                    p = norm(args.get("filePath") or "")
                    if p in paths:
                        attributed[p] = chars
                    capped = int(bool(CAPPED.search(output[-400:])))
                    offset, limit = args.get("offset"), args.get("limit")
                elif tool == "grep":
                    cat = "search"
                    mc = GREP_COUNT.search(output)
                    matches = int(mc.group(1)) if mc else output.count("Line ")
                    blocks = list(GREP_BLOCK.finditer(output))
                    for i, b in enumerate(blocks):
                        p = norm(b["path"])
                        if p in paths:
                            end = blocks[i + 1].start() if i + 1 < len(blocks) else len(output)
                            attributed[p] = attributed.get(p, 0) + end - b.start()
                elif tool == "glob" or tool == "list":
                    cat = "search"
                elif tool in ("edit", "write", "apply_patch", "multiedit", "patch"):
                    cat = "edit"
                elif tool == "bash":
                    cmd = (args.get("command") or "")
                    head = cmd.split("<<", 1)[0][:2400]
                    if TEST.search(head):
                        cat = "test"
                    elif INSPECT.search(head):
                        cat = "shell_inspect"
                        if matcher:
                            hits = {m[1] for m in matcher.finditer(head)}
                            for p in hits:
                                attributed[p] = chars // len(hits)
                    elif BUILD.search(head):
                        cat = "build"
                    else:
                        cat = "shell_other"
                elif tool in ("webfetch", "websearch"):
                    cat = "web"
                elif tool == "task":
                    cat = "delegate"
                elif tool in ("todowrite", "todoread"):
                    cat = "todo"
                calls.append(dict(model=model, group=group, task=task, k=step, tool=tool, cat=cat,
                                  status=state.get("status"), chars=chars, capped=capped, matches=matches,
                                  offset=offset, limit=limit,
                                  attributed=";".join(f"{p}={c}" for p, c in attributed.items())))
    run.update(
        steps=len(ctx), tokens_main=sum(tot), tokens_all=all_tokens, ctx_first=ctx[0] if ctx else None,
        ctx_last=ctx[-1] if ctx else None, ctx_max=max(ctx) if ctx else None, out_sum=sum(out),
        ctx_sum=sum(ctx), end_reason=end_reason,
        compaction=int(any(ctx[i] < 0.6 * ctx[i - 1] for i in range(1, len(ctx)))),
        ctx_series=" ".join(map(str, ctx)), out_series=" ".join(map(str, out)),
        dur_series=" ".join(f"{d:.2f}" for d in dur),
    )
    return run, calls


def main():
    OUT.mkdir(exist_ok=True)
    universe = injection_universe()
    jobs = []
    for model_dir in sorted(TRACES.iterdir()):
        for group_dir in sorted(model_dir.iterdir()):
            for task_dir in sorted(group_dir.iterdir()):
                if task_dir.is_dir():
                    jobs.append((model_dir.name, group_dir.name, task_dir.name, frozenset(universe.get(task_dir.name, ()))))
    runs, calls = [], []
    with ProcessPoolExecutor() as pool:
        for r, c in pool.map(parse_run, jobs, chunksize=16):
            runs.append(r)
            calls.extend(c)
    pd.DataFrame(runs).to_csv(OUT / "runs.csv.gz", index=False)
    pd.DataFrame(calls).to_csv(OUT / "calls.csv.gz", index=False)
    print(len(runs), "runs", len(calls), "calls")


if __name__ == "__main__":
    main()
