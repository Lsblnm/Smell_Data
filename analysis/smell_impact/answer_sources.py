"""Audit observable answer access in the local archive. Never fetch a URL or run a transcript command."""

import csv
from collections import defaultdict
import gzip
from itertools import chain
import json
from math import expm1, log
import re
from statistics import fmean
from urllib.parse import urlsplit

from measure import OUT, ROOT, TRACES


def lucene_prompt_evidence():
    edits = []
    results = {}
    for group, number in (("None-FE", 10), ("FE-S2", 24)):
        folder = TRACES / "gpt" / group / "apache__lucene-12626"
        prompt = (folder / "prompt.txt").read_text()
        blocks = dict(re.findall(r"^(Existing|Fix):\s*\n```\n([\s\S]*?)\n```", prompt, re.M))
        events = [
            json.loads(line)
            for line in (folder / "trajectory.jsonl").read_bytes().splitlines()
            if line.strip()
        ]
        event = events[number - 1]["part"]
        assert event["tool"] == "apply_patch"
        edit = event["state"]["input"]["patchText"]
        hunk = edit.split("\n@@\n", 1)[1].split("\n*** End Patch", 1)[0].splitlines()
        before = "\n".join(line[1:] for line in hunk if line.startswith((" ", "-")))
        after = "\n".join(line[1:] for line in hunk if line.startswith((" ", "+")))
        assert (before, after) == (blocks["Existing"], blocks["Fix"])
        preceding = [e["part"]["tool"] for e in events[: number - 1] if e["type"] == "tool_use"]
        assert set(preceding) <= {"read", "grep", "glob", "todowrite"}
        results[group] = dict(line=number, status=event["state"]["status"], previous_tools=preceding)
        edits.append(edit)
    assert (
        edits[0] == edits[1]
        and results["None-FE"]["status"] == "completed"
        and results["FE-S2"]["status"] == "error"
    )
    return results


def lombok_commit_evidence():
    folder = TRACES / "glm" / "GC-S2" / "projectlombok__lombok-3326"
    events = [
        json.loads(line)["part"]
        for line in (folder / "trajectory.jsonl").read_bytes().splitlines()
        if line.strip()
    ]
    merge = events[41]["state"]["output"]
    history = events[47]["state"]
    assert "Merge pull request #3326" in merge
    assert "show 5f0582ba" in history["input"]["command"] and "commit 5f0582ba" in history["output"]
    assert "apply the same fix" in events[50]["text"]
    assert "erasure_field" not in (folder / "prompt.txt").read_text()
    final = (folder / "patch.diff").read_text().splitlines()
    for edit_line, code in [
        (58, "public Type erasure_field;"),
        (59, "innerClassSymbol.erasure_field = null;"),
    ]:
        assert any(line.startswith("+") and code in line for line in history["output"].splitlines())
        assert (
            events[edit_line - 1]["state"]["status"] == "completed"
            and code in events[edit_line - 1]["state"]["input"]["newString"]
        )
        assert any(line.startswith("+") and code in line for line in final)
    return {"projectlombok__lombok-3326": f"{folder.relative_to(ROOT)}/trajectory.jsonl#L48"}


