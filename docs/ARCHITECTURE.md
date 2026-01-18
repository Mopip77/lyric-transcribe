# 技术架构文档

## 概述

Lyric Transcribe 是一个基于 FastAPI 的音频转歌词 Web 应用，采用异步事件驱动架构，支持实时进度流式传输。系统通过 Whisper AI 进行语音识别，并将同步歌词嵌入到 MP3 文件的 ID3 标签中。

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web Browser                               │
│  ┌──────────────┐         ┌──────────────────────────────────┐ │
│  │ Static HTML  │◄────────┤  SSE EventSource Connection      │ │
│  │  Interface   │         │  (Real-time Progress Stream)     │ │
│  └──────┬───────┘         └──────────────▲───────────────────┘ │
│         │ REST API                       │ SSE Events           │
└─────────┼────────────────────────────────┼─────────────────────┘
          │                                │
          ▼                                │
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  API Endpoints Layer                                      │  │
│  │  • GET  /api/config      • GET  /api/files               │  │
│  │  • POST /api/config      • POST /api/task/start          │  │
│  │  • GET  /api/models      • GET  /api/task/status         │  │
│  │  • POST /api/task/cancel • GET  /api/task/stream (SSE)   │  │
│  └───────────────────────┬──────────────────────────────────┘  │
│                          │                                      │
│  ┌───────────────────────▼──────────────────────────────────┐  │
│  │              Task Manager (Singleton)                     │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │  Event Broadcasting System                         │  │  │
│  │  │  • output_buffer (deque, maxlen=2000)             │  │  │
│  │  │  • _subscribers (list of asyncio.Queue)           │  │  │
│  │  │  • broadcast() → all subscribers                  │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                                                            │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │  Task Execution Engine                             │  │  │
│  │  │  • Async task runner (_run_task)                   │  │  │
│  │  │  • ThreadPoolExecutor (max_workers=1)              │  │  │
│  │  │  • Thread-safe Queue for callbacks                 │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └───────────────────────┬──────────────────────────────────┘  │
│                          │                                      │
│         ┌────────────────┼────────────────┐                    │
│         │                │                │                     │
│         ▼                ▼                ▼                     │
│  ┌──────────┐   ┌───────────────┐  ┌─────────┐               │
│  │Transcriber│   │  Tagger       │  │ Config  │               │
│  │ Module    │   │  Module       │  │ Manager │               │
│  └─────┬─────┘   └───────┬───────┘  └─────────┘               │
│        │                 │                                      │
└────────┼─────────────────┼──────────────────────────────────────┘
         │                 │
         ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Dependencies                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ pywhispercpp │  │   mutagen    │  │    FFmpeg    │         │
│  │ (Whisper AI) │  │ (ID3 Tags)   │  │ (Audio Conv) │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

## 核心组件详解

### 1. FastAPI Application (app.py)

**职责**：
- HTTP 请求路由和响应处理
- 静态文件服务（Web 界面）
- SSE 连接管理
- 配置文件持久化

**关键设计**：
```python
# SSE 流式响应
@app.get("/api/task/stream")
async def task_stream():
    async def event_generator():
        queue = task_manager.subscribe()  # 订阅事件
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
                if event['type'] in ['task_complete', 'task_cancelled']:
                    break
        finally:
            task_manager.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**API 端点设计**：
- RESTful 风格：资源导向的 URL 设计
- 状态查询端点：支持浏览器刷新恢复
- 流式端点：SSE 协议实现实时推送

### 2. Task Manager (task_manager.py)

**架构模式**：单例模式（Singleton）

**核心数据结构**：

```python
class TaskManager:
    current_task: Task | None              # 当前正在执行的任务
    output_buffer: deque[dict]             # 事件缓冲区（maxlen=2000）
    _subscribers: list[asyncio.Queue]      # SSE 订阅者列表
    _executor: ThreadPoolExecutor          # 线程池（处理阻塞操作）
```

**事件广播机制**：

```
┌──────────────────────────────────────────────────────────┐
│                   broadcast(event)                        │
│  1. Add to output_buffer (for recovery)                  │
│  2. Send to all _subscribers (active SSE connections)    │
│  3. Remove dead/full queues                              │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
         ┌─────────────────┴──────────────────┐
         │                                    │
         ▼                                    ▼
    ┌─────────┐                         ┌─────────┐
    │ Queue 1 │                         │ Queue N │
    │(Client1)│                         │(ClientN)│
    └─────────┘                         └─────────┘
