# DashScope 批量推理（Batch Inference）

对于无需实时响应的推理场景，批量推理能异步处理大批量的数据请求，成本仅为实时推理的 50%，且接口兼容 OpenAI，适合执行模型评测、数据标注等批量作业。

## 工作原理

1. **提交任务**：上传包含多个请求的 JSONL 文件，创建批量推理任务。
2. **异步处理**：系统在后台队列中处理任务。可通过控制台或 API 查询任务进度和状态。
3. **下载结果**：任务完成后，系统生成结果文件（记录成功响应）和错误文件（记录失败详情，如有）。

## 适用范围

**地域**：华北2（北京）、新加坡

### 文本生成模型

| 系列 | 模型 |
|------|------|
| 千问 Max | `qwen3.7-max`、`qwen3-max` |
| 千问 Plus | `qwen3.7-plus`、`qwen3.6-plus`、`qwen3.5-plus`、`qwen-plus`、`qwen-plus-latest` |
| 千问 Flash | `qwen3.6-flash`、`qwen3.5-flash`、`qwen-flash` |
| 千问 Long | `qwen-long`、`qwen-long-latest` |
| 第三方模型 | `deepseek-r1`、`deepseek-v3.2`、`deepseek-v3` |

### 多模态模型

| 能力 | 模型 |
|------|------|
| 图像与视频理解 | `qwen3.7-plus`、`qwen3.6-plus`、`qwen3.6-flash`、`qwen3.5-plus`、`qwen3.5-flash`、`qwen3-vl-plus`、`qwen3-vl-flash` |
| 文字提取 | `qwen-vl-ocr`、`qwen-vl-ocr-latest` |
| 全模态 | `qwen3.5-omni-plus` |

### 文本向量模型

`text-embedding-v1`、`text-embedding-v2`、`text-embedding-v3`、`text-embedding-v4`

### 重要说明

- Batch 场景下，`qwen3.7-max`、`qwen3.7-plus`、`qwen3.6-plus`、`qwen3.6-flash`、`qwen3.5-plus`、`qwen3.5-flash` 和 `qwen3.5-omni-plus` 单次请求的上下文 Token 数最大支持 **256K**。`qwen3.5-omni-plus` 不支持语音输出。
- 部分模型支持思考模式，开启后会产生思考 tokens 导致成本增加。
- `qwen3.7`、`qwen3.6` 和 `qwen3.5` 系列模型**默认开启思考模式**。建议使用混合思考模型时，显式设置 `enable_thinking` 参数（`true` 开启 / `false` 关闭）。
- 在 JSONL 请求体中，`enable_thinking` 为 `body` 的顶层参数，须与 `model` 同级传入，**不能放在 `extra_body` 中**。

---

## 步骤一：准备输入文件

创建任务前，准备一个符合以下规范的 JSONL 文件：

### 文件规范

| 项目 | 限制 |
|------|------|
| 格式 | UTF-8 编码的 JSONL（每行一个独立 JSON 对象） |
| 单文件规模 | ≤ 50,000 个请求，且 ≤ 500 MB（超出时拆分为多个任务） |
| 单行限制 | 每个 JSON 对象 ≤ 6 MB，且不超过模型上下文长度 |
| 模型一致性 | 同一文件内所有请求须使用**相同模型**及**相同思考模式** |
| 唯一标识 | 每个请求必须有文件内唯一的 `custom_id`，最大 256 字符 |

### 每行 JSON 字段

| 字段 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `custom_id` | string | 是 | 请求的唯一标识符 |
| `method` | string | 是 | HTTP 方法，仅支持 `POST` |
| `url` | string | 是 | 请求端点，仅支持 `/v1/chat/completions` |
| `body` | object | 是 | 请求体，格式与 `/v1/chat/completions` 接口一致 |

### 示例文件

