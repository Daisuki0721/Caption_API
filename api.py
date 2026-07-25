import os
import yaml
import json
import subprocess
import re
import time
from datetime import datetime
from openai import OpenAI

def main():
    # 1. 隧道链接配置
    TUNNEL_BASE_URL = "https://elements-gnome-rachel-extension.trycloudflare.com"

    # 2. 前置校验：加载配置与 Prompt
    if not os.path.exists('config.yaml'):
        raise FileNotFoundError("找不到 config.yaml 配置文件")
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    prices = config['models']['qwen3.5-omni-plus']

    if not os.path.exists('prompt.txt'):
        raise FileNotFoundError("找不到 prompt.txt 文件")
    with open('prompt.txt', 'r', encoding='utf-8') as f:
        final_prompt = f.read().strip()

    # 核心判断：是否属于 JSON 模式请求
    is_json_mode = "json" in final_prompt.lower()
    if is_json_mode:
        print("探测到 'json' 关键字，启用严格 JSON 输出模式")
    else:
        print("未探测到 'json' 关键字，启用普通文本自由输出模式")

    # 3. 初始化客户端
    client = OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://ws-9eaupaeyp0hh6lcp.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )

    # 4. 路径与资源校验
    local_video_path = "/Users/daisuki/Documents/Projects/API/API_test/assets/sea.mp4"
    if not os.path.exists(local_video_path):
        raise FileNotFoundError(f"找不到源视频文件: {local_video_path}")
        
    video_name = os.path.basename(local_video_path) 

    public_dir = os.path.join(os.getcwd(), 'public')
    results_dir = os.path.join(os.getcwd(), 'results')
    os.makedirs(public_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)

    output_filename = "temp_pilot_test.mp4"
    exposed_file_path = os.path.join(public_dir, output_filename)
    public_video_url = f"{TUNNEL_BASE_URL}/{output_filename}"

    print(f"\n开始压缩视频 (全长 1 分钟，高画质，双声道保留)...")

    try:
        # 5. FFmpeg 压缩处理
        cmd = [
            'ffmpeg', '-y', '-i', local_video_path,
            '-t', '60',            
            '-vf', 'scale=-2:480', 
            '-r', '10',            
            '-c:v', 'libx264', '-preset', 'fast',
            '-c:a', 'aac', '-ac', '2', '-b:a', '128k', 
            exposed_file_path
        ]
        process = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg 压缩失败:\n{process.stderr.decode('utf-8')}")

        print(f"视频已就绪！映射地址为: {public_video_url}")
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "video_url", "video_url": {"url": public_video_url}},
                    {"type": "text", "text": final_prompt}
                ]
            }
        ]

        # 动态构建请求参数
        api_kwargs = {
            "model": "qwen3.5-omni-plus",
            "messages": messages,
            "stream": False,
            "timeout": 120
        }
        if is_json_mode:
            api_kwargs["response_format"] = {"type": "json_object"}

        # API 请求重试机制
        max_retries = 3
        completion = None
        
        print("正在请求大模型，请确保你的隧道服务正常运行中...\n")
        for attempt in range(max_retries):
            try:
                completion = client.chat.completions.create(**api_kwargs)
                break 
            except Exception as api_err:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"API 调用在 {max_retries} 次尝试后彻底失败: {str(api_err)}")
                print(f"API 请求异常 (尝试 {attempt + 1}/{max_retries}): {str(api_err)}")
                print("等待 3 秒后重试...")
                time.sleep(3)

        # 6. 数据清洗与文件写入 (分流处理)
        raw_content = completion.choices[0].message.content

        if is_json_mode:
            # --- JSON 模式处理 ---
            cleaned_text = re.sub(r'^```json\s*|\s*```$', '', raw_content.strip()).strip()
            if cleaned_text.startswith('{'):
                new_start = '{\n  "video": "' + video_name + '",'
                final_json_block = new_start + cleaned_text[1:]
            else:
                final_json_block = '{\n  "video": "' + video_name + '",\n  "raw_result": ' + json.dumps(cleaned_text, ensure_ascii=False) + '\n}'

            output_path = os.path.join(results_dir, f"{video_name}.json")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_json_block + '\n')
            print(f"JSON 结果已写入: {output_path}")
            
            # 屏幕回显
            try:
                json_result = json.loads(cleaned_text)
                print(f"全局声景:\n{json_result.get('global_soundscape', '未提取到')}\n")
                print(f"最终 Caption:\n{json_result.get('final_caption', '未提取到')}\n")
            except json.JSONDecodeError:
                print("屏幕回显解析失败，请直接查看生成的文件。")
                
        else:
            # --- 普通文本模式处理 ---
            output_path = os.path.join(results_dir, f"{video_name}.txt")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"Video: {video_name}\n")
                f.write("="*40 + "\n")
                f.write(raw_content.strip() + '\n')
            print(f"普通文本结果已写入: {output_path}")
            print(f"模型原始输出:\n{raw_content.strip()}\n")

        print("="*60)
        
        # 7. 计费统计与历史追加逻辑
        usage = completion.usage
        prompt_details = getattr(usage, 'prompt_tokens_details', {})
        audio_in_tokens = prompt_details.get('audio_tokens', 0) if hasattr(prompt_details, 'get') else 0
        visual_text_in_tokens = usage.prompt_tokens - audio_in_tokens
        text_out_tokens = usage.completion_tokens

        cost_visual_text_in = (visual_text_in_tokens / 1000000) * prices['input_video_price_per_1m']
        cost_audio_in = (audio_in_tokens / 1000000) * prices['input_audio_price_per_1m']
        cost_text_out = (text_out_tokens / 1000000) * prices['output_text_price_per_1m']
        total_current_cost = cost_visual_text_in + cost_audio_in + cost_text_out

        # 读取并更新 consume-history.txt
        history_file = os.path.join(os.getcwd(), 'consume-history.txt')
        
        history_total_in = 0
        history_total_out = 0
        history_total_cost = 0.0
        
        # 使用正则精准抓取最后的历史总计
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                content = f.read()
                in_match = re.findall(r"历史总计消耗 Input Tokens:\s*(\d+)", content)
                out_match = re.findall(r"历史总计消耗 Output Tokens:\s*(\d+)", content)
                cost_match = re.findall(r"历史总计费用:\s*¥([0-9.]+)", content)
                
                if in_match: history_total_in = int(in_match[-1])
                if out_match: history_total_out = int(out_match[-1])
                if cost_match: history_total_cost = float(cost_match[-1])

        # 累加本次消耗
        new_total_in = history_total_in + usage.prompt_tokens
        new_total_out = history_total_out + usage.completion_tokens
        new_total_cost = history_total_cost + total_current_cost

        # 追加写入日志文件
        with open(history_file, 'a', encoding='utf-8') as f:
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{now_str}] 推理任务: {video_name} (模式: {'JSON' if is_json_mode else '文本'})\n")
            f.write(f"  本次消耗 - Input: {usage.prompt_tokens} (Audio: {audio_in_tokens}, Visual/Text: {visual_text_in_tokens}), Output: {text_out_tokens}\n")
            f.write(f"  本次费用 - ¥{total_current_cost:.6f}\n")
            f.write(f"  历史总计消耗 Input Tokens: {new_total_in}\n")
            f.write(f"  历史总计消耗 Output Tokens: {new_total_out}\n")
            f.write(f"  历史总计费用: ¥{new_total_cost:.6f}\n")
            f.write("-" * 50 + "\n")

        print("--- 本次计费统计 ---")
        print(f"消耗 Token: 输入 {usage.prompt_tokens} | 输出 {usage.completion_tokens}")
        print(f"预估花费: ¥{total_current_cost:.6f}")
        print(f"\n已将计费结果追加至 {history_file} (当前总计花费: ¥{new_total_cost:.6f})")

    except Exception as e:
        print(f"\n[致命错误] 执行流程中断: {str(e)}")

    finally:
        # 安全的清理机制
        if 'exposed_file_path' in locals() and os.path.exists(exposed_file_path):
            try:
                os.remove(exposed_file_path)
                print("\n临时生成的隧道映射视频已删除")
            except Exception as clean_err:
                print(f"\n临时文件删除失败，请手动清理: {clean_err}")

if __name__ == "__main__":
    main()
