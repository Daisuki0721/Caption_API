import os
import sys
import yaml
import json
import subprocess
import re
import time
import glob
import atexit
from datetime import datetime
from openai import OpenAI

httpd_process = None
cf_process = None

def cleanup_processes():
    """强制清理后台衍生的子进程（HTTP服务和隧道）"""
    global httpd_process, cf_process
    print("\n[系统清理] 正在终止后台服务...")
    if httpd_process and httpd_process.poll() is None:
        httpd_process.terminate()
        print("  - 本地 HTTP 服务已终止")
    if cf_process and cf_process.poll() is None:
        cf_process.terminate()
        print("  - Cloudflare 隧道已关闭")

# 注册退出清理逻辑，无论是正常跑完还是按 Ctrl+C 中断，都会执行
atexit.register(cleanup_processes)

def start_services_and_get_url(public_dir, port=8000):
    """启动本地 HTTP 服务和 Cloudflare 隧道，并自动提取公网 URL"""
    global httpd_process, cf_process
    
    print(f"[服务启动] 正在 {public_dir} 目录启动本地 HTTP 服务 (端口: {port})...")
    httpd_process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port)],
        cwd=public_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    print("[服务启动] 正在拉起 Cloudflare 临时公网隧道...")
    # 启动 cloudflared 并将 stderr 合并到 stdout 以便读取
    cf_process = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    tunnel_url = None
    print("[服务启动] 正在等待 Cloudflare 分配公网 IP 节点，请稍候...")
    start_time = time.time()

    # 轮询读取控制台输出，寻找 URL
    while time.time() - start_time < 30: # 30秒超时机制
        line = cf_process.stdout.readline()
        if not line:
            break
        # 正则匹配形如 https://xxx.trycloudflare.com 的临时链接
        match = re.search(r'(https://[a-zA-Z0-9-]+\.trycloudflare\.com)', line)
        if match:
            tunnel_url = match.group(1)
            break

    if not tunnel_url:
        raise TimeoutError("Cloudflare 隧道启动超时或被屏蔽，未能获取到公网 URL。")
        
    print(f"[服务启动] 隧道建立成功！分配的公网入口为: {tunnel_url}")
    return tunnel_url

