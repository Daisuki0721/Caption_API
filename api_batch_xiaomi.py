#!/usr/bin/env python3
"""使用小米 LLM 网关和 Gemini 3.5 Flash 批量分析本地视频。"""

import argparse
import base64
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path


API_URL = "https://api.llm.mioffice.cn/v1/chat/completions"
MODEL = "vertex_ai/gemini-3.5-flash"
TARGET_FPS = 10
TARGET_HEIGHT = 480
MEDIA_RESOLUTION = "default"
VIDEO_EXTENSIONS = ("*.mp4", "*.avi", "*.mov", "*.mkv", "*.webm")


def parse_args():
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Gemini 3.5 Flash 批量视频推理（固定 480p / 10fps）"
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=script_dir / "assets",
        help="视频目录（默认：脚本目录下的 assets）",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        default=script_dir / "prompt.txt",
        help="提示词文件（默认：脚本目录下的 prompt.txt）",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=script_dir / "results",
        help="结果目录（默认：脚本目录下的 results）",
    )
    parser.add_argument(
        "--max-completion-tokens",
        type=int,
        default=4096,
        help="最大输出 Token 数（默认：4096）",
    )
    parser.add_argument(
        "--output-format",
        choices=("auto", "json", "text"),
        default="auto",
        help="输出格式；auto 会根据 prompt 是否包含 json 判断",
    )
    return parser.parse_args()


def require_commands():
    missing = [name for name in ("ffmpeg", "ffprobe", "curl") if not shutil.which(name)]
    if missing:
        raise EnvironmentError(
            f"缺少系统命令：{', '.join(missing)}。请先按 README_xiaomi.md 安装。"
        )


def get_api_key():
    api_key = os.getenv("DASHSCOPE_API_KEY_XIAOMI") or os.getenv("LLM_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "未设置 API Key，请设置 DASHSCOPE_API_KEY_XIAOMI 或 LLM_API_KEY"
        )
    return api_key


def find_videos(source_dir):
    videos = []
    for pattern in VIDEO_EXTENSIONS:
        videos.extend(glob.glob(str(source_dir / pattern)))
        videos.extend(glob.glob(str(source_dir / pattern.upper())))
    return sorted({Path(path).resolve() for path in videos})


def probe_video(video_path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate",
            "-of",
            "json",
            str(video_path),
        ],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 检查失败: {result.stderr.strip()}")
    stream = json.loads(result.stdout)["streams"][0]
    numerator, denominator = map(int, stream["avg_frame_rate"].split("/"))
    fps = numerator / denominator if denominator else 0
    return stream["width"], stream["height"], fps


def video_to_data_url(video_path):
    """转码为 480p/10fps MP4，并返回 Base64 Data URL。"""
    with tempfile.TemporaryDirectory(prefix="gemini-video-") as temp_dir:
        output_path = Path(temp_dir) / "video.mp4"
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(video_path),
                "-vf",
                f"fps={TARGET_FPS},scale=-2:{TARGET_HEIGHT}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "28",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-movflags",
                "+faststart",
                str(output_path),
            ],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"视频转码失败: {result.stderr.strip()}")

        width, height, fps = probe_video(output_path)
        if height != TARGET_HEIGHT or abs(fps - TARGET_FPS) > 0.01:
            raise RuntimeError(
                f"转码校验失败：得到 {width}x{height} @ {fps:.2f}fps，"
                f"预期高度 {TARGET_HEIGHT}px @ {TARGET_FPS}fps"
            )

        encoded = base64.b64encode(output_path.read_bytes()).decode("ascii")
        size_mb = output_path.stat().st_size / 1024 / 1024
        return f"data:video/mp4;base64,{encoded}", width, height, fps, size_mb


def post_chat_completion(api_key, request_id, payload):
    """通过 curl 调用网关，规避本机 httpx 与网关的 TLS 兼容问题。"""
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "20",
        "--max-time",
        "300",
        "--request",
        "POST",
        API_URL,
        "--header",
        f"Authorization: Bearer {api_key}",
        "--header",
        f"X-Model-Request-Id: {request_id}",
        "--header",
        "Content-Type: application/json",
        "--data-binary",
        "@-",
        "--write-out",
        "\n%{http_code}",
    ]
    request_body = json.dumps(payload, ensure_ascii=False)

    for attempt in range(1, 4):
        result = subprocess.run(
            command,
            input=request_body,
            text=True,
            capture_output=True,
        )
        if result.returncode == 0:
            body, separator, status_text = result.stdout.rpartition("\n")
            if not separator or not status_text.isdigit():
                raise RuntimeError("接口响应中缺少 HTTP 状态码")
            status_code = int(status_text)
            if not 200 <= status_code < 300:
                raise RuntimeError(f"接口返回 HTTP {status_code}: {body}")
            try:
                return json.loads(body)
            except json.JSONDecodeError as error:
                raise RuntimeError(f"接口返回的内容不是有效 JSON: {error}") from error

        if attempt == 3:
            raise RuntimeError(f"curl 请求失败: {result.stderr.strip()}")
        wait_seconds = attempt * 2
        print(f"  [Retry] 网络异常，{wait_seconds} 秒后第 {attempt + 1} 次尝试...")
        time.sleep(wait_seconds)