```

**任务处理流程**：

```
start_task()
    │
    ├─> 创建 Task 对象
    ├─> 清空 output_buffer
    ├─> 启动异步任务 _run_task()
    │
    └─> _run_task() [Async Loop]
         │
         ├─> For each FileTask:
         │    │
         │    ├─> Phase 1: Transcription
         │    │    ├─> 检查 LRC 是否存在
         │    │    ├─> 在线程池中运行 transcribe_audio()
         │    │    ├─> 通过 Queue 收集回调事件
         │    │    └─> broadcast('transcribe_line')
         │    │
         │    ├─> Phase 2: Embedding
         │    │    ├─> 检查 MP3 是否存在
         │    │    ├─> 在线程池中运行 embed_lyric()
         │    │    └─> broadcast('progress')
         │    │
         │    └─> broadcast('file_complete')
         │
         └─> broadcast('task_complete')
```

**线程安全设计**：

```python
# 同步线程 → 异步事件循环的桥接
line_queue: ThreadQueue = ThreadQueue()  # 线程安全队列

def on_transcribe_line(timestamp: str, text: str):
    line_queue.put(("line", timestamp, text))  # 在工作线程中调用

# 在异步循环中轮询
while not finished:
    try:
        item = line_queue.get_nowait()
        await broadcast("transcribe_line", {...})
    except QueueEmpty:
        await asyncio.sleep(0.1)
```

### 3. Transcriber Module (transcriber.py)

**核心流程**：

```
transcribe_audio()
    │
    ├─> 1. FFmpeg: 输入音频 → WAV (16kHz, mono)
    │
    ├─> 2. 初始化 Whisper 模型
    │      Model(model_name, print_realtime=False)
    │
    ├─> 3. 转录 with 回调
    │      whisper.transcribe(
    │          wav_path,
    │          language=language,
    │          initial_prompt=prompt,
    │          new_segment_callback=on_new_segment  ← 实时回调
    │      )
    │
    ├─> 4. 回调函数处理
    │      def on_new_segment(segment):
    │          timestamp = format_timestamp(segment.t0 / 100.0)
    │          lrc_lines.append(f"{timestamp}{segment.text}")
    │          callback(timestamp, text)  ← 通知上层
    │
    └─> 5. 写入 LRC 文件
```

**时间戳格式**：
- Whisper 输出：centiseconds (1/100 秒)
- LRC 格式：`[mm:ss.xx]`
- 转换公式：`seconds = segment.t0 / 100.0`

### 4. Tagger Module (tagger.py)

**ID3 标签嵌入流程**：

```
embed_lyric()
    │
    ├─> 1. 音频格式转换（如需要）
    │      非 MP3 → FFmpeg → MP3 (libmp3lame, qscale=2)
    │
    ├─> 2. 解析 LRC 文件
    │      parse_lrc() → [(text, time_ms), ...]
    │
    ├─> 3. 添加 ID3v2 标签
    │      ├─> TIT2: 标题（文件名）
    │      ├─> TPE1: 歌手（singer_name）
    │      ├─> TALB: 专辑（album_name）
    │      ├─> SYLT: 同步歌词
    │      │    • encoding=UTF8
    │      │    • lang="zho"
    │      │    • format=2 (milliseconds)
    │      │    • type=1 (lyrics)
    │      └─> APIC: 封面图片（cover_path）
    │           • type=3 (Cover front)
    │           • mime: image/jpeg or image/png
    │
    └─> 4. 保存 MP3 文件
```

**SYLT vs USLT**：
- 本项目使用 **SYLT (Synchronized Lyrics)**
- SYLT 包含时间戳，支持卡拉 OK 效果
- 格式：`[(text, milliseconds), ...]`

## 数据模型

### Pydantic Models (models.py)

```python
# 核心枚举
class TaskPhase(Enum):
    PENDING → TRANSCRIBING → EMBEDDING → COMPLETED/FAILED/CANCELLED

class FileStatus(Enum):
    PENDING → PROCESSING → COMPLETED/FAILED/SKIPPED

# 配置模型
class Config:
    source_dir: str          # 源文件目录
    lyric_dir: str           # LRC 输出目录
    output_dir: str          # MP3 输出目录
    model: str               # Whisper 模型
    language: str            # 语言代码
    prompt: str              # 提示词
    singer_name: str         # 歌手名
    album_name: str          # 专辑名
    cover_path: str          # 封面路径

# 任务进度
class TaskProgress:
    current: int             # 当前文件索引
    total: int               # 总文件数
    phase: TaskPhase         # 当前阶段
    file: str                # 当前文件名
    duration: str            # 文件时长 "mm:ss"

# 任务状态（用于恢复）
class TaskStatus:
    running: bool            # 是否运行中
    progress: TaskProgress   # 进度信息
    recent_output: list      # 缓冲的事件列表
    start_time: float        # 任务开始时间戳
