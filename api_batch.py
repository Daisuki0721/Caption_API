#!/usr/bin/env python3
"""Batch-submit local videos to DashScope through a temporary public tunnel."""

import argparse
import atexit
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from openai import OpenAI
import yaml

ROOT_DIR = Path(__file__).resolve().parent
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
server_process: subprocess.Popen | None = None
tunnel_process: subprocess.Popen | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT_DIR / "assets")
    parser.add_argument("--prompt", type=Path, default=ROOT_DIR / "prompt.txt")
    parser.add_argument("--config", type=Path, default=ROOT_DIR / "config.yaml")
    parser.add_argument("--results-dir", type=Path, default=ROOT_DIR / "results")
    parser.add_argument("--public-dir", type=Path, default=ROOT_DIR / "public")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def cleanup_processes() -> None:
    for process in (tunnel_process, server_process):
        if process and process.poll() is None:
            process.terminate()


atexit.register(cleanup_processes)


def start_tunnel(public_dir: Path, port: int) -> str:
    global server_process, tunnel_process
    server_process = subprocess.Popen([sys.executable, "-m", "http.server", str(port)], cwd=public_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tunnel_process = subprocess.Popen(["cloudflared", "tunnel", "--url", f"http://localhost:{port}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        line = tunnel_process.stdout.readline() if tunnel_process.stdout else ""
        match = re.search(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)", line)
        if match:
            return match.group(1)
        if not line and tunnel_process.poll() is not None:
            break
    raise TimeoutError("Could not obtain a Cloudflare tunnel URL within 30 seconds.")


def transcode(source: Path, destination: Path) -> bool:
    command = ["ffmpeg", "-y", "-i", str(source), "-t", "60", "-vf", "scale=-2:480", "-r", "10", "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-ac", "2", "-b:a", "128k", "-f", "mp4", str(destination)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        print(f"Skipping {source.name}: ffmpeg failed: {result.stderr.strip()}")
        return False
    return True


def render_template(value: object, **variables: str) -> object:
    if isinstance(value, str):
        return value.format(**variables)
    if isinstance(value, list):
        return [render_template(item, **variables) for item in value]
    if isinstance(value, dict):
        return {key: render_template(item, **variables) for key, item in value.items()}
    return value


def write_result(content: str, request_id: str, json_mode: bool, results_dir: Path) -> None:
    if not json_mode:
        (results_dir / f"{request_id}.txt").write_text(content.strip() + "\n", encoding="utf-8")
        return
    cleaned = re.sub(r"^```json\s*|\s*```$", "", content.strip()).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        payload = {"video": request_id, "raw_result": cleaned}
    else:
        payload["video"] = request_id
    (results_dir / f"{request_id}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    for command in ("ffmpeg", "cloudflared"):
        if not shutil.which(command):
            raise EnvironmentError(f"Required command not found: {command}")
    if not args.source_dir.is_dir():
        raise FileNotFoundError(f"Source directory not found: {args.source_dir}")
    if not args.prompt.is_file() or not args.config.is_file():
        raise FileNotFoundError("Both --prompt and --config must point to existing files.")
    prompt = args.prompt.read_text(encoding="utf-8").strip()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    api_config = config["api"]
    batch_config = config["batch"]
    json_mode = "json" in prompt.lower()
    videos = sorted(path for path in args.source_dir.iterdir() if path.suffix.lower() in VIDEO_EXTENSIONS)
    if not videos:
        raise FileNotFoundError(f"No supported video files found in {args.source_dir}")
    args.public_dir.mkdir(parents=True, exist_ok=True)
    args.results_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=os.getenv("DASHSCOPE_API_KEY"), base_url=api_config["base_url"])
    temporary_files: list[Path] = []
    input_path = ROOT_DIR / "batch_input.jsonl"
    try:
        base_url = start_tunnel(args.public_dir, args.port)
        requests = []
        for video in videos:
            filename = f"batch_{video.stem}.mp4"
            public_path = args.public_dir / filename
            temporary_files.append(public_path)
            if not transcode(video, public_path):
                continue
            body = render_template(copy.deepcopy(batch_config["request"]["body"]), video_url=f"{base_url}/{filename}", prompt=prompt)
            if json_mode:
                body["response_format"] = batch_config["json_response_format"]
            requests.append({"custom_id": video.stem, **batch_config["request"], "body": body})
        if not requests:
            raise RuntimeError("No valid batch requests were generated.")
        input_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in requests) + "\n", encoding="utf-8")
        with input_path.open("rb") as input_file:
            batch_file = client.files.create(file=input_file, purpose="batch")
        batch = client.batches.create(input_file_id=batch_file.id, endpoint=batch_config["request"]["url"], completion_window=batch_config["completion_window"])
        print(f"Batch submitted: {batch.id}")
        while batch.status not in {"completed", "failed", "expired", "cancelled"}:
            time.sleep(30)
            batch = client.batches.retrieve(batch.id)
            print(f"Batch status: {batch.status}")
        if batch.status != "completed":
            raise RuntimeError(f"Batch finished with status: {batch.status}")
        total_input_tokens = 0
        total_output_tokens = 0
        for line in client.files.content(batch.output_file_id).text.splitlines():
            record = json.loads(line)
            response = record.get("response", {}).get("body", {})
            if "choices" not in response:
                print(f"Request failed: {record['custom_id']}")
                continue
            usage = response.get("usage", {})
            total_input_tokens += usage.get("prompt_tokens", 0)
            total_output_tokens += usage.get("completion_tokens", 0)
            write_result(response["choices"][0]["message"]["content"], record["custom_id"], json_mode, args.results_dir)
        print(f"Results saved to {args.results_dir}")
        print(f"Usage: input={total_input_tokens}, output={total_output_tokens}")
    finally:
        for file_path in temporary_files:
            file_path.unlink(missing_ok=True)
        input_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
