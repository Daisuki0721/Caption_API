# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a test/exploration project for **Alibaba Cloud DashScope Model Studio API** (阿里云百炼), using the **Qwen3.5-Omni** multimodal model via an OpenAI-compatible SDK interface.

## Running the Code

```bash
# Requires: DASHSCOPE_API_KEY environment variable
export DASHSCOPE_API_KEY="your-api-key"
python api.py
```

There is no dependency file; install as needed:
```bash
pip install openai
```

## Architecture

Single-script API client (`api.py`) with supporting config and reference files. No framework, no tests, no build system.

### Files

- **`api.py`** — Main script. Initializes an OpenAI client pointed at the DashScope Beijing MaaS endpoint (`ws-9eaupaeyp0hh6lcp.cn-beijing.maas.aliyuncs.com`), calls `qwen3.5-omni-plus` with streaming, and prints chunk deltas. The `stream` parameter **must** be `True` for this endpoint/model — non-streaming calls will error.
- **`config.yaml`** — Pricing reference for the `qwen3.5-omni-plus` model (video/audio input, text output per 1M tokens).
- **`md.txt`** — Full API parameter reference for the DashScope chat completions endpoint (messages structure, multimodal input format, audio output, thinking/reasoning controls, tool calling, search, etc.). This is the authoritative documentation file for this API.
- **`assets/sea.mp4`** — Sample video file (~12MB) for testing multimodal (video) input capabilities.

### Key API Details

- **Base URL**: `https://ws-9eaupaeyp0hh6lcp.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` (Beijing region)
- **Model**: `qwen3.5-omni-plus` — supports text, image, audio, and video inputs; can output text and audio
- **Auth**: API key via `DASHSCOPE_API_KEY` environment variable. Obtain keys from [Alibaba Cloud Model Studio](https://www.alibabacloud.com/help/zh/model-studio/get-api-key).
- **Non-OpenAI-standard parameters** (e.g., `enable_thinking`, `thinking_budget`, `enable_search`, `vl_high_resolution_images`) must be passed via `extra_body` in the OpenAI SDK. See `md.txt` for full details.
- Different regions (Singapore vs Beijing) use different API keys.