```

## 异步与并发设计

### 线程模型

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Thread                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         FastAPI/Uvicorn Event Loop                    │  │
│  │  • HTTP Request Handling                              │  │
│  │  • SSE Connection Management                          │  │
│  │  • Task Scheduling                                    │  │
│  └──────────────────┬───────────────────────────────────┘  │
│                     │ loop.run_in_executor()                │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              ThreadPoolExecutor (max_workers=1)              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Worker Thread                                        │  │
│  │  • transcribe_audio() - CPU 密集                      │  │
│  │  • embed_lyric() - I/O 密集                          │  │
│  │  • get_audio_duration() - I/O                        │  │
│  └──────────────────┬───────────────────────────────────┘  │
│                     │ ThreadQueue                           │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
                 Async Event Loop
                 (via queue polling)
```

**为什么使用 ThreadPoolExecutor？**
1. Whisper 模型推理是 CPU 密集型操作，阻塞式
2. FFmpeg 调用是同步的子进程操作
3. mutagen 的 ID3 写入是同步 I/O

**为什么 max_workers=1？**
1. 音频转录是内存密集型，并行会导致 OOM
2. 保证文件按顺序处理，避免竞争条件
3. 简化状态管理（单一活动任务）

### 事件流设计

```
[Worker Thread]                 [Main Thread]
     │                               │
     │  transcribe callback          │
     ├──────────────────────────────►│
     │  line_queue.put()             │ queue.get_nowait()
     │                               │
     │                               ├─► broadcast()
     │                               │
     │                               ├─► output_buffer.append()
     │                               │
     │                               ├─► For each subscriber:
     │                               │       queue.put_nowait(event)
     │                               │
     │                               ▼
     │                        [SSE Connections]
     │                               │
     │                               ├─► Client 1
     │                               ├─► Client 2
     │                               └─► Client N
```

## SSE 实时通信

### 事件类型

| Event Type | Data | 触发时机 |
|------------|------|----------|
| `progress` | `{current, total, phase, file, duration}` | 每个文件开始处理 |
| `transcribe_line` | `{time, text}` | 每识别一行歌词 |
| `transcribe_complete` | `{file}` | 转录完成 |
| `file_complete` | `{file, success, message}` | 文件处理完成 |
| `task_complete` | `{success_count, fail_count}` | 所有文件处理完成 |
| `task_cancelled` | `{}` | 任务被取消 |
| `error` | `{file, message}` | 发生错误 |

### 断线重连机制

```
Client Connects
    │
    ├─> 1. 调用 GET /api/task/status
    │      获取 recent_output (最多 2000 个事件)
    │
    ├─> 2. 重放缓冲事件
    │      恢复到最新状态
    │
    └─> 3. 连接 SSE 端点
         接收后续实时事件
```

**缓冲区设计**：
- `output_buffer = deque(maxlen=2000)`
- 为什么是 2000？
  - 长音频文件（如 5 分钟歌曲）可能产生 500+ 歌词行
  - 加上进度事件、完成事件等
  - 提供足够的恢复窗口

### 连接保活

```python
# 30 秒超时 + keepalive
try:
    event = await asyncio.wait_for(queue.get(), timeout=30.0)
    yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
except asyncio.TimeoutError:
    yield ": keepalive\n\n"  # SSE 注释行保持连接
```

## 智能文件跳过

### 跳过逻辑

```python
# 转录阶段
if Path(lyric_path).exists():
    skip_transcription()  # LRC 已存在
else:
    transcribe_audio()

# 嵌入阶段
if Path(output_path).exists():
    skip_embedding()  # MP3 已存在
else:
    embed_lyric()
```

**优势**：
1. 支持增量处理：新增文件不影响已处理文件
2. 断点续传：任务失败后可重新启动，跳过成功的文件
3. 节省时间：避免重复转录

## 性能优化

### 1. 音频预处理

```bash
# FFmpeg 参数优化
ffmpeg -i input.m4a \
    -ar 16000 \      # 降采样到 16kHz (Whisper 要求)
    -ac 1 \          # 转单声道 (减少计算量)
    -y \
    output.wav
```

### 2. 模型选择

| 场景 | 推荐模型 | 理由 |
|------|----------|------|
| 开发测试 | tiny | 快速验证流程 |
| 日常使用 | large-v3-turbo | 速度与准确度平衡 |
| 生产环境 | large-v3-turbo | 最佳性价比 |
| 高质量需求 | large-v3 | 最高准确度 |

### 3. 内存管理

- 单线程处理：避免多个模型同时加载
- 临时文件清理：`finally` 块确保 WAV 文件删除
- 事件缓冲限制：`deque(maxlen=2000)` 防止内存泄漏

## 错误处理

### 分层错误处理

```
API Layer (app.py)
    │
    ├─> HTTPException → 返回 4xx/5xx
    │
Task Manager (task_manager.py)
    │
    ├─> try-except → broadcast('error')
    ├─> file_task.status = FAILED
    ├─> task.fail_count += 1
    │
Worker Modules
    │
    ├─> transcriber.py → RuntimeError
    └─> tagger.py → RuntimeError
```

