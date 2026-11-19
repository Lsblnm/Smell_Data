"""Link reported smell metrics, physical patch changes and observable source reads."""

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import re


HUNK = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
HEADER = re.compile(rb"^diff --git a/.*? b/(.+)$")
NUMBERED = re.compile(r"^(\d+):(?: )?(.*)$", re.M)
FILE_TOTAL = re.compile(r"(?:End of file - total (\d+) lines|Showing lines \d+-\d+ of (\d+)\.)")
MAY_WRITE = re.compile(
    r"\b(?:apply_patch|patch\s+-|tee\s|sed\s+-i|perl\s+-[pi]|git\s+(?:apply|reset|checkout|restore|stash)|write_text\s*\(|write_bytes\s*\(|open\([^\n]{0,160}?['\"](?:w|a)[bt+]?['\"])|(?<![\d>])>{1,2}\s*(?![>&]|/dev/)[\w./-]+"
)
METRICS = {
    "FE": ("atfd", "laa", "fdp"),
    "GC": ("loc", "wmc", "tcc"),
    "LM": ("loc", "cc", "depth"),
}
RAD = ("rad_files", "rad_modules", "rad_distance")
KEYS = {
    "LOC": "loc",
    "WMC": "wmc",
    "TCC": "tcc",
    "ATFD": "atfd",
    "LAA": "laa",
    "FDP": "fdp",
    "CC": "cc",
    "嵌套深度": "depth",
    "文件分散度": "rad_files",
    "模块跨度": "rad_modules",
    "结构距离": "rad_distance",
}


@lru_cache(maxsize=None)
def annotation(root, dirname, smell, level, task):
    stub = f"{task}-{smell}"
    text = (root / "smell-patch-intro" / level / dirname / (stub + ".json")).read_text()
    info = json.JSONDecoder().raw_decode(text[text.index("{") :])[0]
    assert info["实例名称"] == task and info["Status"] == "SUCCESS"
    loc = info["注入位置"]
    target = loc["目标文件"]
    unit = loc.get("目标方法", loc.get("目标类"))
    source = loc.get("来源文件") if smell == "FE" else ""
    values = {"target": target, "target_unit": unit, "source": source, "exposure": loc["暴露等级"]}
    for k, v in info["质量因子"].items():
        if k == "RAD":
            values.update({KEYS[n]: m["数值"] for n, m in v.items()})
        else:
            values[KEYS[k]] = v["数值"]
    current = None
    delta = 0
    files = set()
    for line in (root / "smell-patch" / level / dirname / (stub + ".patch")).read_bytes().splitlines():
        header = HEADER.match(line)
        if header:
            current = header[1].decode()
            files.add(current)
        elif current == target:
            hunk = HUNK.match(line)
            if hunk:
                delta += int(hunk[4] or 1) - int(hunk[2] or 1)
    assert target in files
    test_path = root / "smell-patch" / level / dirname / (stub + "-test.patch")
    values.update(
        target_file_delta=delta,
        cross_file_move=int(smell == "FE" and source != target and source in files),
        adapted_tests=int(test_path.is_file()),
    )
    return values


@dataclass(frozen=True)
class Window:
    offset: int
    limit: int | None
    line: int
    ranges: tuple
    chars: int
    file_lines: int | None

    def contains(self, line):
        return any(lo <= line <= hi for lo, hi in self.ranges)


def read_window(args, output, trace_line):
    groups = []
    chars = 0
    content = output.partition("<content>")[2].partition("</content>")[0]
    for match in NUMBERED.finditer(content):
        n = int(match[1])
        chars += len(match[2])
        if groups and n == groups[-1][1] + 1:
            groups[-1][1] = n
        else:
            groups.append([n, n])
    if not groups:
        return None
    total = FILE_TOTAL.search(content)
    return Window(
        args.get("offset", 1),
        args.get("limit"),
        trace_line,
        tuple(map(tuple, groups)),
        chars,
        int(total[1] or total[2]) if total else None,
    )


@lru_cache(maxsize=None)
def single_hunk_fix(path):
    """A pure insertion is anchored on the preceding original line."""
    if not path.exists():
        return None
    files = []
    hunks = 0
    anchor = None
    old = 0
    delta = []
    for line in path.read_bytes().splitlines():
        header = HEADER.match(line)
        if header:
            files.append(header[1].decode())
            if len(files) > 1:
                return None
            continue
        h = HUNK.match(line)
        if h:
            hunks += 1
            old = int(h[1])
            if hunks > 1:
                return None
        elif hunks and line.startswith((b"+", b"-")):
            if anchor is None:
                anchor = old if line[:1] == b"-" else max(1, old - 1)
            delta.append(line)
            old += line[:1] == b"-"
        elif hunks and line.startswith(b" "):
            old += 1
    if not files or hunks != 1 or anchor is None:
        return None
    return files[0], hashlib.sha256(b"\n".join(delta)).digest(), anchor


def paired_reads(b, v, meta, base_dir, var_dir, explicit, changed_paths):
    target, source = meta["target"], meta["source"]
    result = {}
    bs, vs = b.windows.get(target, ()), v.windows.get(target, ())
    paths = (source, target) if meta["cross_file_move"] else (target,)
    matcher = explicit(paths)
    for prefix, run, windows in [("b_", b, bs), ("v_", v, vs)]:
        found = set()
        for shell, arg, _ in run.reads:
            if shell:
                found.update(m["path"] for m in matcher.finditer(arg))
            elif arg.removeprefix("./") in paths:
                found.add(arg.removeprefix("./"))
        w = windows[0] if windows else None
        result.update(
            {
                prefix + "target_queried": int(target in found),
                prefix + "both_owners": int(source in found and target in found)
                if meta["cross_file_move"]
                else None,
                prefix + "target_windows": len(windows),
                prefix + "target_offsets": len({a.offset for a in windows}),
                prefix + "first_target_line": w.line if w else None,
                prefix + "first_target_chars": w.chars if w else None,
                prefix + "first_target_file_lines": w.file_lines if w else None,
            }
        )
    same = bool(bs and vs and (bs[0].offset, bs[0].limit) == (vs[0].offset, vs[0].limit))
    result["same_first_request"] = int(same)
    result["same_open_request"] = int(same and bs[0].offset == 1 and bs[0].limit is None)
    result["same_bounded_request"] = int(same and bs[0].limit is not None)
    result.update(comparison_file=None, b_comparison_chars=None, v_comparison_chars=None)
    if same and not meta["adapted_tests"]:
        candidates = []
        for path in b.windows.keys() & v.windows.keys():
            if path in changed_paths:
                continue
            left, right = b.windows[path][0], v.windows[path][0]
            if (left.offset, left.limit) != (right.offset, right.limit):
                continue
            if (left.limit is None) != (bs[0].limit is None):
                continue
            if left.chars and right.chars:
                candidates.append((left.line, path, left.chars, right.chars))
        if candidates:
            _, path, left, right = min(candidates)
            result.update(comparison_file=path, b_comparison_chars=left, v_comparison_chars=right)
    first, second = single_hunk_fix(base_dir / "patch.diff"), single_hunk_fix(var_dir / "patch.diff")
    same_fix = bool(first and second and first[:2] == second[:2] and first[0] == target)
    result["same_target_single_fix"] = int(same_fix)
    for prefix, fix, wins in [("b_", first, bs), ("v_", second, vs)]:
        result[prefix + "fix_anchor"] = fix[2] if same_fix else None
        result[prefix + "first_window_hit"] = (
            int(wins[0].contains(fix[2])) if same_fix and wins else None
        )
    return result
