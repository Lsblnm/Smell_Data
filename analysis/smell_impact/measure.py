"""Read the archived experiment. Commands in transcripts are data, never executed."""

from collections import Counter
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re

from static_metrics import MAY_WRITE, annotation, paired_reads, read_window


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
TRACES = ROOT / "traj_results/opencode"
MODELS = ("gpt", "glm", "deepseek")
SMELLS = {"FE": "FeatureEnvy", "GC": "GodClass", "LM": "LongMethod"}
LEVELS = ("S0", "S1", "S2")
CONTAINER = re.compile(r"cli-eval-opencode-[A-Za-z0-9_.-]+?-[0-9a-f]{8}\b")
INSPECT = re.compile(
    r"(?:^|[;&|\n'\"(]\s*|\s-?lc\s+)(?:\s*)(?:rg|grep|ag|sed|cat|head|tail|awk|less|nl|find|ls|git\s+(?:show|grep))\s"
)
TEST = re.compile(
    r"\b(?:pytest|phpunit|rspec|ctest|jest|vitest|mocha|sbt\s+test|cargo\s+(?:nextest|test)|go\s+test|dotnet\s+test|(?:npm|yarn|pnpm|bundle\s+exec)\s+(?:run\s+)?test)\b|(?:\bmvnw?\b|\bgradlew?\b)[^\n]{0,220}?(?:\btest\b|Test|--tests)|(?:\bbin/rails\s+test|\bmake\s+(?:check|test))",
    re.I,
)
SHELL_WRITE = re.compile(
    r"\b(?:apply_patch|git\s+apply|tee|sed\s+-i|perl\s+-[pi]|write_text|open\([^\n]+?['\"]w['\"])\b"
)
FILE_HEADER = re.compile(rb"^diff --git a/.*? b/(.+)$", re.M)
ABS_TESTBED = re.compile(r"(?:/[\w.\-]+)*/testbed/")
REFERENCE = re.compile(
    r"\bgit\s+(?:-C\s+\S+\s+)?(?:clone\b|show\s+[^;|&\n]{0,80}?\b[0-9a-f]{7,40}\b)|\bgh\s+pr\b|https?://[^\s]+/(?:pull|pulls|commit|commits)/",
    re.I,
)


def grade_reports():
    reports = {}
    for path in sorted((ROOT / "bench_result").glob("*.json")):
        group = path.stem.split("opencode-gpt-")[1].upper().replace("NONE", "None")
        raw = json.loads(path.read_bytes())
        results = {}
        for state in ("resolved", "unresolved", "error", "empty_patch", "incomplete"):
            for task in raw[state + "_ids"]:
                if task in results:
                    raise ValueError(f"Overlapping grades in {path.name}: {task}")
                results[task] = state
        reports[group] = results
    return reports


@lru_cache(maxsize=None)
def changed_lines(path):
    if not path.exists():
        return None
    lines = path.read_bytes().splitlines()
    return tuple(
        line
        for line in lines
        if line.startswith((b"diff --git ", b"+", b"-")) and not line.startswith((b"--- ", b"+++ "))
    )


@lru_cache(maxsize=None)
def explicit_paths(paths):
    options = "|".join(re.escape(p) for p in paths)
    return re.compile(r"(?<![\w./-])(?:\./)?(?P<path>" + options + r")(?![\w./-])")