### 错误恢复策略

1. **文件级隔离**：单个文件失败不影响其他文件
2. **状态保存**：失败文件标记为 FAILED，可查询
3. **用户通知**：通过 SSE 实时推送错误信息
4. **任务继续**：遇到错误继续处理下一个文件

## 安全考虑

### 1. 路径安全

```python
# 所有路径通过 Path 对象处理
source_path = Path(config.source_dir) / filename
# 避免路径遍历攻击
if not source_path.exists():
    raise HTTPException(status_code=400)
```

### 2. 文件类型验证

```python
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".mp4", ".wav", ".flac", ".ogg", ".aac"}
if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
    continue  # 跳过非音频文件
```

### 3. 资源限制

- 单任务执行：防止资源耗尽
- 队列大小限制：防止内存泄漏
- 超时机制：SSE 30 秒超时

## 扩展性

### 水平扩展方案

当前架构是单机版，若需要水平扩展：

```
┌──────────────────────────────────────────────────────────┐
│                     Load Balancer                         │
└────────────────────┬──────────────────┬──────────────────┘
                     │                  │
         ┌───────────▼──────┐  ┌───────▼──────────┐
         │   Worker 1       │  │   Worker 2       │
         │  (Task Executor) │  │  (Task Executor) │
         └───────────┬──────┘  └───────┬──────────┘
                     │                  │
         ┌───────────▼──────────────────▼──────────┐
         │         Redis Pub/Sub                    │
         │  • Task Queue                            │
         │  • Event Broadcasting                    │
         └──────────────────────────────────────────┘
```

**改造要点**：
1. TaskManager 从单例改为分布式任务队列（Celery/RQ）
2. output_buffer 迁移到 Redis
3. SSE 通过 Redis Pub/Sub 广播
4. 文件存储使用共享存储（NFS/S3）

### 垂直扩展方案

提升单机性能：

1. **GPU 加速**：使用 faster-whisper 或 whisper.cpp GPU 版本
2. **批量处理**：实现 Whisper 批量推理
3. **模型缓存**：预加载模型到内存
4. **并行转录**：多 GPU 情况下并行处理文件

## 监控与日志

### 建议添加的监控指标

```python
# Prometheus metrics
transcription_duration_seconds = Histogram(...)
files_processed_total = Counter(...)
active_sse_connections = Gauge(...)
task_queue_size = Gauge(...)
```

### 日志记录

```python
import logging

logger = logging.getLogger(__name__)

# 关键事件日志
logger.info(f"Task started: {len(files)} files")
logger.info(f"Transcribing: {filename}")
logger.error(f"Transcription failed: {filename}, error: {e}")
logger.info(f"Task completed: {success}/{total} files")
```

## 测试策略

### 单元测试

```python
# test_streaming.py 已包含
- test_transcriber_callback()      # 测试转录回调
- test_task_manager_streaming()    # 测试事件流
- test_many_events()               # 压力测试（500 事件）
- test_buffer_limits()             # 缓冲区限制
```

### 集成测试

```bash
# 端到端测试
1. 启动服务器
2. test_sse_client.py 连接 SSE
3. 提交任务
4. 验证事件流
5. 检查输出文件
```

### 性能测试

```python
# 建议添加
- test_long_audio()       # 测试长音频（10+ 分钟）
- test_many_files()       # 测试批量处理（100+ 文件）
- test_concurrent_sse()   # 测试多客户端同时连接
```

## 技术债务与改进方向

### 当前限制

1. **单任务限制**：同时只能运行一个任务
2. **单线程转录**：无法利用多核 CPU
3. **内存缓冲**：重启后丢失事件历史
4. **文件存储**：依赖本地文件系统

### 改进方向

1. **任务队列**：支持多任务排队
2. **进度持久化**：SQLite 存储任务状态
3. **WebSocket**：双向通信支持取消、暂停
4. **云存储集成**：S3/OSS 支持
5. **用户系统**：多用户隔离
6. **批量优化**：Whisper 批量推理

## 总结

本架构的核心设计理念：

1. **简单优先**：单例模式、单任务执行，降低复杂度
2. **实时反馈**：SSE 流式传输，提升用户体验
3. **容错性**：文件级隔离、智能跳过、错误恢复
4. **可扩展**：模块化设计，易于改造为分布式架构

适用场景：
- ✅ 个人/小团队使用
- ✅ 中小规模音频批处理（< 1000 文件/批）
- ✅ 本地部署、局域网服务
- ❌ 大规模并发（需改造为分布式）
- ❌ 公有云 SaaS（需增加用户系统、资源隔离）