def main():
    # 1. 基础配置与路径准备
    source_dir = "/Users/daisuki/Documents/Projects/API/API_test/assets" # 源视频目录
    public_dir = os.path.join(os.getcwd(), 'public')
    results_dir = os.path.join(os.getcwd(), 'results')

    os.makedirs(public_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)

    if not os.path.exists('config.yaml') or not os.path.exists('prompt.txt'):
        raise FileNotFoundError("找不到 config.yaml 或 prompt.txt 配置文件")

    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    prices = config['models']['qwen3.5-omni-plus']

    with open('prompt.txt', 'r', encoding='utf-8') as f:
        prompt = f.read().strip()
    is_json_mode = "json" in prompt.lower()

    client = OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://ws-9eaupaeyp0hh6lcp.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )

    # 2. 扫描源视频
    # 这里我们扫描所有常见视频格式，后续统一转为 MP4
    video_files = []
    for ext in ('*.mp4', '*.avi', '*.mov', '*.mkv'):
        video_files.extend(glob.glob(os.path.join(source_dir, ext)))
        
    if not video_files:
         raise FileNotFoundError(f"在 {source_dir} 中未找到任何视频文件")
    print(f"\n[数据准备] 扫描到 {len(video_files)} 个源视频文件")

    # 3. 后台拉起隧道并获取动态 URL
    # 核心步骤：将获取到的动态 URL 注入给业务流
    TUNNEL_BASE_URL = start_services_and_get_url(public_dir=public_dir, port=8000)

    jsonl_lines = []
    exposed_files = []

    print(f"\n[数据准备] 开始进行批量视频压缩，并强制转为 MP4 格式...")
    # 4. 遍历处理视频，生成 JSONL 任务清单
    for local_video_path in video_files:
        base_name = os.path.splitext(os.path.basename(local_video_path))[0]
        # 强制指定扩展名为 .mp4
        output_filename = f"batch_{base_name}.mp4"
        exposed_file_path = os.path.join(public_dir, output_filename)
        public_video_url = f"{TUNNEL_BASE_URL}/{output_filename}"
        
        exposed_files.append(exposed_file_path)

        # 强制格式转换与压缩
        cmd = [
            'ffmpeg', '-y', '-i', local_video_path,
            '-t', '60',            
            '-vf', 'scale=-2:480', 
            '-r', '10',            
            '-c:v', 'libx264', '-preset', 'fast',
            '-c:a', 'aac', '-ac', '2', '-b:a', '128k', 
            '-f', 'mp4', # 强制输出为 MP4 容器
            exposed_file_path
        ]
        print(f"  -> 处理中: {os.path.basename(local_video_path)} => {output_filename}")
        process = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if process.returncode != 0:
            print(f"{base_name} 处理失败，跳过。报错: {process.stderr.decode('utf-8')}")
            continue
        
        # 组装请求体[cite: 2]
        body = {
            "model": "qwen3.5-omni-plus",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "video_url", "video_url": {"url": public_video_url}},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
        }
        if is_json_mode:
            body["response_format"] = {"type": "json_object"}

        batch_request = {
            "custom_id": base_name, 
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body
        }
        jsonl_lines.append(json.dumps(batch_request, ensure_ascii=False))

    if not jsonl_lines:
        raise RuntimeError("没有成功构建出任何有效的请求数据。")

    # 5. 上传与提交 Batch 任务
    batch_input_path = "batch_input.jsonl"
    with open(batch_input_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(jsonl_lines) + '\n')
    
    try:
        print("\n[云端交互] 正在上传 JSONL 任务文件至阿里云...")
        batch_file = client.files.create(
            file=open(batch_input_path, "rb"),
            purpose="batch"
        )
        
        print("[云端交互] 正在提交批量推理任务...")
        batch_job = client.batches.create(
            input_file_id=batch_file.id,
            endpoint="/v1/chat/completions",
            completion_window="24h"
        )
        print(f"任务提交成功！Batch ID: {batch_job.id}")
        print("系统正在异步处理，此时隧道将保持开启状态，直至模型拉取完毕...")

        # 6. 轮询任务状态
        while True:
            job_status = client.batches.retrieve(batch_job.id)
            status = job_status.status
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务状态: {status} (已完成: {job_status.request_counts.completed} / 总计: {job_status.request_counts.total})")
            
            if status == 'completed':
                print("批量推理任务全部处理完成！")
                break
            elif status in ['failed', 'expired', 'cancelled']:
                raise RuntimeError(f"批量任务异常终止，最终状态: {status}")
                
            time.sleep(30) 

        # 7. 下载并解析结果
        print("\n[结果处理] 正在下载推理结果...")
        result_response = client.files.content(job_status.output_file_id)
        result_content = result_response.text

        total_batch_prompt_tokens = 0
        total_batch_completion_tokens = 0
        total_batch_cost = 0.0
        success_count = 0

        for line in result_content.strip().split('\n'):
            if not line: continue
            record = json.loads(line)
            video_name = record.get('custom_id') 
            response_body = record.get('response', {}).get('body', {})
            
            if 'choices' not in response_body:
                print(f"{video_name} 推理失败。")
                continue
                
            raw_content = response_body['choices'][0]['message']['content']
            success_count += 1
            
            # 结果清洗
            if is_json_mode:
                cleaned_text = re.sub(r'^```json\s*|\s*```$', '', raw_content.strip()).strip()
                if cleaned_text.startswith('{'):
                    new_start = '{\n  "video": "' + video_name + '",'
                    final_json_block = new_start + cleaned_text[1:]
                else:
                    final_json_block = '{\n  "video": "' + video_name + '",\n  "raw_result": ' + json.dumps(cleaned_text, ensure_ascii=False) + '\n}'
                output_path = os.path.join(results_dir, f"{video_name}.json")
            else:
                final_json_block = f"Video: {video_name}\n{'='*40}\n{raw_content.strip()}\n"
                output_path = os.path.join(results_dir, f"{video_name}.txt")
                
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(final_json_block + ('\n' if is_json_mode else ''))

            # Token 统计[cite: 2]
            usage = response_body.get('usage', {})
            prompt_details = usage.get('prompt_tokens_details', {})
            audio_in_tokens = prompt_details.get('audio_tokens', 0) if isinstance(prompt_details, dict) else 0
            visual_text_in_tokens = usage.get('prompt_tokens', 0) - audio_in_tokens
            text_out_tokens = usage.get('completion_tokens', 0)
            
            total_batch_prompt_tokens += usage.get('prompt_tokens', 0)
            total_batch_completion_tokens += text_out_tokens
            
            DISCOUNT = 0.5 # Batch 推理 50% 折扣[cite: 2]
            cost_visual_text_in = (visual_text_in_tokens / 1000000) * prices['input_video_price_per_1m'] * DISCOUNT
            cost_audio_in = (audio_in_tokens / 1000000) * prices['input_audio_price_per_1m'] * DISCOUNT
            cost_text_out = (text_out_tokens / 1000000) * prices['output_text_price_per_1m'] * DISCOUNT
            total_batch_cost += (cost_visual_text_in + cost_audio_in + cost_text_out)

        print(f"成功提取并写入了 {success_count} 个结果。")

        # 8. 计费持久化
        history_file = os.path.join(os.getcwd(), 'consume-history.txt')
        history_total_in, history_total_out, history_total_cost = 0, 0, 0.0
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                content = f.read()
                in_match = re.findall(r"历史总计消耗 Input Tokens:\s*(\d+)", content)
                out_match = re.findall(r"历史总计消耗 Output Tokens:\s*(\d+)", content)
                cost_match = re.findall(r"历史总计费用:\s*¥([0-9.]+)", content)
                if in_match: history_total_in = int(in_match[-1])
                if out_match: history_total_out = int(out_match[-1])
                if cost_match: history_total_cost = float(cost_match[-1])

        new_total_in = history_total_in + total_batch_prompt_tokens
        new_total_out = history_total_out + total_batch_completion_tokens
        new_total_cost = history_total_cost + total_batch_cost

        with open(history_file, 'a', encoding='utf-8') as f:
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{now_str}] 自动化 Batch 任务 (成功: {success_count} 个)\n")
            f.write(f"  本次消耗 - Input: {total_batch_prompt_tokens}, Output: {total_batch_completion_tokens}\n")
            f.write(f"  本次费用 - ¥{total_batch_cost:.6f} (已应用 50% 折扣)\n")
            f.write(f"  历史总计消耗 Input Tokens: {new_total_in}\n")
            f.write(f"  历史总计消耗 Output Tokens: {new_total_out}\n")
            f.write(f"  历史总计费用: ¥{new_total_cost:.6f}\n")
            f.write("-" * 50 + "\n")

    except Exception as e:
        print(f"\n[致命错误] 执行流程中断: {str(e)}")

    finally:
        # 9. 清理本地映射视频与临时文件
        print("\n[系统清理] 正在删除本地映射视频...")
        for exposed_file in exposed_files:
            if os.path.exists(exposed_file):
                try: os.remove(exposed_file)
                except: pass
        if os.path.exists(batch_input_path):
             os.remove(batch_input_path)
             
        # 注意：atexit.register 会在这里或者脚本彻底退出时，自动执行 cleanup_processes 关掉隧道服务。

if __name__ == "__main__":
    main()