```jsonl
{"custom_id":"1","method":"POST","url":"/v1/chat/completions","body":{"model":"qwen-max","messages":[{"role":"system","content":"You are a helpful assistant."},{"role":"user","content":"你好！有什么可以帮助你的吗？"}]}}
{"custom_id":"2","method":"POST","url":"/v1/chat/completions","body":{"model":"qwen-max","messages":[{"role":"system","content":"You are a helpful assistant."},{"role":"user","content":"What is 2+2?"}]}}
```

---

## 在批量推理中配置思考模式

部分模型（如 `qwen3.7-plus`、`qwen3.7-max` 及 `qwen3.6`、`qwen3.5` 系列）默认开启思考模式，会产生额外的思考 Token。如需在批量推理中配置思考模式，请在 JSONL 文件每行请求的 `body` 中设置 `enable_thinking` 参数，与 `model` 同级放置。可选参数 `thinking_budget` 用于限制思考 Token 数量上限。

> **重要**：`enable_thinking` 和 `thinking_budget` 必须直接放在 `body` 最外层（与 `model` 同级）。**请勿将其放入 `extra_body` 中**——`extra_body` 是 OpenAI Python SDK 用于透传非标准参数的机制，仅在实时推理的 SDK 调用中有效，在批量推理的 JSONL 文件中不适用。

### 示例：关闭思考模式

```jsonl
{"custom_id":"request-1","method":"POST","url":"/v1/chat/completions","body":{"model":"qwen3.5-plus","enable_thinking":false,"messages":[{"role":"user","content":"你好"}]}}
```

### 示例：开启思考模式并限制 Token 预算

```jsonl
{"custom_id":"request-2","method":"POST","url":"/v1/chat/completions","body":{"model":"qwen3.5-plus","enable_thinking":true,"thinking_budget":50,"messages":[{"role":"user","content":"请分析以下问题"}]}}
```

---

## 步骤二：创建批量推理任务

在**批量推理**页面，单击"创建批量推理任务"。

在弹出的对话框中：
- 填写任务名称和描述
- 设置最长等待时间（1–14 天）
- 上传 JSONL 文件
- 单击确认

---

## 步骤三：监控和管理任务

**查看**：在任务列表页查看任务进度（已处理请求数/总请求数）和状态。可按任务名称或 ID 搜索，或按业务空间筛选。

**管理**：
- **取消**："执行中"的任务可在操作列取消
- **排错**："失败"的任务可悬停状态查看错误概要，下载错误文件查看详情

---

## 步骤四：下载结果

> **重要**：任务结束超过 30 天将自动删除，请及时下载结果。

任务完成后，单击"查看结果"下载产出文件：

| 文件 | 内容 |
|------|------|
| **结果文件** | 记录所有成功请求及其 response 结果 |
| **错误文件**（如有） | 记录所有失败请求及其 error 详情 |

两个文件均包含 `custom_id` 字段，用于与原始输入数据匹配。

---

## 步骤五：查看用量统计（可选）

在模型用量页面，筛选并查看批量推理的用量统计。

- **数据概览**：选择时间范围（最长 30 天），将推理类型选为"批量推理"。
- **模型详情**：单击模型类别进入详情页，选择时间范围和推理类型，可查看单模型调用情况。

> **注意**：
> - 批量推理的调用数据以**任务结束时间**为准进行统计，运行中任务无法查询。
> - 监控数据存在 **1～2 小时**延迟。

---

## 使用 metadata 回传自定义标识

`custom_id` 最大支持 256 个字符。如需在结果文件中回传更长的标识信息，可使用 `metadata` 的自定义字段实现。

### metadata 字段说明

`metadata` 是创建 Batch 任务时的可选参数，支持以下字段：

| 字段 | 说明 |
|------|------|
| `ds_name` | 任务名称，设置后将显示在控制台的任务名称列 |
| `ds_description` | 任务描述，设置后将显示在控制台的任务描述列 |
| 自定义字段 | 除上述官方字段外，还支持任意自定义字段，且自定义字段的值**不受 256 字符限制**。查询任务详情时，所有自定义字段会完整回传 |

### 代码示例

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