class Run:
    def __init__(self, folder):
        data_path = folder / "result.json"
        data = json.loads(data_path.read_bytes()) if data_path.exists() else {}
        prompt = folder / "prompt.txt"
        prompt_hash = ""
        if prompt.exists():
            prompt_hash = sha256(
                CONTAINER.sub("RUN_CONTAINER", prompt.read_text()).strip().encode()
            ).hexdigest()
        metrics = Counter(
            {
                k: 0
                for k in (
                    "tokens",
                    "steps",
                    "cache_read",
                    "cache_write",
                    "input",
                    "output",
                    "reasoning",
                    "calls",
                    "inspects",
                    "test_calls",
                    "structured_edits",
                    "tool_error",
                    "result_chars",
                    "inspect_chars",
                    "delegates",
                    "web_calls",
                    "first_context",
                    "missing_total",
                    "orphan_start",
                    "first_ts",
                    "last_ts",
                    "preedit_calls",
                    "reference_calls",
                )
            }
        )
        self.reads = []
        self.windows = {}
        before_edit = True
        first_edit_message = None
        tokens_through_edit = None
        self.session = ""
        first_edit = None
        end_reason = ""
        seen_finish = set()
        seen_calls = set()
        starts = 0
        path = folder / "trajectory.jsonl"
        if path.exists():
            with path.open("rb") as handle:
                for trace_line, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    evt = json.loads(line)
                    kind, part = evt["type"], evt.get("part", {})
                    ts = evt.get("timestamp") or 0
                    if not metrics["first_ts"]:
                        metrics["first_ts"] = ts
                        self.session = evt.get("sessionID", "")
                    metrics["last_ts"] = ts
                    if kind == "step_start":
                        starts += 1
                    elif kind == "step_finish":
                        key = (evt.get("sessionID"), part.get("id"))
                        if key in seen_finish:
                            continue
                        seen_finish.add(key)
                        tok = part.get("tokens") or {}
                        total = tok.get("total")
                        cache = tok.get("cache") or {}
                        end_reason = part.get("reason")
                        metrics["steps"] += 1
                        if not isinstance(total, (int, float)):
                            metrics["missing_total"] += 1
                            continue
                        if metrics["steps"] == 1:
                            metrics["first_context"] = tok["input"] + sum(cache.values())
                        metrics["tokens"] += total
                        if first_edit_message == (evt.get("sessionID"), part.get("messageID")):
                            tokens_through_edit = metrics["tokens"]
                            first_edit_message = None
                        for field in ("input", "output", "reasoning"):
                            metrics[field] += tok.get(field, 0)
                        for side in ("read", "write"):
                            metrics["cache_" + side] += cache.get(side, 0)
                    elif kind == "tool_use":
                        key = (evt.get("sessionID"), part.get("callID") or part.get("id"))
                        if key in seen_calls:
                            continue
                        seen_calls.add(key)
                        tool, state = part.get("tool"), part.get("state") or {}
                        args = state.get("input") or {}
                        if (
                            before_edit
                            and state.get("status") == "completed"
                            and tool in ("edit", "write", "apply_patch", "multiedit")
                        ):
                            first_edit_message = (evt.get("sessionID"), part.get("messageID"))
                        if before_edit and tool == "read" and state.get("status") == "completed":
                            file = ABS_TESTBED.sub("", args.get("filePath") or "").removeprefix("./")
                            window = read_window(args, state.get("output") or "", trace_line)
                            if window:
                                self.windows.setdefault(file, []).append(window)
                        if tool in ("edit", "write", "apply_patch", "multiedit") or (
                            tool == "bash" and MAY_WRITE.search(args.get("command") or "")
                        ):
                            before_edit = False
                        metrics["calls"] += 1
                        length = len(state.get("output") or state.get("error") or "")
                        metrics["result_chars"] += length
                        metrics["tool_error"] += state.get("status") == "error"
                        metrics["delegates"] += tool == "task"
                        metrics["web_calls"] += tool == "webfetch"
                        metrics["reference_calls"] += tool == "webfetch"
                        if tool in ("edit", "write", "apply_patch"):
                            metrics["structured_edits"] += 1
                            if first_edit is None:
                                first_edit = metrics["calls"] - 1
                        inspect_arg = ""
                        if tool in ("read", "grep", "glob"):
                            inspect_arg = args.get("filePath") or args.get("path") or "."
                        elif tool == "bash":
                            cmd = args.get("command") or ""
                            head = cmd.split("<<", 1)[0][:2400]
                            metrics["reference_calls"] += bool(REFERENCE.search(head))
                            testing = bool(TEST.search(head))
                            metrics["test_calls"] += testing
                            if not testing and not SHELL_WRITE.search(head) and INSPECT.search(head):
                                inspect_arg = head
                        if inspect_arg:
                            metrics["inspects"] += 1
                            metrics["inspect_chars"] += length
                            self.reads.append(
                                (tool == "bash", ABS_TESTBED.sub("", inspect_arg), length)
                            )
        metrics["orphan_start"] = starts - metrics["steps"]
        metrics["preedit_calls"] = first_edit if first_edit is not None else -1
        self.metrics = dict(metrics)
        self.metrics.update(
            tokens_through_edit=tokens_through_edit,
            seconds=data.get("agent_seconds"),
            status=data.get("status", "missing"),
            end_reason=end_reason,
            prompt_hash=prompt_hash,
        )
        self.metrics["usable"] = int(
            self.metrics["status"] == "COMPLETED"
            and end_reason == "stop"
            and (self.metrics["seconds"] or 0) > 0
            and metrics["tokens"] > 0
            and metrics["missing_total"] == 0
        )
        if metrics["tokens"] != sum(
            metrics[k] for k in ("input", "output", "reasoning", "cache_read", "cache_write")
        ):
            raise ValueError(f"Token components disagree in {folder}")

    def measure(self, paths):
        matcher = explicit_paths(paths)
        frequency = Counter()
        hits = []
        for shell, arg, length in self.reads:
            if shell:
                matches = {match["path"] for match in matcher.finditer(arg)}
            else:
                path = arg.removeprefix("./")
                matches = {path} if path in paths else set()
            if matches:
                frequency.update(matches)
                hits.append(length)
        return dict(
            self.metrics,
            touched_reads=len(hits),
            touched_chars=sum(hits),
            touched_distinct=len(frequency),
            touched_revisits=sum(frequency.values()) - len(frequency),
        )


