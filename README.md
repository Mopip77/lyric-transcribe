# Lyric Transcribe

一个基于 Whisper AI 的音频转歌词工具，支持自动转录、实时进度流式传输和 ID3 标签嵌入。

## ✨ 特性

- 🎵 **智能转录**：使用 Whisper AI 模型自动将音频转换为同步歌词（LRC 格式）
- ⚡ **实时进度**：通过 Server-Sent Events (SSE) 实时查看转录进度
- 🏷️ **ID3 标签**：自动嵌入歌词、封面、歌手、专辑等元数据到 MP3 文件
- 🎯 **批量处理**：支持一次性处理多个音频文件
- 🔄 **智能恢复**：浏览器刷新后自动恢复任务进度
- 📱 **Web 界面**：简洁易用的网页操作界面

## 🚀 快速开始

### 环境要求

- Python 3.10+
- FFmpeg（用于音频格式转换）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 安装 FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt install ffmpeg
```

**Windows:**
从 [FFmpeg 官网](https://ffmpeg.org/download.html) 下载并安装

### 运行应用

```bash
python app.py
```

应用将在 http://localhost:8000 启动

## 📖 使用方法

1. **配置路径**
   - 打开 Web 界面
   - 设置源文件目录（音频文件所在位置）
   - 设置歌词输出目录（LRC 文件保存位置）
   - 设置 MP3 输出目录（带标签的 MP3 文件保存位置）

2. **配置转录参数**
   - 选择 Whisper 模型（推荐 `large-v3-turbo`）
   - 设置语言代码（如 `zh` 中文，`en` 英文）
   - 自定义提示词以提高转录准确度

3. **配置元数据**（可选）
   - 设置歌手名称
   - 设置专辑名称
   - 选择封面图片路径

4. **开始处理**
   - 选择要处理的文件
   - 点击"开始处理"
   - 实时查看转录进度和歌词

## 🎛️ 配置文件

应用会在首次运行时创建 `config.json` 配置文件：

```json
{
  "source_dir": "/path/to/audio/files",
  "lyric_dir": "/path/to/lyrics",
  "output_dir": "/path/to/output",
  "model": "large-v3-turbo",
  "language": "zh",
  "prompt": "歌词 简体中文",
  "singer_name": "歌手名",
  "album_name": "专辑名",
  "cover_path": "/path/to/cover.png"
}
```

## 🎵 支持的音频格式

- MP3 (.mp3)
- M4A (.m4a)
- MP4 (.mp4)
- WAV (.wav)
- FLAC (.flac)
- OGG (.ogg)
- AAC (.aac)

## 🧪 运行测试

```bash
# 测试转录流式传输和事件管理
python test_streaming.py

# 测试 SSE 客户端连接（需要先启动服务器）
python test_sse_client.py
```

## 📊 可用的 Whisper 模型

| 模型 | 大小 | 速度 | 准确度 | 推荐用途 |
|------|------|------|--------|----------|
| tiny | 最小 | 最快 | 较低 | 快速测试 |
| base | 小 | 快 | 一般 | 日常使用 |
| small | 中 | 中等 | 良好 | 平衡选择 |
| medium | 大 | 较慢 | 很好 | 高质量需求 |
| large-v3-turbo | 大 | 较快 | 最佳 | **推荐** |
| large-v3 | 最大 | 最慢 | 最佳 | 最高质量 |

## 🔧 技术栈

- **后端框架**：FastAPI
- **AI 模型**：Whisper (via pywhispercpp)
- **音频处理**：FFmpeg, mutagen
- **实时通信**：Server-Sent Events (SSE)
- **异步处理**：asyncio + ThreadPoolExecutor
- **前端**：原生 HTML/JavaScript

## 📚 API 文档

启动应用后访问 http://localhost:8000/docs 查看完整的 API 文档。

### 主要端点

- `GET /api/config` - 获取配置
- `POST /api/config` - 更新配置
- `GET /api/models` - 获取可用模型列表
- `GET /api/files` - 获取待处理文件列表
- `POST /api/task/start` - 开始处理任务
- `GET /api/task/status` - 获取任务状态
- `POST /api/task/cancel` - 取消任务
- `GET /api/task/stream` - SSE 实时进度流

## 🎯 工作流程

1. **扫描文件**：应用扫描源目录中的音频文件
2. **智能跳过**：已存在 LRC 或 MP3 的文件将被跳过
3. **音频转录**：
   - 使用 FFmpeg 将音频转换为 WAV 格式
   - Whisper AI 进行语音识别
   - 实时输出歌词行到前端
   - 保存为 LRC 格式
4. **标签嵌入**：
   - 将音频转换为 MP3（如需要）
   - 使用 mutagen 添加 ID3v2 标签
   - 嵌入同步歌词（SYLT）
   - 添加封面、歌手、专辑等元数据
5. **完成**：输出带完整标签的 MP3 文件

## 📁 项目结构

```
lyric-transcribe/
├── app.py              # FastAPI 应用主入口
├── models.py           # Pydantic 数据模型
├── task_manager.py     # 任务管理和 SSE 事件广播
├── transcriber.py      # Whisper 转录模块
├── tagger.py           # ID3 标签嵌入模块
├── config.json         # 配置文件（自动生成）
├── static/
│   └── index.html      # Web 前端界面
├── test_streaming.py   # 流式传输测试
└── test_sse_client.py  # SSE 客户端测试
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## ⚠️ 注意事项

- 首次使用时，Whisper 模型会自动下载，可能需要一些时间
- 模型文件较大（large-v3-turbo 约 1.5GB），请确保有足够的磁盘空间
- 转录长音频文件可能需要较长时间，建议使用较快的模型进行测试
- 建议在处理重要文件前先进行小规模测试

## 💡 提示

- **提高准确度**：在 `prompt` 中添加常见词汇，如歌手名、常见歌词短语
- **中文歌曲**：推荐使用 `language: "zh"` 和包含"歌词 简体中文"的提示词
- **英文歌曲**：使用 `language: "en"`
- **粤语歌曲**：可以在提示词中添加"粤语"以提高识别准确度
