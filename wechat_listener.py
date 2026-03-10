"""
Thread A: 独立进程脚本，TCP 客户端模式
- 只负责监听聊天列表中的未读消息
- 发现未读后，通过 TCP 连接向 wechat_worker 发送 (name, info) 指令
- 等待 wechat_worker 回复 ACK 后，继续监听下一条消息
"""

import json
import socket
import sys
import time
import re
from pathlib import Path
from collections import deque
from typing import List, Deque, Set, Tuple

# 导入现有的 wechat_openclaw 中的关键函数和全局变量
sys.path.insert(0, str(Path(__file__).parent))

from wechat_openclaw import (
    get_wechat_window,
    get_chat_list_control,
    extract_chat_list_items,
    collect_visible_text,
    parse_session_summary,
    calculate_similarity,
    _safe_text,
    find_list_controls,
    find_control_by_automation_id,
    _replied_messages,
)

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5555


def send_instruction_to_worker(name: str, info: dict) -> bool:
    """向 wechat_worker 发送指令，等待 ACK。
    
    返回 True 如果成功收到 ACK，False 如果失败。
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((SERVER_HOST, SERVER_PORT))
        
        # 发送指令
        payload = json.dumps({"name": name, "info": info})
        print(f"[ListenerA] 发送负载: {payload}", flush=True)
        sock.send(payload.encode("utf-8"))
        
        # 等待回复（最多等待 120 秒，假设回复过程最长）
        sock.settimeout(120)
        raw = sock.recv(1024)
        response = raw.decode("utf-8") if raw is not None else ""
        print(f"[ListenerA] 原始回复 bytes: {raw}", flush=True)
        sock.close()
        
        if response == "ACK":
            print(f"[ListenerA] 收到 ACK，{name} 已处理", flush=True)
            return True
        else:
            print(f"[ListenerA] 收到回复: {response}", flush=True)
            return False
    
    except ConnectionRefusedError:
        print(f"[ListenerA] ERROR: 无法连接到 wechat_worker (localhost:{SERVER_PORT})", flush=True)
        return False
    except socket.timeout:
        print(f"[ListenerA] ERROR: 等待 wechat_worker 回复超时", flush=True)
        return False
    except Exception as e:
        print(f"[ListenerA] ERROR: {e}", flush=True)
        return False


def monitor_chat_list(interval_seconds: float = 1.0) -> None:
    """线程A：监听聊天列表，发现未读就向 wechat_worker 发送指令。"""
    print(f"[ListenerA] 启动监听，等待 wechat_worker 就绪...", flush=True)
    time.sleep(2)  # 给 wechat_worker 充足的启动时间
    
    wechat = get_wechat_window()
    if not wechat:
        raise SystemExit("未找到微信窗口，请先打开微信桌面版。")
    
    chat_list = get_chat_list_control(wechat, strict=True)
    if not chat_list:
        chat_list = find_control_by_automation_id(wechat, "chat_message_list")
    if not chat_list:
        list_controls = find_list_controls(wechat)
        candidates: List[Tuple] = []
        for ctrl in list_controls:
            try:
                children = ctrl.GetChildren()
            except Exception:
                children = []
            if children and len(children) >= 3:
                candidates.append((ctrl, len(children)))
        candidates.sort(key=lambda item: item[1], reverse=True)
        if candidates:
            chat_list = candidates[0][0]
    
    if not chat_list:
        raise SystemExit("未找到聊天列表控件。")
    
    last_preview_by_name: dict[str, str] = {}
    
    print(f"[ListenerA] 找到聊天列表，开始监听", flush=True)
    
    while True:
        items = extract_chat_list_items(chat_list)
        
        for ctrl, name, preview in items:
            # 清理名称，去掉换行和多余内容，只保留第一行
            name = name.splitlines()[0].strip()
            try:
                raw_texts = collect_visible_text(ctrl, max_depth=2, max_nodes=80)
                has_unread = any(
                    "未读" in _safe_text(t) or "[1条]" in _safe_text(t) 
                    or re.search(r"^\d+$", _safe_text(t)) 
                    for t in raw_texts
                )
                
                if has_unread:
                    # raw_texts 里通常包含类似 '[1条]'、'晚上好'、'22:19 - [1条] 晚上好' 等
                    # 我们需要用方括号作为分隔符提取真正的消息内容
                    message = ""
                    for t in raw_texts:
                        tclean = _safe_text(t)
                        if not tclean:
                            continue
                        # 跳过仅包含未读数字的方括号
                        if re.fullmatch(r"\[\d+条\]", tclean):
                            continue
                        # 如果包含时间和 '-'
                        if " - " in tclean and re.search(r"\d{1,2}:\d{2}", tclean):
                            # 取最后一部分并去掉方括号
                            part = tclean.split(" - ")[-1]
                            message = re.sub(r"^\[\d+条\]\s*", "", part)
                            break
                        # 普通文本直接作为消息
                        message = tclean
                        break
                    
                    summary_text = " ".join([_safe_text(t) for t in raw_texts if _safe_text(t)])
                    info = parse_session_summary(summary_text)
                    # sanitize name inside info as well
                    info_name = info.get("name", "")
                    if info_name:
                        info["name"] = info_name.splitlines()[0].strip()
                    # 用我们提取的消息覆盖
                    info["last_message"] = message
                    
                    current_preview = info.get("last_message", "")
                    last_preview = last_preview_by_name.get(name, "")
                    
                    # 排除自己发出的消息
                    if any(calculate_similarity(current_preview, replied) >= 0.5 
                           for replied in _replied_messages):
                        continue
                    
                    # 只有新消息才发送指令
                    if current_preview != last_preview or name not in last_preview_by_name:
                        print(f"[ListenerA] 发现未读: {name} - {current_preview}", flush=True)
                        last_preview_by_name[name] = current_preview
                        
                        # 发送指令给 worker，阻塞等待回复
                        success = send_instruction_to_worker(name, info)
                        if not success:
                            print(f"[ListenerA] 指令发送失败，继续监听", flush=True)
                        
                        break  # 处理完一条消息后重新扫描整个列表
            
            except Exception as e:
                print(f"[ListenerA] 处理 {name} 时出错: {e}", flush=True)
        
        time.sleep(interval_seconds)


if __name__ == "__main__":
    monitor_chat_list()
