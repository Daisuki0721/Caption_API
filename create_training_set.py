#!/usr/bin/env python3
"""Randomly build a first-batch video training set from approved annotations."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from tqdm import tqdm


FFMPEG_CORES_PER_TASK = 8
RESERVED_CPU_CORES = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "从 videos_anno.jsonl 中随机抽取 passed=true 的视频，复制原片并生成 "
            "10fps/480p 的备用打标视频。"
        )
    )
    parser.add_argument("dataset_name", help="数据集名称，同时用作输出文件夹名")
    parser.add_argument("size", type=int, help="抽取的视频数量")
    parser.add_argument(
        "--annotation",
        type=Path,
        default=Path("videos_anno.jsonl"),
        help="标注 JSONL 路径（默认：videos_anno.jsonl）",
    )
    parser.add_argument(
        "--source-list",
        type=Path,
        default=Path("videoSourceList.txt"),
        help="视频源清单路径（默认：videoSourceList.txt）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default="/mnt/vlm-ks3/chenkaijin/datasets",
        help="数据集文件夹的父目录",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="随机种子；省略时由系统随机生成并记录到 source_info.json",
    )
    return parser.parse_args()


def load_source_roots(path: Path) -> list[Path]:
    roots: list[Path] = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line and not line.startswith("#"):
                roots.append(Path(line).expanduser())
    if not roots:
        raise ValueError(f"{path} 中没有有效的视频源路径")
    return roots


def load_approved(path: Path) -> list[dict[str, str]]:
    approved: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if not raw_line.strip():
                continue
            try:
                item = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} 不是合法 JSON: {exc}") from exc
            if item.get("passed") is not True:
                continue
            video_id = item.get("id")
            folder = item.get("folder")
            if not isinstance(video_id, str) or not isinstance(folder, str):
                raise ValueError(f"{path}:{line_number} 的 passed 样本缺少字符串 id/folder")
            if Path(video_id).name != video_id or video_id in {"", ".", ".."}:
                raise ValueError(f"{path}:{line_number} 的视频 id 不是安全的文件名: {video_id!r}")
            key = (folder, video_id)
            if key not in seen:
                approved.append({"id": video_id, "folder": folder})
                seen.add(key)
    return approved


def resolve_roots(folders: set[str], listed_roots: list[Path]) -> dict[str, Path]:
    """Resolve folder labels, including unlisted siblings such as *_v2 ... *_v5."""
    resolved: dict[str, Path] = {}
    exact = {root.name: root for root in listed_roots}
    parent_dirs = {root.parent for root in listed_roots}

    for folder in folders:
        candidates: list[Path] = []
        if folder in exact:
            candidates.append(exact[folder])
        candidates.extend(parent / folder for parent in parent_dirs)

        # Keep order while removing duplicate candidates.
        unique_candidates = list(dict.fromkeys(candidates))
        for candidate in unique_candidates:
            if (candidate / "sources_extracted").is_dir():
                resolved[folder] = candidate
                break
    return resolved


def safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "video"


def discover_available_videos(
    approved: list[dict[str, str]], roots: dict[str, Path]
) -> tuple[list[dict[str, Any]], Counter[Path], dict[str, int]]:
    """Find every approved clip that actually exists before sampling anything."""
    available: list[dict[str, Any]] = []
    valid_counts: Counter[Path] = Counter()
    skipped = {"unresolved_folder": 0, "missing_file": 0}

    for item in tqdm(approved, desc="扫描有效切片", unit="个", dynamic_ncols=True):
        root = roots.get(item["folder"])
        if root is None:
            skipped["unresolved_folder"] += 1
            continue
        source = root / "sources_extracted" / item["id"]
        if not source.is_file():
            skipped["missing_file"] += 1
            continue

        available.append(
            {
                "id": item["id"],
                "folder": item["folder"],
                "source_dataset": str(root),
                "original_path": str(source),
            }
        )
        valid_counts[root] += 1
    return available, valid_counts, skipped


def assign_output_names(selected: list[dict[str, Any]]) -> None:
    """Assign collision-free output names after the global random draw."""
    used_names: set[str] = set()
    for item in selected:
        output_name = Path(item["id"]).name
        if output_name in used_names:
            output_name = f"{safe_component(item['folder'])}__{output_name}"
        suffix = 2
        base_name = output_name
        while output_name in used_names:
            stem, ext = os.path.splitext(base_name)
            output_name = f"{stem}__{suffix}{ext}"
            suffix += 1
        used_names.add(output_name)
        item["output_name"] = output_name


def print_source_statistics(
    listed_roots: list[Path], root_map: dict[str, Path], valid_counts: Counter[Path]
) -> None:
    """Print listed and inferred source paths with their usable clip counts."""
    listed_set = set(listed_roots)
    print("\n视频来源与有效切片统计：")
    for root in listed_roots:
        extracted_dir = root / "sources_extracted"
        status = "" if extracted_dir.is_dir() else "（目录不存在）"
        print(f"  {extracted_dir}: {valid_counts[root]} 个 {status}")

    inferred_roots = sorted(set(root_map.values()) - listed_set, key=str)
    for root in inferred_roots:
        print(f"  {root / 'sources_extracted'}: {valid_counts[root]} 个（自动推导）")
    print(f"  合计: {sum(valid_counts.values())} 个\n")


def build_cpu_groups() -> list[tuple[int, ...]]:
    """Return disjoint 8-core groups after reserving four available CPUs."""
    if not sys.platform.startswith("linux") or not hasattr(os, "sched_getaffinity"):
        raise RuntimeError("严格 CPU 绑核仅支持 Linux，请在目标 Linux 服务器上运行")
    if shutil.which("taskset") is None:
        raise RuntimeError("找不到 taskset，请安装 util-linux 后重试")

    available_cpus = sorted(os.sched_getaffinity(0))
    worker_count = (len(available_cpus) - RESERVED_CPU_CORES) // FFMPEG_CORES_PER_TASK
    if worker_count < 1:
        raise RuntimeError(
            f"当前进程只有 {len(available_cpus)} 个可用 CPU；至少需要 "
            f"{RESERVED_CPU_CORES + FFMPEG_CORES_PER_TASK} 个"
        )

    usable_cpus = available_cpus[RESERVED_CPU_CORES:]
    return [
        tuple(usable_cpus[index * FFMPEG_CORES_PER_TASK : (index + 1) * FFMPEG_CORES_PER_TASK])
        for index in range(worker_count)
    ]


def format_cpu_list(cpu_ids: tuple[int, ...]) -> str:
    return ",".join(str(cpu_id) for cpu_id in cpu_ids)


def transcode(source: Path, destination: Path, cpu_ids: tuple[int, ...]) -> None:
    command = [
        "taskset",
        "--cpu-list",
        format_cpu_list(cpu_ids),
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-filter_threads",
        str(FFMPEG_CORES_PER_TASK),
        "-i",
        str(source),
        "-vf",
        "fps=10,scale=-2:480",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "23",
        "-threads",
        str(FFMPEG_CORES_PER_TASK),
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    subprocess.run(command, check=True)


def transcode_batch(
    items: list[dict[str, Any]],
    sources_dir: Path,
    caption_dir: Path,
    cpu_ids: tuple[int, ...],
    progress: tqdm[Any],
) -> list[str]:
    """Process one queue sequentially on one exclusive CPU group."""
    errors: list[str] = []
    for item in items:
        try:
            transcode(
                sources_dir / item["output_name"],
                caption_dir / item["output_name"],
                cpu_ids,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            errors.append(f"{item['output_name']}: {exc}")
        finally:
            progress.update(1)
    return errors


def main() -> int:
    args = parse_args()
    if args.size <= 0:
        raise ValueError("size 必须大于 0")
    if (
        not args.dataset_name
        or Path(args.dataset_name).name != args.dataset_name
        or args.dataset_name in {".", ".."}
    ):
        raise ValueError("dataset_name 必须是单个安全的文件夹名称，不能包含路径")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("找不到 ffmpeg，请先安装并确保它位于 PATH 中")
    cpu_groups = build_cpu_groups()

    annotation = args.annotation.resolve()
    source_list = args.source_list.resolve()
    dataset_dir = (args.output_dir / args.dataset_name).resolve()
    if dataset_dir.exists():
        raise FileExistsError(f"输出目录已存在，为避免覆盖已停止：{dataset_dir}")

    roots = load_source_roots(source_list)
    approved = load_approved(annotation)
    if args.size > len(approved):
        raise ValueError(f"要求 {args.size} 条，但标注中只有 {len(approved)} 条通过样本")

    root_map = resolve_roots({item["folder"] for item in approved}, roots)
    available, valid_counts, skipped = discover_available_videos(approved, root_map)
    print_source_statistics(roots, root_map, valid_counts)
    if len(available) < args.size:
        unresolved = sorted({item["folder"] for item in approved} - root_map.keys())
        raise RuntimeError(
            f"只能找到 {len(available)} 个可用的通过视频，少于要求的 {args.size} 个。"
            f"未解析的数据集：{unresolved or '无'}；不存在的视频数：{skipped['missing_file']}。"
            "请检查 videoSourceList.txt 和各路径下的 sources_extracted 文件夹。"
        )

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**63)
    rng = random.Random(seed)
    rng.shuffle(available)
    selected = available[: args.size]
    assign_output_names(selected)

    sources_dir = dataset_dir / "sources"
    caption_dir = dataset_dir / "caption"
    sources_dir.mkdir(parents=True)
    caption_dir.mkdir()

    print(f"随机种子: {seed}")
    for item in tqdm(selected, desc="复制原始视频", unit="个", dynamic_ncols=True):
        shutil.copy2(item["original_path"], sources_dir / item["output_name"])

    worker_count = len(cpu_groups)
    print(
        f"使用 {worker_count} 个 ffmpeg 进程生成 10fps/480p 视频；"
        f"每个进程固定使用 {FFMPEG_CORES_PER_TASK} 个独立 CPU 核心"
    )
    for index, cpu_ids in enumerate(cpu_groups, 1):
        print(f"  进程组 {index}: CPU {format_cpu_list(cpu_ids)}")

    batches = [selected[index::worker_count] for index in range(worker_count)]
    errors: list[str] = []
    with tqdm(total=len(selected), desc="ffmpeg 转码", unit="个", dynamic_ncols=True) as progress:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [
                executor.submit(
                    transcode_batch,
                    batch,
                    sources_dir,
                    caption_dir,
                    cpu_ids,
                    progress,
                )
                for batch, cpu_ids in zip(batches, cpu_groups)
                if batch
            ]
            for future in as_completed(futures):
                errors.extend(future.result())
    if errors:
        raise RuntimeError("以下视频转码失败：\n" + "\n".join(errors))

    manifest = {
        "dataset_name": args.dataset_name,
        "size": len(selected),
        "seed": seed,
        "annotation_file": str(annotation),
        "source_list_file": str(source_list),
        "available_video_count": len(available),
        "available_by_source": {
            str(root / "sources_extracted"): valid_counts[root]
            for root in sorted(valid_counts, key=str)
        },
        "caption_format": {"fps": 10, "height": 480, "video_codec": "h264"},
        "cpu_allocation": {
            "reserved_cores": RESERVED_CPU_CORES,
            "cores_per_ffmpeg": FFMPEG_CORES_PER_TASK,
            "ffmpeg_processes": worker_count,
            "core_groups": [list(cpu_ids) for cpu_ids in cpu_groups],
        },
        "videos": selected,
    }
    manifest_path = dataset_dir / "source_info.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(f"完成：{dataset_dir}")
    print(f"来源信息：{manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1)
