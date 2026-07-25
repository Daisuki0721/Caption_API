# DashScope Chat Completions API 参考

> 基于阿里云百炼 Model Studio API，OpenAI 兼容接口。

---

## 1. Messages 结构

`messages` 为必选参数，按对话顺序排列，传递给大模型作为上下文。

### 1.1 System Message — 系统消息

设定模型角色、语气、任务目标或约束条件，通常放在 `messages` 数组首位。

> **注意**：QwQ 模型不建议设置 System Message；QVQ 模型设置后不会生效。

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `content` | string | 是 | 系统指令，明确角色、行为规范、回答风格和任务约束 |
| `role` | string | 是 | 固定为 `"system"` |

### 1.2 User Message — 用户消息

向模型传递问题、指令或上下文。

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `content` | string 或 array | 是 | 纯文本时为 string；含多模态数据或启用显式缓存时为 array |
| `role` | string | 是 | 固定为 `"user"` |

#### 多模态 / 显式缓存时的 content 数组元素

**text** — 文本输入

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `type` | string | 是 | `"text"` |
| `text` | string | 是 | 输入的文本 |

**image_url** — 图片输入

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `type` | string | 是 | `"image_url"` |
| `image_url.url` | string | 是 | 图片 URL 或 Base64 Data URL |

**input_audio** — 音频输入

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `type` | string | 是 | `"input_audio"` |
| `input_audio.data` | string | 是 | 音频 URL 或 Base64 Data URL |
| `input_audio.format` | string | 是 | 音频格式，如 `mp3`、`wav` |

**video** — 图片列表形式的视频输入

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `type` | string | 是 | `"video"` |
| `video` | array | 是 | 图片 URL 数组，按帧顺序排列 |

示例：
```json
[
  "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/xzsgiz/football1.jpg",
  "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241108/tdescd/football2.jpg"
]
```

**video_url** — 视频文件输入

> Qwen-VL 只理解视频的视觉信息，Qwen-Omni 可理解视觉与音频信息。

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `type` | string | 是 | `"video_url"` |
| `video_url.url` | string | 是 | 视频文件公网 URL 或 Base64 Data URL |

**cache_control** — 显式缓存标记

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 仅支持 `"ephemeral"` |

#### 图像/视频像素控制参数

以下参数用于控制图像和视频帧的像素处理，适用于 Qwen-VL、QVQ 模型。

`min_pixels` — 最小像素阈值

当输入图像/视频帧像素小于此值时，自动放大至该值以上。

| 模型系列 | 图像默认/最小值 | 视频默认值 | 视频最小值 |
|----------|:-----------:|:--------:|:--------:|
| Qwen3.7/3.6/3.5/3-VL | 65536 | 65536 | 4096 |
| Qwen3.5-Omni | 24576 | 65536 | 4096 |
| qwen-vl-max/plus (特定版本) | 4096 | 65536 | 4096 |
| Qwen2.5-VL 开源 / QVQ 系列 | 3136 | 50176 | 3136 |

`max_pixels` — 最大像素阈值

当像素超过此值时，自动缩小至该值以下。

**输入图像（`vl_high_resolution_images=false` 时）：**

| 模型系列 | 默认值 | 最大值 |
|----------|:-----:|:-----:|
| Qwen3.7/3.6/3.5/3-VL | 2,621,440 | 16,777,216 |
| Qwen3.5-Omni | 1,310,720 | 16,777,216 |
| qwen-vl-max/plus (特定版本) | 1,310,720 | 16,777,216 |
| Qwen2.5-VL 开源 / QVQ | 1,003,520 | 12,845,056 |

**输入图像（`vl_high_resolution_images=true` 时）：**

| 模型系列 | 固定上限 |
|----------|:-----:|
| Qwen3.7/3.6/3.5/3-VL / qwen-vl-max/plus 特定版本 | 16,777,216 |
| Qwen2.5-VL 开源 / QVQ | 12,845,056 |

**输入视频文件/图像列表：**

| 模型系列 | 默认值 | 最大值 |
|----------|:-----:|:-----:|
| Qwen3.7/3.6/3.5/3.5-Omni / 3-VL 闭源 | 655,360 | 2,048,000 |
| 其他 Qwen3-VL 开源 / qwen-vl-max/plus 特定版本 | 655,360 | 786,432 |
| Qwen2.5-VL 开源 / QVQ | 501,760 | 602,112 |

`total_pixels` — 视频总像素限制

限制从视频中抽取的所有帧的总像素（单帧 × 总帧数），用于控制 Token 消耗。缩放后单帧仍在 `[min_pixels, max_pixels]` 范围内。

