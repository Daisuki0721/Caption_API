# Gemini 3.5 Flash 批量视频推理

该工程通过小米 LLM 网关，固定使用 `vertex_ai/gemini-3.5-flash`
分析本地视频。每个视频会在上传前转码为 **480p、10fps、H.264 MP4**，
请求中也会显式设置 `"fps": 10`。

## 环境要求

- Python 3.10+
- `ffmpeg` / `ffprobe`
- `curl`
- 小米 LLM API Key

macOS 安装系统依赖：

```bash
brew install ffmpeg
```

脚本仅使用 Python 标准库，不需要额外安装 pip 包。

## 配置 API Key

脚本依次读取：

1. `DASHSCOPE_API_KEY_XIAOMI`
2. `LLM_API_KEY`

例如在 `~/.zshrc` 中：

```bash
export LLM_API_KEY="your-key"
```

修改后重新打开终端，或执行：

```bash
source ~/.zshrc
```

## 准备输入

- 将视频放入 `assets/`
- 将提示词写入 `prompt.txt`
- 提示词包含 `json`（不区分大小写）时，默认输出 JSON；否则输出文本

支持 `.mp4`、`.avi`、`.mov`、`.mkv` 和 `.webm`。

## 运行

在当前目录执行：

```bash
python api_batch_xiaomi.py
```

指定自定义目录：

```bash
python api_batch_xiaomi.py \
  --source-dir /path/to/videos \
  --prompt /path/to/prompt.txt \
  --results-dir /path/to/results
```

强制输出 JSON：

```bash
python api_batch_xiaomi.py --output-format json
```

查看完整参数：

```bash
python api_batch_xiaomi.py --help
```

## 固定推理配置

| 配置 | 值 |
|---|---|
| 模型 | `vertex_ai/gemini-3.5-flash` |
| 转码分辨率 | 高度 480px，等比缩放 |
| 转码帧率 | 10fps |
| API 视频采样帧率 | 10fps |
| API `media_resolution` | `default` |
| 视频编码 | H.264 + AAC |
| 上传方式 | Base64 Data URL |

`media_resolution` 是网关枚举，不接受 `"640x480"`；物理 480p 由 FFmpeg
预处理保证。

## 输出

- 推理结果：`results/<视频名>.json` 或 `.txt`
- Token 记录：`consume-history.txt`
- 任一视频失败时，进程退出码为 `1`

脚本会用临时文件完成转码，退出后自动删除，不需要 Cloudflare 隧道。