batch = client.batches.create(
    input_file_id="file-batch-xxxxxxxxxxxxxxxxxxxx",
    endpoint="/v1/chat/completions",
    completion_window="24h",
    metadata={
        "ds_name": "my_batch_task",
        "ds_description": "批量推理任务描述",
        "my_custom_field": "此字段的值可以超过256个字符，用于回传更长的标识信息..."
    }
)
print(batch)
```

任务创建成功后，通过查询任务详情接口 `GET /v1/batches/{batch_id}` 可获取完整的 metadata 信息，包括所有自定义字段及其完整内容。

---

## API 参考

在生产环境中，使用兼容 OpenAI 的 API 自动化创建和管理 Batch 任务。核心流程如下：

| 步骤 | API | 说明 |
|------|-----|------|
| 1. 上传文件 | `POST /v1/files` | 上传 JSONL 文件，记录返回的 `id` |
| 2. 创建任务 | `POST /v1/batches` | 传入文件 ID 或 OSS 路径，记录返回的 `batch_id` |
| 3. 轮询状态 | `GET /v1/batches/{batch_id}` | 当 `status` 变为 `completed` 时，记录 `output_file_id` 并停止轮询 |
| 4. 下载结果 | `GET /v1/files/{output_file_id}/content` | 使用 `output_file_id` 下载结果文件 |

> 完整的 Batch API 接口定义和代码示例，请参见 **OpenAI 兼容-Batch（文件输入）**。

---

## 任务生命周期

| 状态 | 说明 |
|------|------|
| `validating`（验证中） | 系统正在校验文件格式（JSONL 规范）及每行请求的 API 格式合法性 |
| `in_progress`（执行中） | 文件验证通过，系统已开始逐行处理推理请求 |
| `finalizing`（最终处理中） | 所有请求均已处理完毕，结果正在分别写入结果文件和错误文件 |
| `completed`（已完成） | 结果文件和错误文件已写入完成，可下载 |
| `failed`（失败） | 任务在 validating 阶段失败，通常由文件级错误（如 JSONL 格式错误、文件过大）导致。此状态下不会执行任何推理请求，也不会生成结果文件 |
| `expired`（已终止） | 任务运行时间超过创建时设定的最长等待时间，被系统终止。创建新任务时，建议设置更长的等待时间 |
| `cancelled`（已取消） | 任务已取消，未开始处理的请求将被终止 |

---

## 计费说明

- **计费单价**：所有成功请求的输入和输出 Token，单价均为对应模型实时推理价格的 **50%**。
- **计费范围**：
  - 仅对任务中成功执行的请求计费
  - 文件解析失败、任务执行失败、或行级错误请求均**不产生费用**
  - 对于被取消的任务，在取消前已成功完成的请求仍正常计费
- **思考 Token**：部分模型（如 `qwen3.7-plus`、`qwen3.7-max` 及 `qwen3.6`、`qwen3.5` 系列）默认开启思考模式，会产生额外思考 Token 并按输出 Token 价格计费。建议根据任务复杂度设置 `enable_thinking` 参数以控制成本。
- 批量推理为独立计费项，支持 AI 通用型节省计划，但不支持预付费（节省计划）、新人免费额度等优惠，以及上下文缓存等功能。

---

## 常见问题

### 使用批量推理需要额外购买或开通吗？

不需要。开通阿里云百炼服务后即可使用，费用按后付费模式从账户余额中扣除。

### 任务提交后为什么立即失败（状态变为 failed）？

这通常是文件级错误导致的，任务并未执行任何推理请求。按以下顺序排查：

1. **文件格式**：是否为严格的 JSONL 格式，每行一个完整的 JSON 对象
2. **文件规模**：文件大小、行数等是否超出限制
3. **模型一致性**：检查文件中所有请求的 `body.model` 字段是否完全一致，且使用的是当前地域支持的模型

### 任务处理需要多长时间？

处理时长主要取决于系统当时的负载。系统繁忙时任务可能需要排队，成功或失败都会在设定的最长等待时间内返回结果。

---

## 错误码

如果调用失败并返回报错信息，请参见[错误码文档](https://help.aliyun.com/zh/model-studio/error-code)进行解决。