| 模型系列 | 默认值 | 对应图像 Token |
|----------|:-----:|:------------:|
| Qwen3.7/3.6/3.5 | 819,200,000 | 800,000 (32×32/Token) |
| Qwen3-VL 闭源 / qwen3-vl-235b 开源 | 134,217,728 | 131,072 (32×32/Token) |
| Qwen3.5-Omni | 184,549,376 | 180,224 (32×32/Token) |
| 其他 Qwen3-VL 开源 / qwen-vl-max/plus 特定版本 | 67,108,864 | 65,536 (32×32/Token) |
| Qwen2.5-VL 开源 / QVQ | 51,380,224 | 65,536 (28×28/Token) |

### 1.3 Assistant Message — 助手消息

模型的回复，用于在多轮对话中作为上下文回传。

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `content` | string | 条件必选 | 模型回复文本。含 `tool_calls` 时可为空，否则必选 |
| `role` | string | 是 | 固定为 `"assistant"` |
| `partial` | boolean | 否 | 是否开启前缀续写，默认 `false` |
| `tool_calls` | array | 否 | Function Calling 返回的工具调用信息 |

**tool_calls 数组元素：**

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 工具响应 ID |
| `type` | string | 是 | 固定为 `"function"` |
| `function.name` | string | 是 | 工具名称 |
| `function.arguments` | string | 是 | 入参，JSON 格式字符串 |
| `index` | integer | 是 | 在 `tool_calls` 数组中的索引 |

### 1.4 Tool Message — 工具消息

工具函数的输出信息。

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `content` | string | 是 | 工具输出内容，必须为字符串（结构化数据需序列化） |
| `role` | string | 是 | 固定为 `"tool"` |
| `tool_call_id` | string | 是 | 对应 `tool_calls` 中的 id |

---

## 2. 请求参数

### 2.1 流式输出

**`stream`** — boolean，默认 `false`

- `false`：模型生成全部内容后一次性返回
- `true`：边生成边输出，每个 chunk 包含部分内容

> **强烈建议设为 `true`**，可提升体验并降低超时风险。非流式调用超过 300 秒将被中断（返回已生成内容，不报错）。

**`stream_options`** — object，仅 `stream=true` 时生效

| 属性 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `include_usage` | boolean | `false` | 是否在最后一个 chunk 包含 Token 消耗信息 |

### 2.2 输出模态（Qwen-Omni 专用）

**`modalities`** — array，默认 `["text"]`

| 值 | 说明 |
|----|------|
| `["text", "audio"]` | 输出文本和音频 |
| `["text"]` | 仅输出文本 |

**`audio`** — object，仅 `modalities=["text","audio"]` 时有效

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `voice` | string | 是 | 输出音频音色 |
| `format` | string | 是 | 仅支持 `"wav"` |

### 2.3 采样控制

**`temperature`** — float，范围 `[0, 2)`

控制生成文本多样性。值越高越多样，越低越确定。建议与 `top_p` 只设一个。

> 不建议修改 QVQ 模型的默认值。

**`top_p`** — float，范围 `(0, 1.0]`

核采样概率阈值。值越高越多样。建议与 `temperature` 只设一个。

> 不建议修改 QVQ 模型的默认值。

**`top_k`** — integer，≥ 0

候选 Token 数量。值越大输出越随机。设为 `null` 或大于 100 时禁用。

> **非 OpenAI 标准参数**，需放入 `extra_body`：`extra_body={"top_k": xxx}`

默认值：

| 模型系列 | 默认值 |
|----------|:-----:|
| QVQ 系列 | 10 |
| QwQ 系列 | 40 |
| qwen-vl-plus 早期 / qwen2.5-omni-7b | 1 |
| Qwen3-Omni-Flash | 50 |
| DeepSeek / Kimi / MiniMax 系列 | 不支持 |
| GLM 系列（阿里云直供） | 20 |
| 其余模型 | 20 |

### 2.4 重复惩罚

**`repetition_penalty`** — float，> 0

控制连续序列重复度。`1.0` 表示不做惩罚。值越高重复度越低。

> **非 OpenAI 标准参数**，需放入 `extra_body`：`extra_body={"repetition_penalty": xxx}`
>
> qwen-vl-plus (2025-01-25) 文字提取时建议设为 `1.0`。
> 不建议修改 QVQ 模型的默认值。

**`presence_penalty`** — float，范围 `[-2.0, 2.0]`

正值降低重复度（更多样），负值增加重复度（更一致）。

默认值：

