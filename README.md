# wechat_rag
自动化RAG微信模拟真人回复工具
# wechat_rag
自动化RAG微信模拟真人回复工具

本仓库包含两个核心脚本：`wechat_listener.py` 和 `wechat_worker.py`，它们协同工作以检测微信桌面版中的未读消息并利用 AI 自动回复。

---

## 文件说明

### `wechat_listener.py`

- **模式**：TCP 客户端。
- **职责**：
  1. 检查微信聊天列表中的未读消息。
  2. 解析聊天摘要并提取最后一条消息内容。
  3. 向本地 `wechat_worker` 进程发送 `name` 和 `info` 指令，并等待 `ACK`。
  4. 通过 `wechat_openclaw` 模块共享的工具函数进行聊天列表访问和文本提取。

- **运行方式**：

```bash
python wechat_listener.py
```

> 注意：在启动此脚本前需要确保微信桌面版已经打开，并且 `wechat_worker` 正在运行。

### `wechat_worker.py`

- **模式**：TCP 服务器（监听 `127.0.0.1:5555`）。
- **职责**：
  1. 接收来自 `wechat_listener` 的连接请求。
  2. 根据发送者的昵称搜索并打开对应的聊天窗口。
  3. 调用 AI 模型生成回复（通过 `build_ai_reply` 等函数）。
  4. 在微信界面输入并发送生成的回复，然后回复 `ACK` 给 listener。

- **运行方式**：

```bash
python wechat_worker.py
```

> 启动后，该脚本将持续运行并等待指令。按 `Ctrl+C` 可退出。

## 使用示例

1. 打开微信桌面版。
2. 启动 worker：
   ```bash
   python wechat_worker.py
   ```
3. 启动 listener（可以在另一个终端）：
   ```bash
   python wechat_listener.py
   ```
4. 当微信收到未读消息时，listener 会自动通知 worker，worker 会生成并发送 AI 回复。

## 依赖

- `uiautomation`
- 以及项目根目录下 `wechat_openclaw.py` 中定义的函数和逻辑。

确保在 Python 环境中安装了所需依赖，比如：

```bash
pip install uiautomation
```

## 许可证

请根据需要自定义相应的许可证和贡献声明。
