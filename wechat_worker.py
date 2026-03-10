"""
Thread B: 独立进程脚本，TCP 服务器模式
- 监听 localhost:5555
- 接收来自 wechat_listener 的 (name, info) 指令
- 搜索打开对话，调用 AI 生成回复并发送
- 完成后回复 "ACK"
"""

import json
import socket
import sys
import time
from pathlib import Path
import uiautomation as auto

# 导入现有的 wechat_openclaw 中的关键函数和全局变量
sys.path.insert(0, str(Path(__file__).parent))

from wechat_openclaw import (
    get_wechat_window,
    extract_chat_list_items,
    get_chat_list_control,
    focus_input_near_send,
    get_current_chat_messages,
    build_ai_reply,
    type_reply_slowly,
    click_send_button,
    calculate_similarity,
    _replied_messages,
)

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5555


def search_and_open_chat(name: str) -> bool:
    """搜索联系人并打开对话框。
    
    返回 True 如果成功打开，False 则继续用原始点击方式。
    """
    wechat = get_wechat_window()
    if not wechat:
        print("[search] get_wechat_window returned None", flush=True)
        return False
    
    try:
        # 尝试找搜索框并输入
        search_box = wechat.EditControl(Name="搜索")
        if search_box.Exists(0, 0):
            search_box.Click()
            time.sleep(0.2)
            search_box.SendKeys(name)
            time.sleep(0.8)
            # 按回车以打开第一个结果
            print("[search] 按 Enter 打开第一个结果", flush=True)
            search_box.SendKeys('{ENTER}')
            time.sleep(0.5)
            return True
        else:
            print("[search] 搜索框不存在", flush=True)
    except Exception as e:
        print(f"[WARN] search_and_open_chat 失败: {e}", flush=True)
    return False


def handle_client(client_socket: socket.socket, addr: tuple) -> None:
    """处理来自 wechat_listener 的单个连接。"""
    try:
        # 接收指令（name 和 info）
        recv_data = client_socket.recv(4096).decode("utf-8")
        if not recv_data:
            return
        print(f"[WorkerB] 原始请求文本: {recv_data}", flush=True)
        request = json.loads(recv_data)
        name = request.get("name", "")
        info = request.get("info", {})
        
        print(f"[WorkerB] 收到指令: name={name}, info={info}", flush=True)
        
        if not name:
            client_socket.send("FAIL".encode("utf-8"))
            return
        
        try:
            # 打开聊天窗口
            print(f"[WorkerB] 尝试打开聊天: {name}", flush=True)
            ok = search_and_open_chat(name)
            print(f"[WorkerB] search_and_open_chat returned: {ok}", flush=True)
            if not ok:
                print(f"[WorkerB] 搜索失败或未打开窗口，跳过本次处理", flush=True)
                client_socket.send("FAIL".encode("utf-8"))
                return
            
            # 已经打开了，等待几秒让界面稳定
            print(f"[WorkerB] 等待界面稳定...", flush=True)
            time.sleep(1)

            # 聚焦输入框并读取消息
            print(f"[WorkerB] 聚焦输入框", flush=True)
            focus_input_near_send()
            time.sleep(0.5)
            
            print(f"[WorkerB] 读取消息", flush=True)
            messages = get_current_chat_messages()
            print(f"[WorkerB] 读取到消息: {messages}", flush=True)
            
            # 生成 AI 回复
            print(f"[WorkerB] 生成 AI 回复", flush=True)
            reply = build_ai_reply(messages, session_info=info)
            
            if reply:
                print(f"[WorkerB] 输入回复: {reply}", flush=True)
                type_reply_slowly(reply)
                
                print(f"[WorkerB] 点击发送", flush=True)
                click_send_button()
                time.sleep(0.5)
                
                # 记录已回复
                _replied_messages.append(reply)
                print(f"[WorkerB] 回复完成，通知 ListenerA", flush=True)
                
                # 回复 ACK
                client_socket.send("ACK".encode("utf-8"))
            else:
                print(f"[WorkerB] AI 未生成回复", flush=True)
                client_socket.send("NO_REPLY".encode("utf-8"))
        
        except Exception as e:
            print(f"[WorkerB] 处理消息失败: {e}", flush=True)
            client_socket.send("FAIL".encode("utf-8"))
    
    except json.JSONDecodeError:
        print(f"[WorkerB] JSON 解析失败", flush=True)
        client_socket.send("FAIL".encode("utf-8"))
    except Exception as e:
        print(f"[WorkerB] 连接处理出错: {e}", flush=True)
    finally:
        client_socket.close()


def main():
    """启动 TCP 服务器，等待 wechat_listener 的连接。"""
    print(f"[WorkerB] 启动 TCP 服务器，监听 {SERVER_HOST}:{SERVER_PORT}", flush=True)
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((SERVER_HOST, SERVER_PORT))
    server_socket.listen(5)
    
    print(f"[WorkerB] 服务器就绪，等待指令...", flush=True)
    
    try:
        while True:
            client_socket, addr = server_socket.accept()
            print(f"[WorkerB] 来自 {addr} 的连接", flush=True)
            handle_client(client_socket, addr)
    except KeyboardInterrupt:
        print(f"\n[WorkerB] 服务器关闭", flush=True)
    finally:
        server_socket.close()


if __name__ == "__main__":
    main()