| 模型系列 | 默认值 |
|----------|:-----:|
| Qwen3.7/3.6/3.5/3 非思考 / Qwen3.5-Omni / QVQ / qwen-max / qwen2.5-vl / qwen-vl-max / qwen-vl-plus / Qwen3-VL 非思考 / qwen3-preview 思考 | 1.5 |
| qwen3-8b/14b/32b/30b-a3b/235b-a22b 思考 / qwen-plus/turbo 思考 | 0.5 |
| DeepSeek R1 系列（阿里云直供） | 1.0 |
| Kimi 全系列 | 0.0 |
| MiniMax M2.5/M2.1 | 0.0 |
| 其余模型 | 0.0 |

> qwen-vl-plus 文字提取时建议设为 `1.5`。

### 2.5 结构化输出

**`response_format`** — object，默认 `{"type": "text"}`

| 值 | 说明 |
|----|------|
| `{"type": "text"}` | 输出纯文本 |
| `{"type": "json_object"}` | 输出标准 JSON 字符串 |

> 设为 `json_object` 时，必须在提示词中明确要求 JSON 格式，否则报错。

### 2.6 输出长度控制

**`max_tokens`** — integer（即将废弃，新接入请用 `max_completion_tokens`）

限制模型回答的最大长度（不含思维链）。超过则提前停止，`finish_reason` 为 `length`。

> GLM-5.2+ 中 `max_tokens` 行为与 `max_completion_tokens` 一致（含思维链）。

**`max_completion_tokens`** — integer

限制模型完整输出的最大长度（**含思维链 + 回答**）。超过则提前停止。

支持的模型：Qwen3.7-Max+、Qwen3.5-Plus+、Qwen3.5-Flash+、Kimi K2.5+、GLM-5+、MiniMax M2.5+、DeepSeek V3/R1/V3.1/V3.2/V4 系列。

> 实际输出与设定值最多有 10 Token 误差。

### 2.7 高分辨率图像

**`vl_high_resolution_images`** — boolean，默认 `false`

是否将输入图像像素上限提升至 16384 Token 对应的像素值。

> **非 OpenAI 标准参数**，需放入 `extra_body`：`extra_body={"vl_high_resolution_images": true}`

| 值 | 行为 |
|----|------|
| `true` | 固定分辨率策略，忽略 `max_pixels`，超限时缩小至固定上限 |
| `false` | 像素上限由 `max_pixels` 决定 |

`true` 时的像素上限：

| 模型系列 | 上限 |
|----------|-----:|
| Qwen3.7/3.6/3.5/3-VL / qwen-vl-max/plus 特定版本 | 16,777,216 (16384 × 32×32) |
| QVQ / Qwen2.5-VL | 12,845,056 (16384 × 28×28) |

### 2.8 思考模式

**`enable_thinking`** — boolean

是否开启混合思考模式。适用于 Qwen3.7/3.6/3.5/3/3-Omni-Flash/3-VL、DeepSeek-V4/V3.2/V3.1、Kimi K2.7-code/K2.6/K2.5、GLM 系列。

- `true`：开启，思考内容通过 `reasoning_content` 字段返回
- `false`：不开启

> **非 OpenAI 标准参数**，需放入 `extra_body`：`extra_body={"enable_thinking": true}`
>
> 各模型默认值不同，详见模型列表。

**`thinking_budget`** — integer

思考过程最大 Token 数。适用于 Qwen3.7/3.6/3.5/3-VL/3 的商业版与开源版。

> **非 OpenAI 标准参数**，需放入 `extra_body`：`extra_body={"thinking_budget": xxx}`

**`reasoning_effort`** — string，默认 `"high"`

控制 DeepSeek-V4 与 GLM 系列的推理力度。

| 值 | 映射行为 |
|----|----------|
| `high` | 高力度推理 |
| `max` | 最大力度推理 |
| `low` / `medium` | 映射为 `high` |
| `xhigh` | 映射为 `max` |

适用于：glm-5.2/5.1/5、deepseek-v4-pro/v4-flash。

> **非 OpenAI 标准参数**，需放入 `extra_body`：`extra_body={"reasoning_effort": "high"}`

**`thinking`** — object，默认 `{"type": "adaptive"}`

仅适用于稀宇科技直供的 MiniMax/MiniMax-M3。

| `thinking.type` | 说明 |
|-----------------|------|
| `adaptive` | 自适应，模型自主判断是否需要思考 |
| `disabled` | 关闭思考 |

> **非 OpenAI 标准参数**，需放入 `extra_body`：`extra_body={"thinking": {"type": "adaptive"}}`

**`preserve_thinking`** — boolean，默认 `false`

是否将历史 `reasoning_content` 拼接到模型输入。支持：qwen3.7-max/plus、qwen3.6-max-preview/plus/flash、kimi-k2.6/k2.7-code（阿里云部署）、kimi/k2.7-code（月之暗面直供，默认开启）。

> 开启后历史思考内容会计入输入 Token 并计费。
>
> **非 OpenAI 标准参数**，需放入 `extra_body`：`extra_body={"preserve_thinking": True}`

