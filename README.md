# 批量视频推理工具

> 小米 LLM 网关 + Gemini 3.5 Flash（固定 480p/10fps）的使用方式，
> 请查看 [README_xiaomi.md](README_xiaomi.md)。

基于阿里云百炼 DashScope Batch API，对本地视频批量进行 Qwen3.5-Omni 多模态推理，成本仅为实时推理的 50%。

## 环境准备

### 1. 安装依赖

```bash
# 创建 conda 环境
conda env create -f environment.yml
conda activate api

# 额外系统依赖（需手动安装）
# macOS
brew install ffmpeg cloudflared

# Ubuntu/Debian
sudo apt install ffmpeg
# cloudflared 安装: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
```

### 2. 设置 API Key

```bash
export DASHSCOPE_API_KEY="your-api-key"
```

获取 Key：https://www.alibabacloud.com/help/zh/model-studio/get-api-key

---

## 运行前准备（重要！）

以下三样东西**必须手动准备好**，脚本不会自动创建：

### ① 修改脚本中的视频源路径

打开 `api_batch.py`，修改第 73 行的 `source_dir`，指向你存放视频的目录：

```python
source_dir = "/path/to/your/videos"  # 改为你的路径
```

### ② 创建 `prompt.txt`

在脚本同级目录创建，写入你要对每个视频提出的问题，例如：

```
请用中文描述这段视频的内容，包括场景、人物、动作和关键事件。
```

如果 prompt 中包含 `json` 字样，脚本会自动以 JSON 模式请求并输出 `.json` 结果文件；否则输出 `.txt`。

### ③ 创建 `config.yaml`

在脚本同级目录创建，内容为模型定价（用于费用统计，实际扣费以阿里云为准）：

```yaml
models:
  qwen3.5-omni-plus:
    input_video_price_per_1m: 7.0
    input_audio_price_per_1m: 53.0
    output_text_price_per_1m: 40.0
```

---

## 运行

```bash
conda activate api
python api_batch.py
```

## 运行时会自动创建的内容

| 文件/目录 | 说明 |
|-----------|------|
| `public/` | 临时目录，存放压缩后的视频，通过 Cloudflare 隧道对外暴露。脚本退出后视频文件自动删除，**目录保留** |
| `results/` | 推理结果输出目录。JSON 模式下输出 `{视频名}.json`，否则输出 `{视频名}.txt` |
| `batch_input.jsonl` | 上传至阿里云的临时任务文件，脚本退出后自动删除 |
| `consume-history.txt` | 费用累计记录，每次运行追加写入，不会被删除 |

---

## 工作流程

```
本地视频目录
    │
    ├─ ffmpeg 压缩/转码 → public/ 目录
    │
    ├─ cloudflared 启动公网隧道 → 视频获得临时 HTTPS URL
    │
    ├─ 生成 JSONL 任务文件 → 上传至阿里云 Batch API
    │
    ├─ 轮询等待任务完成（异步，最长等待 24 小时）
    │
    └─ 下载结果 → 写入 results/ 目录，更新消费记录
```

## 注意事项

- **网络要求**：脚本通过 `cloudflared` 创建临时公网隧道，确保网络能访问 Cloudflare（会自动选择最优节点）。
- **视频处理**：所有视频会被 `ffmpeg` 强制转为 480p、10fps 的 MP4 文件，且最多截取前 60 秒。超过 60 秒的视频只分析前段。
- **任务时长**：Batch 任务最长等待时间为 24 小时。脚本会每 30 秒轮询一次状态，期间**隧道必须保持开启**——不要提前关闭终端。
- **Ctrl+C 中断**：脚本注册了 `atexit` 清理逻辑，中断后会依次关闭隧道、删除临时文件。
- **费用**：Batch 推理按实时价格的 50% 计费，具体取决于输入音视频 Token 和输出文本 Token。每次运行结束后会在 `consume-history.txt` 追加本次和累计费用。
- **模型**：当前使用 `qwen3.5-omni-plus`，北京地域 MaaS 端点。如需切换地域或模型，修改脚本中的 `base_url` 和 `body["model"]`。
- **结果格式**：JSON 模式下，每个结果文件会追加 `"video"` 字段标明来源视频文件名；非 JSON 模式直接输出模型回复原文。
