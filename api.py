#!/usr/bin/env python3
"""Submit one public video URL to DashScope Chat Completions."""

import argparse
import copy
import json
import os
import re
import subprocess
import time
from pathlib import Path

from openai import OpenAI
import yaml

ROOT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=ROOT_DIR / "assets" / "sea.mp4")
    parser.add_argument("--prompt", type=Path, default=ROOT_DIR / "prompt.txt")
    parser.add_argument("--config", type=Path, default=ROOT_DIR / "config.yaml")
    parser.add_argument("--results-dir", type=Path, default=ROOT_DIR / "results")
    parser.add_argument("--public-dir", type=Path, default=ROOT_DIR / "public")
    parser.add_argument("--public-base-url", default=os.getenv("PUBLIC_BASE_URL"))
    return parser.parse_args()


def transcode_video(source: Path, destination: Path) -> None:
    command = ["ffmpeg", "-y", "-i", str(source), "-t", "60", "-vf", "scale=-2:480", "-r", "10", "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-ac", "2", "-b:a", "128k", str(destination)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")


def render_template(value: object, **variables: str) -> object:
    if isinstance(value, str):
        return value.format(**variables)
    if isinstance(value, list):
        return [render_template(item, **variables) for item in value]
    if isinstance(value, dict):
        return {key: render_template(item, **variables) for key, item in value.items()}
    return value


def format_response(content: str, video_name: str, json_mode: bool) -> tuple[str, str]:
    if not json_mode:
        return f"Video: {video_name}\n{'=' * 40}\n{content.strip()}\n", ".txt"
    cleaned = re.sub(r"^```json\s*|\s*```$", "", content.strip()).strip()
    try:
        response = json.loads(cleaned)
    except json.JSONDecodeError:
        response = {"video": video_name, "raw_result": cleaned}
    else:
        response["video"] = video_name
    return json.dumps(response, ensure_ascii=False, indent=2) + "\n", ".json"


def main() -> None:
    args = parse_args()
    if not args.video.is_file():
        raise FileNotFoundError(f"Video file not found: {args.video}")
    if not args.prompt.is_file() or not args.config.is_file():
        raise FileNotFoundError("Both --prompt and --config must point to existing files.")
    if not args.public_base_url:
        raise ValueError("Set --public-base-url or PUBLIC_BASE_URL.")

    prompt = args.prompt.read_text(encoding="utf-8").strip()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))["api"]
    args.public_dir.mkdir(parents=True, exist_ok=True)
    args.results_dir.mkdir(parents=True, exist_ok=True)
    public_name = f"request_{args.video.stem}.mp4"
    public_path = args.public_dir / public_name
    try:
        print(f"Transcoding {args.video.name}...")
        transcode_video(args.video, public_path)
        video_url = f"{args.public_base_url.rstrip('/')}/{public_name}"
        request = render_template(copy.deepcopy(config["request"]), video_url=video_url, prompt=prompt)
        if "json" in prompt.lower():
            request["response_format"] = config["json_response_format"]
        client = OpenAI(api_key=os.getenv("DASHSCOPE_API_KEY"), base_url=config["base_url"])
        for attempt in range(1, 4):
            try:
                completion = client.chat.completions.create(**request)
                break
            except Exception:
                if attempt == 3:
                    raise
                print(f"Request failed; retrying ({attempt}/3)...")
                time.sleep(3)
        output, suffix = format_response(completion.choices[0].message.content or "", args.video.name, "json" in prompt.lower())
        output_path = args.results_dir / f"{args.video.stem}{suffix}"
        output_path.write_text(output, encoding="utf-8")
        usage = completion.usage
        print(f"Saved result to {output_path}")
        print(f"Usage: input={usage.prompt_tokens}, output={usage.completion_tokens}")
    finally:
        public_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