**`clear_thinking`** — boolean，默认 `false`

仅 GLM 系列 glm-5.2/5.1/5/4.7 支持。控制多轮对话中是否忽略历史 `reasoning_content`。

| 值 | 说明 |
|----|------|
| `true` | 忽略历史轮次的思考内容，仅用可见文本/工具调用等作为上下文 |
| `false` | 保留历史思考内容（需完整透传，缺失/修改会导致效果下降） |

> **非 OpenAI 标准参数**：`extra_body={"enable_thinking": True, "clear_thinking": True}`

### 2.9 工具调用（Function Calling）

**`tools`** — array

工具对象数组，供模型调用。

| 属性 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定为 `"function"` |
| `function.name` | string | 是 | 工具名称，仅允许字母、数字、下划线、短划线，最长 64 Token |
| `function.description` | string | 是 | 工具描述，帮助模型判断调用时机 |
| `function.parameters` | object | 否 | 工具参数 JSON Schema。建议传入以提高调用准确性 |

**`tool_choice`** — string 或 object，默认 `"auto"`

| 值 | 说明 |
|----|------|
| `"auto"` | 模型自主选择 |
| `"none"` | 禁用所有工具 |
| `{"type": "function", "function": {"name": "xxx"}}` | 强制调用指定工具 |

> 思考模式模型不支持强制调用某个工具。

**`parallel_tool_calls`** — boolean，默认 `false`

是否开启并行工具调用。

**`tool_stream`** — boolean，默认 `false`

仅在 `stream=true` 时生效。影响复杂工具参数（array/object 类型）的输出方式。

| 值 | 说明 |
|----|------|
| `false` | 复杂参数一次性输出，格式更准确 |
| `true` | 复杂参数流式输出，无超时风险 |

支持：Qwen Max/Plus/Flash 系列、GLM 4.6/4.7/5/5.1。

> **非 OpenAI 标准参数**，需放入 `extra_body`：`extra_body={"tool_stream": true}`

### 2.10 联网搜索

**`enable_search`** — boolean，默认 `false`

是否开启联网搜索。可能增加 Token 消耗。

> **非 OpenAI 标准参数**，需放入 `extra_body`：`extra_body={"enable_search": True}`

**`search_options`** — object

| 属性 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `forced_search` | boolean | `false` | 是否强制联网搜索，仅 `enable_search=true` 时有效 |
| `search_strategy` | string | `"turbo"` | 搜索量级策略 |
| `enable_search_extension` | boolean | `false` | 是否开启垂域搜索 |

`search_strategy` 可选值：

| 值 | 说明 |
|----|------|
| `turbo`（默认） | 兼顾响应速度与搜索效果 |
| `max` | 更全面搜索，响应时间更长 |
| `agent` | 多轮信息检索与整合，仅支持 qwen3.5-plus/flash、qwen3-max、qwen3.5-omni 特定快照版本 |
| `agent_max` | `agent` + 网页抓取，仅支持 qwen3-max 思考模式特定快照版本 |

> **非 OpenAI 标准参数**，需放入 `extra_body`：`extra_body={"search_options": {...}}`

### 2.11 代码解释器

**`enable_code_interpreter`** — boolean，默认 `false`

> **非 OpenAI 标准参数**，需放入 `extra_body`：`extra_body={"enable_code_interpreter": true}`

### 2.12 其他参数

**`n`** — integer，默认 `1`，范围 1-4

生成响应的数量。仅 Qwen3（非思考模式）支持。传入 `tools` 时需设为 `1`。

**`seed`** — integer，范围 `[0, 2^31-1]`

随机数种子，用于结果复现。

**`logprobs`** — boolean，默认 `false`

是否返回输出 Token 的对数概率。思考内容不返回对数概率。

**`top_logprobs`** — integer，默认 `0`，范围 `[0, 5]`

返回最大概率的候选 Token 个数。仅 `logprobs=true` 时生效。

**`stop`** — string 或 array

停止词。模型输出中出现指定字符串或 token_id 时立即终止。数组中不可混用字符串和 token_id。

---

## 3. 参数速查：extra_body 汇总

以下参数非 OpenAI 标准，必须通过 `extra_body` 传入：

```python
extra_body={
    "top_k": 20,
    "repetition_penalty": 1.0,
    "vl_high_resolution_images": True,
    "enable_thinking": True,
    "thinking_budget": 1000,
    "reasoning_effort": "high",
    "thinking": {"type": "adaptive"},
    "preserve_thinking": True,
    "clear_thinking": True,
    "tool_stream": True,
    "enable_search": True,
    "search_options": {"forced_search": False, "search_strategy": "turbo"},
    "enable_code_interpreter": True,
}
```
