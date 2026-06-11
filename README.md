# 模型智能体网站

这是一个前后端分离的多模型问答网站。

- 后端：`backend/server.py`
- 前端：`frontend/src/App.vue`、`frontend/src/main.js`
- 配置：`.env`

## 配置

`.env` 支持以下变量：

```env
BASE_URL="https://api.openai-proxy.org"
KEY="你的 API Key"
PORT=8000
SUMMARY_TRIGGER_TOKENS=3000
FORCE_NEW_CHAT_TOKENS=8000
RECENT_MESSAGE_COUNT=8
```

也可以使用 `API_KEY` 或 `OPENAI_API_KEY` 代替 `KEY`。

## 运行

首次或修改前端后，先在 `frontend` 目录构建 Vue：

```powershell
cd .\frontend
npm install
npm run build
```

然后在 `agent` 目录下执行后端：

```powershell
python .\backend\server.py
```

然后打开：

```text
http://127.0.0.1:8000
```

## 已支持模型

- `qwen3.7-max`
- `gemini-3.5-flash`
- `deepseek-v4-pro`
- `kimi-k2.6`
- `glm-5`

## 已支持工具

- 当前时间查询：使用本机时区数据库。
- 实时天气查询：使用 Open-Meteo 的地理编码和天气接口。

## RAG 文件检索

网站支持在左侧打开 `RAG 文件` 弹窗，上传并选择当前对话要使用的文件。

支持格式：

- `.txt`
- `.md`
- `.pdf`
- `.docx`
- `.doc`

说明：

- `.txt` 和 `.md` 会直接读取文本。
- `.docx` 使用内置 XML 抽取文本。
- `.pdf` 使用基础文本抽取，扫描版 PDF 或复杂排版 PDF 可能无法抽取内容。
- 每个对话可以选择不同的 RAG 文件，发送消息时只检索当前对话选择的文件。
- 上传后的文件保存在 `rag_store/`，该目录已加入 `.gitignore`。

## 记忆模式

- 未达到 `SUMMARY_TRIGGER_TOKENS` 时，后端会把完整历史对话发送给模型。
- 达到 `SUMMARY_TRIGGER_TOKENS` 后，后端会把较早消息压缩成长期记忆摘要，并保留最近 `RECENT_MESSAGE_COUNT` 条消息。
- 达到 `FORCE_NEW_CHAT_TOKENS` 后，前端和后端都会触发强制新对话，避免上下文过长。
