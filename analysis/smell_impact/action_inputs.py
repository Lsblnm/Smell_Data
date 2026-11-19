"""Compare the same observed tool inputs on both sides of a repair. No commands from logs are run."""

from collections import Counter
import csv
import gzip
import json
import re

from measure import OUT, ROOT, TRACES
from static_metrics import MAY_WRITE
from answer_sources import lucene_prompt_evidence


def local_path(value):
    if "/testbed/" in value:
        return value.rsplit("/testbed/", 1)[1]
    if value.endswith("/testbed") or value in ("", "./"):
        return "."
    return value.removeprefix("./")


def grep_count(state):
    if state.get("status") != "completed":
        return None
    output = state.get("output") or ""
    first = output.strip().split("\n", 1)[0]
    if first in ("No files found", "No matches found"):
        return 0
    m = re.fullmatch(r"Found ([0-9]+) match(?:es)?", first.strip(), re.I)
    # Exclude truncated output rather than using the count limit as an equality.
    if (
        not m
        or (state.get("metadata") or {}).get("truncated")
        or "more matches available" in output.lower()
    ):
        return None
    return int(m[1])


def edit_key(tool, args):
    args = dict(args)
    if tool == "edit" and args.get("filePath") and args.get("oldString") is not None:
        args["filePath"] = local_path(args["filePath"])
    elif tool == "apply_patch" and args.get("patchText"):
        args["patchText"] = re.sub(
            r"^(\*\*\* (?:Update File|Add File|Delete File|Move to): )(.+)$",
            lambda m: m[1] + local_path(m[2]),
            args["patchText"],
            flags=re.M,
        )
    else:
        return None
    return tool, json.dumps(args, sort_keys=True, ensure_ascii=False)


def pre_edit_inputs(path):
    searches = {}
    with path.open("rb") as file:
        for raw in file:
            evt = json.loads(raw)
            if evt["type"] != "tool_use":
                continue
            part = evt["part"]
            tool, state = part.get("tool"), part.get("state") or {}
            args = state.get("input") or {}
            if tool == "grep":
                count = grep_count(state)
                if count is not None and args.get("pattern"):
                    settings = dict(args, path=local_path(args.get("path") or "."))
                    if not settings["path"].startswith("/"):
                        key = json.dumps(settings, sort_keys=True, ensure_ascii=False)
                        searches.setdefault(key, count)
            elif tool in ("edit", "apply_patch", "write", "multiedit"):
                return searches, (edit_key(tool, args), state.get("status"))
            elif tool == "bash" and MAY_WRITE.search(args.get("command") or ""):
                break
    return searches, (None, None)


def matched_inputs():
    with gzip.open(OUT / "paired_tasks.csv.gz", "rt") as handle:
        rows = [
            r
            for r in csv.DictReader(handle)
            if r["b_usable"] == r["v_usable"] == r["prompt_matched"] == "1"
            and r["adapted_tests"] == "0"
        ]
    metrics = {}
    controls = {}
    for row in rows:
        model, smell, level, task = (row[k] for k in ("model", "smell", "level", "task"))
        base = TRACES / model / ("None-" + smell) / task / "trajectory.jsonl"
        if base not in controls:
            controls[base] = pre_edit_inputs(base)
        left, first = controls[base]
        right, second = pre_edit_inputs(
            TRACES / model / (smell + "-" + level) / task / "trajectory.jsonl"
        )
        counts = metrics.setdefault(model + "/" + smell, Counter())
        counts["eligible"] += 1
        # One vote per pair. Use baseline order and choose without inspecting the difference.
        query = next((key for key in left if key in right), None)
        if query is not None:
            before, after = left[query], right[query]
            direction = "same" if before == after else "more" if after > before else "fewer"
            counts["same_grep_" + direction] += 1
        if first[0] is not None and first[0] == second[0]:
            counts["same_edit_" + str(first[1]) + "_to_" + str(second[1])] += 1
    return metrics


def event(model, group, task, line):
    path = TRACES / model / group / task / "trajectory.jsonl"
    with path.open("rb") as fh:
        for n, raw in enumerate(fh, 1):
            if n == line:
                return json.loads(raw)["part"]["state"]
    raise ValueError(f"Missing line {line} in {path}")


def case_checks():
    lucene_prompt_evidence()

    gson = "google__gson-2479"
    a = event("deepseek", "None-GC", gson, 6)
    z = event("deepseek", "GC-S2", gson, 5)
    assert (
        a["input"]["command"].split("/testbed && ", 1)[1]
        == z["input"]["command"].split("/testbed && ", 1)[1]
    )
    old = {line for line in a["output"].splitlines() if re.match(r"^\d+:", line)}
    new = {line for line in z["output"].splitlines() if re.match(r"^\d+:", line)}
    assert old.issubset(new)

    laravel = "laravel__framework-52451"
    selector = "$inlineEntry[$this->getAttributeType($attribute)]"
    guard = "$sourceKey === $attribute && is_array($message)"
    base = event("gpt", "None-FE", laravel, 33)["output"]
    treatment = event("gpt", "FE-S2", laravel, 18)["output"]
    assert selector in base and guard in base and guard in treatment and selector not in treatment
    selector_read = None
    path = TRACES / "gpt" / "FE-S2" / laravel / "trajectory.jsonl"
    with path.open("rb") as file:
        for n, raw in enumerate(file, 1):
            evt = json.loads(raw)
            if evt["type"] == "tool_use" and selector in (
                evt["part"].get("state", {}).get("output") or ""
            ):
                selector_read = n
                break
    assert selector_read == 63
    first = event("gpt", "FE-S2", laravel, 40)["input"]["patchText"]
    assert "+                        continue;" in first
    failed = event("gpt", "FE-S2", laravel, 47)["output"]
    assert "validation.size.string" in failed and "name should be of length 9" in failed
    assert "validation.size.string" in event("gpt", "FE-S2", laravel, 57)["output"]
    fix_message = event("gpt", "FE-S2", laravel, 66)["input"]["patchText"]
    assert any(
        line.startswith("+") and "if ($rule !== null)" in line for line in fix_message.splitlines()
    )
    assert "OK (676 tests" in event("gpt", "FE-S2", laravel, 70)["output"]
    fixes = [
        TRACES / "gpt" / "None-FE" / laravel / "patch.diff",
        ROOT / "smell-patch" / "S2" / "FeatureEnvy" / (laravel + "-FE-gold.patch"),
    ]
    changed = [
        [
            line
            for line in fix.read_bytes().splitlines()
            if line.startswith((b"+", b"-")) and not line.startswith((b"+++ ", b"--- "))
        ]
        for fix in fixes
    ]
    assert changed[0] == changed[1] and len(changed[0]) == 4
    return dict(
        lucene_same_patch_different_status=True,
        lucene_edit_matches_existing_and_fix_in_prompt=True,
        gson_original_matches=len(old),
        gson_injected_matches=len(new),
        gson_preserved_matches=len(old & new),
        laravel_guard_and_type_selector_same_base_read=True,
        laravel_injected_type_selector_first_tool_output=selector_read,
        laravel_base_solution_and_adapted_gold_same_changed_lines=True,
        laravel_regression_observed=True,
    )


if __name__ == "__main__":
    groups = matched_inputs()
    total = Counter()
    for counts in groups.values():
        total.update(counts)
    print(
        json.dumps(
            dict(exact_cases=case_checks(), total=total, paired_inputs=groups),
            ensure_ascii=False,
            indent=2,
        )
    )