@lru_cache(maxsize=None)
def injection(smell, level, task):
    path = ROOT / "smell-patch" / level / SMELLS[smell] / f"{task}-{smell}.patch"
    raw = path.read_bytes()
    files = tuple(p.decode("utf-8") for p in FILE_HEADER.findall(raw))
    added = sum(line.startswith(b"+") and not line.startswith(b"+++ ") for line in raw.splitlines())
    return files, added


def collect():
    grades = grade_reports()
    pairs, repeats = [], []
    diagnostics = Counter()
    presence = Counter()
    for model in MODELS:
        controls = {}
        for smell in SMELLS:
            group = "None-" + smell
            for directory in sorted((TRACES / model / group).iterdir()):
                if not directory.is_dir():
                    continue
                task = directory.name
                ctrl = Run(directory)
                if ctrl.session:
                    for prev_smell, prev in controls.get(task, []):
                        if prev.session == ctrl.session:
                            continue
                        repeats.append(
                            dict(
                                model=model,
                                task=task,
                                left=prev_smell,
                                right=smell,
                                left_grade=grades.get("None-" + prev_smell, {}).get(task, "")
                                if model == "gpt"
                                else "",
                                right_grade=grades.get(group, {}).get(task, "")
                                if model == "gpt"
                                else "",
                                **{"b_" + k: v for k, v in prev.metrics.items()},
                                **{"v_" + k: v for k, v in ctrl.metrics.items()},
                            )
                        )
                    controls.setdefault(task, []).append((smell, ctrl))
                for level in LEVELS:
                    variant_group = smell + "-" + level
                    other = Run(TRACES / model / variant_group / task)
                    paths, added = injection(smell, level, task)
                    meta = annotation(ROOT, SMELLS[smell], smell, level, task)
                    assert paths, (smell, level, task)
                    b, v = ctrl.measure(paths), other.measure(paths)
                    same_prompt = bool(b["prompt_hash"]) and b["prompt_hash"] == v["prompt_hash"]
                    if b["prompt_hash"] and v["prompt_hash"] and not same_prompt:
                        raise ValueError(f"Solver prompts differ for {model} {variant_group} {task}")
                    same_lines = None
                    if model == "gpt" and variant_group in grades:
                        first = changed_lines(directory / "patch.diff")
                        second = changed_lines(TRACES / model / variant_group / task / "patch.diff")
                        if first is not None and second is not None:
                            same_lines = int(first == second)
                    pairs.append(
                        dict(
                            model=model,
                            smell=smell,
                            level=level,
                            task=task,
                            repo=task.rsplit("-", 1)[0],
                            injection_files=len(paths),
                            injection_added=added,
                            prompt_matched=int(same_prompt),
                            same_changed_lines=same_lines,
                            **meta,
                            **paired_reads(
                                ctrl,
                                other,
                                meta,
                                directory,
                                TRACES / model / variant_group / task,
                                explicit_paths,
                                paths,
                            ),
                            b_grade=grades.get(group, {}).get(task, "") if model == "gpt" else "",
                            v_grade=grades.get(variant_group, {}).get(task, "")
                            if model == "gpt"
                            else "",
                            **{"b_" + k: v0 for k, v0 in b.items() if k != "prompt_hash"},
                            **{"v_" + k: v0 for k, v0 in v.items() if k != "prompt_hash"},
                        )
                    )
                    diagnostics["paired_slots"] += 1
                    diagnostics["identical_solver_prompt"] += same_prompt
                    diagnostics["usable"] += b["usable"] and v["usable"] and same_prompt
            presence[model, smell] = sum(1 for p in (TRACES / model / group).iterdir() if p.is_dir())
        diagnostics[model + "_shared_three_baselines"] = sum(
            len(items) == 3 and len({run.session for _, run in items}) == 1
            for items in controls.values()
        )
    return pairs, repeats, dict(diagnostics)