def same_pr_diff_access():
    """One row per main session. Only direct GitHub PR .diff/.patch URLs with returned hunks qualify."""
    seen = set()
    rows = []
    for path in sorted(TRACES.glob("*/*/*/trajectory.jsonl")):
        model, group, task = path.parts[-4:-1]
        repo, number = task.rsplit("-", 1)
        prefix = f"/{repo.replace('__', '/')}/pull/{number}"
        with path.open("rb") as file:
            first = next((item for item in enumerate(file, 1) if item[1].strip()), None)
            if not first:
                continue
            session = json.loads(first[1]).get("sessionID")
            if not session or (model, session) in seen:
                continue
            seen.add((model, session))
            for line_no, line in chain([first], enumerate(file, first[0] + 1)):
                if b'"webfetch"' not in line or b"/pull/" not in line:
                    continue
                event = json.loads(line)
                part = event.get("part", {})
                if (
                    event["type"] != "tool_use"
                    or part.get("tool") != "webfetch"
                    or event.get("sessionID") != session
                ):
                    continue
                state = part.get("state", {})
                url = state.get("input", {}).get("url", "")
                parsed = urlsplit(url)
                if parsed.hostname != "github.com" or parsed.path.lower() not in (
                    prefix.lower() + ".diff",
                    prefix.lower() + ".patch",
                ):
                    continue
                output = state.get("output") or ""
                if state.get("status") != "completed" or not re.search(
                    r"^diff --git a/.+ b/.+", output, re.M
                ):
                    continue
                hunk = re.search(r"^@@ -\d+[^\n]*\n", output, re.M)
                if hunk is None or not re.search(
                    r"^[+-](?![+-]{2})(?=.*\w).+", output[hunk.end() :], re.M
                ):
                    continue
                rows.append(
                    dict(
                        model=model,
                        session=session,
                        task=task,
                        group=group,
                        line=line_no,
                        url=url,
                        trace=str(path.relative_to(ROOT)),
                    )
                )
                break
    return seen, rows


def excluding_displayed_pr_tasks(hits):
    excluded = {hit["task"] for hit in hits} | {"projectlombok__lombok-3326", "apache__lucene-12626"}
    groups = defaultdict(lambda: defaultdict(list))
    with gzip.open(OUT / "paired_tasks.csv.gz", "rt") as file:
        for row in csv.DictReader(file):
            if row["task"] in excluded or not all(
                row[k] == "1" for k in ("b_usable", "v_usable", "prompt_matched")
            ):
                continue
            groups[row["model"]][row["task"]].append(log(int(row["v_tokens"]) / int(row["b_tokens"])))
    return {
        "excluded_tasks": len(excluded),
        "remaining": {
            model: {
                "tasks": len(tasks),
                "pairs": sum(map(len, tasks.values())),
                "token_pct": round(100 * expm1(fmean(fmean(ratios) for ratios in tasks.values())), 2),
            }
            for model, tasks in groups.items()
        },
    }


def write_task_access(hits, verified_git):
    with gzip.open(OUT / "paired_tasks.csv.gz", "rt") as file:
        tasks = {row["task"] for row in csv.DictReader(file)}
    evidence = defaultdict(dict)
    for hit in hits:
        evidence[hit["task"]].setdefault(hit["model"], f"{hit['trace']}#L{hit['line']}")
    confirmed = set(evidence) | set(verified_git)
    assert confirmed <= tasks
    with (OUT / "answer_access_by_task.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(
            [
                "task",
                "upstream_fix_access",
                "target_pr_models",
                "target_pr_evidence",
                "verified_git_adoption",
            ]
        )
        for task in sorted(tasks):
            examples = evidence.get(task, {})
            writer.writerow(
                [
                    task,
                    "confirmed" if task in confirmed else "not_observed",
                    "|".join(sorted(examples)),
                    "|".join(examples[m] for m in sorted(examples)),
                    verified_git.get(task, ""),
                ]
            )
    return {
        "total": len(tasks),
        "target_pr": len(evidence),
        "confirmed": len(confirmed),
        "additional_verified_git": len(set(verified_git) - set(evidence)),
    }


if __name__ == "__main__":
    evidence = lucene_prompt_evidence()
    verified_git = lombok_commit_evidence()
    sessions, hits = same_pr_diff_access()
    with (OUT / "target_pr_access.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["model", "session", "task", "group", "line", "url", "trace"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(hits)
    print(
        json.dumps(
            dict(
                by_task=write_task_access(hits, verified_git),
                lucene=evidence,
                lombok_shown_then_applied=True,
                trace_sessions=len(sessions),
                returned_pr_diff_sessions=len(hits),
                tasks=len({r["task"] for r in hits}),
                by_model={m: sum(r["model"] == m for r in hits) for m in ("gpt", "glm", "deepseek")},
                sensitivity=excluding_displayed_pr_tasks(hits),
            ),
            indent=2,
        )
    )