def build_payload(video_data_url, prompt, max_completion_tokens):
    return {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful AI assistant.",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        "video_url": {"url": video_data_url},
                        "fps": TARGET_FPS,
                        "media_resolution": MEDIA_RESOLUTION,
                    },
                    {"type": "text", "text": prompt},
                ],
            },
        ],
        "max_completion_tokens": max_completion_tokens,
    }


def save_result(results_dir, base_name, raw_content, json_mode):
    if json_mode:
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", raw_content.strip(), flags=re.IGNORECASE
        ).strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            parsed = {"raw_result": cleaned}
        if isinstance(parsed, dict):
            parsed = {**parsed, "video": base_name}
        else:
            parsed = {"video": base_name, "result": parsed}
        content = json.dumps(parsed, ensure_ascii=False, indent=2) + "\n"
        output_path = results_dir / f"{base_name}.json"
    else:
        content = f"Video: {base_name}\n{'=' * 40}\n{raw_content.strip()}\n"
        output_path = results_dir / f"{base_name}.txt"

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=results_dir,
        prefix=f".{base_name}.",
        delete=False,
    ) as temp_file:
        temp_file.write(content)
        temp_path = Path(temp_file.name)
    os.replace(temp_path, output_path)
    output_path.chmod(0o644)
    return output_path


def append_history(history_file, prompt_tokens, completion_tokens, success_count):
    history_in = 0
    history_out = 0
    if history_file.exists():
        content = history_file.read_text(encoding="utf-8")
        input_matches = re.findall(r"历史总计消耗 Input Tokens:\s*(\d+)", content)
        output_matches = re.findall(r"历史总计消耗 Output Tokens:\s*(\d+)", content)
        if input_matches:
            history_in = int(input_matches[-1])
        if output_matches:
            history_out = int(output_matches[-1])

    with history_file.open("a", encoding="utf-8") as file:
        file.write(
            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 自动化顺序任务 "
            f"({MODEL}) (成功: {success_count} 个)\n"
        )
        file.write(f"  本次消耗 - Input: {prompt_tokens}, Output: {completion_tokens}\n")
        file.write(f"  历史总计消耗 Input Tokens: {history_in + prompt_tokens}\n")
        file.write(
            f"  历史总计消耗 Output Tokens: {history_out + completion_tokens}\n"
        )
        file.write("-" * 50 + "\n")


def main():
    args = parse_args()
    require_commands()
    api_key = get_api_key()

    source_dir = args.source_dir.expanduser().resolve()
    prompt_path = args.prompt.expanduser().resolve()
    results_dir = args.results_dir.expanduser().resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"视频目录不存在: {source_dir}")
    if not prompt_path.is_file():
        raise FileNotFoundError(f"提示词文件不存在: {prompt_path}")
    if args.max_completion_tokens <= 0:
        raise ValueError("--max-completion-tokens 必须大于 0")

    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"提示词文件不能为空: {prompt_path}")
    json_mode = (
        "json" in prompt.lower()
        if args.output_format == "auto"
        else args.output_format == "json"
    )

    videos = find_videos(source_dir)
    if not videos:
        raise FileNotFoundError(f"在 {source_dir} 中未找到视频文件")
    results_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"\n[配置] 模型={MODEL}, 视频={TARGET_HEIGHT}p/{TARGET_FPS}fps, "
        f"media_resolution={MEDIA_RESOLUTION}"
    )
    print(f"[数据准备] 扫描到 {len(videos)} 个视频文件")

    prompt_tokens = 0
    completion_tokens = 0
    success_count = 0
    failed_count = 0

    for index, video_path in enumerate(videos, start=1):
        base_name = video_path.stem
        print(f"\n[{index}/{len(videos)}] 正在转码: {video_path.name}")
        try:
            data_url, width, height, fps, size_mb = video_to_data_url(video_path)
            print(
                f"  -> 转码完成: {width}x{height} @ {fps:.2f}fps, {size_mb:.2f} MB"
            )
            payload = build_payload(data_url, prompt, args.max_completion_tokens)
            request_id = str(uuid.uuid4())
            print(f"[{datetime.now():%H:%M:%S}] 正在调用 {MODEL}...")
            response = post_chat_completion(api_key, request_id, payload)
            choice = response["choices"][0]
            raw_content = choice["message"].get("content")
            if not raw_content or not raw_content.strip():
                raise RuntimeError(
                    f"模型返回空内容（finish_reason={choice.get('finish_reason', 'unknown')}）"
                )

            output_path = save_result(
                results_dir, base_name, raw_content, json_mode
            )
            usage = response.get("usage") or {}
            prompt_tokens += usage.get("prompt_tokens", 0) or 0
            completion_tokens += usage.get("completion_tokens", 0) or 0
            success_count += 1
            print(f"  -> 推理完成: {output_path}")
        except Exception as error:
            failed_count += 1
            print(f"  [Error] {base_name} 失败: {error}")

    history_file = Path(__file__).resolve().parent / "consume-history.txt"
    append_history(
        history_file,
        prompt_tokens,
        completion_tokens,
        success_count,
    )
    print(f"\n[完成] 成功 {success_count} 个，失败 {failed_count} 个")
    if failed_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
