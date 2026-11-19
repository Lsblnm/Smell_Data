"""Assemble directly reusable v1 patches & intros into a v2 directory layout (smell-patch-v2 / smell-patch-intro-v2)."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SMELL_DIR = {"FE": "FeatureEnvy", "GC": "GodClass", "LM": "LongMethod"}


def link_or_copy(src: Path, dst: Path, mode: str):
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if mode == "copy":
        shutil.copy2(src, dst)
    else:
        rel = os.path.relpath(src, dst.parent)
        dst.symlink_to(rel)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-root", type=Path, default=HERE / "assembled_v2",
                    help="Target directory for assembled smell-patch-v2 and smell-patch-intro-v2")
    ap.add_argument("--mode", choices=["symlink", "copy"], default="symlink")
    ap.add_argument("--clean-only", action="store_true",
                    help="Exclude the 65 tasks with observed upstream PR/commit access")
    args = ap.parse_args()

    plan = pd.read_csv(HERE / "manifests" / "v2_code_smell_remap_plan.csv")
    reused = plan[plan.action == "REUSE"].copy()
    if args.clean_only:
        reused = reused[~reused.upstream_leak]

    n_patch = n_gold = n_test = n_intro = 0
    for r in reused.itertuples():
        dname = SMELL_DIR[r.smell]
        stub = f"{r.task}-{r.smell}"
        old_lv = r.reused_from_v1
        new_lv = r.new_level

        src_dir = ROOT / "smell-patch" / old_lv / dname
        dst_dir = args.out_root / "smell-patch" / new_lv / dname
        if link_or_copy(src_dir / f"{stub}.patch", dst_dir / f"{stub}.patch", args.mode):
            n_patch += 1
        if link_or_copy(src_dir / f"{stub}-gold.patch", dst_dir / f"{stub}-gold.patch", args.mode):
            n_gold += 1
        if link_or_copy(src_dir / f"{stub}-test.patch", dst_dir / f"{stub}-test.patch", args.mode):
            n_test += 1

        src_intro = ROOT / "smell-patch-intro" / old_lv / dname / f"{stub}.json"
        dst_intro = args.out_root / "smell-patch-intro" / new_lv / dname / f"{stub}.json"
        if link_or_copy(src_intro, dst_intro, args.mode):
            n_intro += 1

    print(f"Assembled into {args.out_root} ({args.mode}): "
          f"{n_patch} smell patches, {n_gold} gold patches, {n_test} test patches, {n_intro} intro JSONs.")


if __name__ == "__main__":
    main()
