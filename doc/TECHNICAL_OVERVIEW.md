# 图片翻译 POC 技术说明

## 1. 文档目的

本文根据当前仓库代码整理，描述图片翻译 POC 的系统边界、技术架构、主要模块、运行流程、接口、配置、部署和验证方式。文档对应当前插件版本 `0.2.1`，以代码实现为准。

项目面向公司内部小规模使用。用户在 Chrome 或 Edge 中右键图片，插件将图片提交到 Linux GPU 后端；后端使用 PaddleOCR 识别文字和坐标，使用大模型或本地 NLLB 翻译，再将译文绘制回图片。普通网页优先原位替换，浏览器预览页或复杂附件页面使用独立结果页兜底。

## 2. 系统边界

### 2.1 已实现能力

- Chrome/Edge Manifest V3 浏览器扩展。
- 图片右键菜单、服务配置、语言选择和健康检查。
- 普通网页图片原位显示译图，并支持原图、译图、下载和关闭。
- 原位回写失败时使用扩展结果页展示原图和译图。
- PaddleOCR v5 本地检测、识别和文字方向处理。
- OpenAI Chat Completions 兼容的大模型翻译。
- NLLB-200 本地翻译及可选 fastText 自动语言识别。
- OpenCV 图像修复和 Pillow 译文排版。
- Linux 原生后台运行、systemd 示例和 Docker GPU 部署配置。
- 请求链路日志、模型文件校验、GPU 运行时校验和基础单元测试。

### 2.2 当前主要边界

- 一次只处理一张图片，没有网页批量翻译。
- OCR 模型对不同文字体系的覆盖能力取决于实际模型。
- 每个 OCR 区域独立翻译，未进行段落重组。
- 浏览器内部页面不能注入 Content Script，只能采用 URL 获取或截图后打开结果页。
- `blob:`、Canvas、CSS 背景图、跨域 iframe 和受保护资源未被完整支持。
- 后端没有用户认证、租户隔离、任务队列和持久化任务记录。
- 当前实现定位为 POC，不是高并发生产服务。

## 3. 总体架构

```text
Chrome / Edge
  |
  | 右键图片
  v
Manifest V3 Service Worker
  |-- 普通网页：通知 Content Script 并获取图片
  |-- 直接预览：通过 srcUrl 获取图片
  |-- 特殊页面：captureVisibleTab 截图兜底
  |
  | multipart/form-data
  v
FastAPI /v1/translate-image
  |
  +--> 图片大小、像素和格式校验
  +--> PaddleOCR：文字检测、识别、坐标和置信度
  +--> LLM 或 NLLB：按 OCR 区域翻译
  +--> OpenCV：清除原文字
  +--> Pillow：自适应字号绘制译文
  |
  v
PNG 结果图
  |
  +--> Content Script 原位替换
  `--> IndexedDB + result.html 结果页兜底
```

后端是同步单进程设计。`ImageTranslationPipeline` 持有进程级锁，同一进程内的 OCR 和翻译推理串行执行，以避免共享模型状态竞争并限制 GPU 峰值显存。

## 4. 项目目录

```text
app/
  config.py                 配置模型和环境变量
  domain.py                 OCR、翻译区域领域对象
  languages.py              语言及 NLLB 编码映射
  main.py                   FastAPI 应用和 HTTP 接口
  pipeline.py               OCR、翻译、渲染编排
  services/
    ocr.py                  PaddleOCR 适配器
    translator.py           LLM、NLLB、自动检测和回退
    renderer.py             图像修复与文字绘制

extension/
  manifest.json             Manifest V3 清单
  service-worker.js         右键菜单、图片获取、后端请求和兜底
  content.js/css            原网页目标定位、替换和工具条
  popup.html/js/css         服务地址和语言设置
  result.html/js/css        独立结果页
  icons/3.png               当前插件图标

scripts/                    模型、运行时和启动校验脚本
deploy/                     systemd 服务示例
tests/                      不加载实际模型的基础单元测试
models/                     PaddleOCR、NLLB 和可选 fastText 模型
run.py                      Uvicorn 启动入口
start_background_native_linux.sh
                             Linux 后台启停脚本
```

## 5. 后端处理流程

### 5.1 应用启动

`run.py` 从 `Settings` 获取监听地址、端口和日志级别，再启动 Uvicorn。FastAPI lifespan 调用 `get_pipeline()`，在服务对外可用前初始化 OCR、翻译器和渲染器。

如果启用 OCR 预热，启动时会使用一张 `640 x 640` 黑色图片执行一次 PaddleOCR 推理。LLM 模式下 NLLB 回退器延迟加载，只有 LLM 失败且允许回退时才加载 NLLB。

### 5.2 HTTP 请求

插件以 `multipart/form-data` 调用：

```http
POST /v1/translate-image
```

字段如下：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `image` | 文件 | 必填 | 待翻译图片 |
| `source_language` | 字符串 | `auto` | 源语言代码 |
| `target_language` | 字符串 | `zh` | 目标语言代码，不能为 `auto` |
| `source_url` | 字符串 | 空 | 原始图片地址，用于链路日志 |

后端首先校验语言代码，然后读取文件内容。`ImageTranslationPipeline._decode()` 依次检查空文件、文件字节数、图片可解码性和总像素数。

### 5.3 OCR

`PaddleOcrService` 使用三个本地模型：

- `PP-OCRv5_server_det`：文字检测。
- `PP-OCRv5_server_rec`：文字识别。
- `PP-LCNet_x1_0_textline_ori`：文本行方向。

结果转换为 `TextRegion`，包含区域 ID、四点多边形、文字和置信度。低于 `OCR_MIN_SCORE`、空文本或非四边形结果会被过滤，接受的区域按顶部坐标和左侧坐标排序。

### 5.4 翻译

翻译器由 `TRANSLATION_PROVIDER` 决定。

#### LLM 模式

`LlmTranslator` 使用 `requests.Session` 调用：

```text
{LLM_BASE_URL}/chat/completions
```

请求要求模型返回以下结构：

```json
{
  "source_language": "tr",
  "translations": [
    {"id": 0, "text": "译文"}
  ]
}
```

程序校验每个输入 ID 是否有且只有一个译文，并恢复原始顺序。源语言为 `auto` 时，大模型同时返回检测到的 ISO 639-1 代码。批次数由 `LLM_BATCH_SIZE` 控制。

代理处理是显式的：`LLM_USE_ENV_PROXY=false` 时不继承系统 `HTTP_PROXY`、`HTTPS_PROXY` 等环境变量；`LLM_PROXY` 可以指定专用代理。

#### NLLB 模式

`NllbTranslator` 从本地目录加载 Hugging Face tokenizer 和模型，不在运行时联网。程序将项目语言代码转换为 NLLB 语言代码，按 `TRANSLATION_BATCH_SIZE` 批量生成译文。

选择 `auto` 时，NLLB 需要 `LANGUAGE_ID_MODEL` 指向 fastText `lid.176.bin`。没有该模型时必须手动选择源语言。

#### 回退策略

LLM 请求、响应格式或解析失败时，如果 `LLM_FALLBACK_TO_NLLB=true`，程序尝试使用 NLLB。若源语言为 `auto` 且未配置 fastText 模型，则无法执行自动语言回退，原始 LLM 异常会继续抛出。

### 5.5 图片渲染

`ImageRenderer` 将所有 OCR 多边形绘制为掩膜，经一次膨胀后使用 OpenCV Telea 算法修复原文字区域。译文在每个区域的轴对齐包围盒内逐字符换行，字号从上限向下搜索，使用背景亮度选择黑色或白色前景，并增加反色描边。

最终结果统一编码为 PNG。

### 5.6 响应

成功响应的媒体类型为 `image/png`，并返回：

| 响应头 | 含义 |
| --- | --- |
| `X-Detected-Language` | 实际源语言 |
| `X-Region-Count` | OCR 接受区域数 |
| `X-Elapsed-Ms` | 后端端到端耗时 |
| `Cache-Control: no-store` | 不缓存翻译结果 |

输入或参数错误返回 HTTP 400；未分类异常返回 HTTP 500，响应不暴露内部堆栈。

## 6. 浏览器插件流程

### 6.1 配置

插件 Popup 将以下配置保存到 `chrome.storage.sync`：

- `apiBaseUrl`
- `sourceLanguage`
- `targetLanguage`

“测试连接”调用 `/health`，显示翻译提供者和自动语言识别能力。语言表目前在插件与后端各维护一份。

### 6.2 普通网页图片

1. Content Script 捕获 `contextmenu`，记录图片节点、URL 和右键位置。
2. Service Worker 创建请求 ID，发送 `image-translation-started`。
3. Content Script 定位目标图片并返回 `{applied: true}`。
4. Service Worker 获取原图并上传后端。
5. 后端返回 PNG 后，Service Worker 发送 `image-translation-complete`。
6. Content Script 保存原始 `src`、`srcset` 和 `<picture><source>` 状态，替换为译图 Data URL。
7. 图片附近显示原图、译图、下载和关闭操作。

目标定位依次使用右键图片节点、请求 ID、图片 URL、右键位置附近图片和原生单图预览判断。

### 6.3 原位显示失败

Content Script 找不到图片或页面在请求过程中失联时，Service Worker 将原图和译图 Blob 保存到扩展 IndexedDB 的 `results` 对象仓库，然后打开 `result.html?id=...`。结果页支持原图/译图切换和下载。

记录在保存新结果时清理，过期时间为一小时。

### 6.4 浏览器图片预览和附件

当标签页 URL 与图片 URL 相同时，插件将其视为直接图片预览，不依赖页面 DOM，直接获取 `srcUrl` 并打开结果页。普通页面无法注入 Content Script 时，也优先采用 HTTP(S) 图片 URL 直取；非 HTTP(S) 场景尝试 `captureVisibleTab`。

浏览器内部页面、受保护页面、跨域附件和登录资源受 Chromium 安全策略、Cookie、Referer、CSP 和公司浏览器策略影响，插件不能绕过这些限制。

## 7. API 一览

### `GET /health`

返回服务状态、翻译提供者和自动语言检测能力，不执行模型推理。

### `GET /v1/languages`

返回语言代码、英文名称、中文名称和 NLLB 编码。

### `POST /v1/translate-image`

接收图片和语言参数，返回 PNG 译图。服务启动后可通过 `/docs` 查看 OpenAPI 页面。

## 8. 核心配置

### 8.1 服务与 OCR

| 环境变量 | 说明 |
| --- | --- |
| `APP_HOST` / `APP_PORT` | 监听地址和端口 |
| `LOG_LEVEL` | 日志级别 |
| `OCR_*_MODEL_DIR` | 三个 PaddleOCR 模型目录 |
| `OCR_DEVICE` | 例如 `gpu:0` |
| `OCR_PRECISION` | `fp16` 或 `fp32` |
| `OCR_MIN_SCORE` | OCR 最低置信度 |
| `OCR_WARMUP` | 是否启动预热 |

### 8.2 翻译

| 环境变量 | 说明 |
| --- | --- |
| `TRANSLATION_PROVIDER` | `llm` 或 `nllb` |
| `TRANSLATION_MODEL_DIR` | NLLB 本地目录 |
| `TRANSLATION_DEVICE` | 例如 `cuda:0` |
| `LLM_BASE_URL` / `LLM_MODEL` | 大模型地址和模型名 |
| `LLM_API_KEY` | 大模型密钥，只能放在实际私有配置中 |
| `LLM_TIMEOUT_SECONDS` | 请求超时 |
| `LLM_BATCH_SIZE` | 单次发送的 OCR 区域数 |
| `LLM_FALLBACK_TO_NLLB` | 是否启用 NLLB 回退 |
| `LANGUAGE_ID_MODEL` | fastText 自动检测模型，可为空 |

### 8.3 渲染和输入限制

| 环境变量 | 说明 |
| --- | --- |
| `RENDER_FONT_PATH` | 必须存在且覆盖目标字符的字体 |
| `RENDER_MIN_FONT_SIZE` / `RENDER_MAX_FONT_SIZE` | 字号范围 |
| `RENDER_INPAINT_RADIUS` | 图像修复半径 |
| `MAX_IMAGE_BYTES` | 上传字节数上限 |
| `MAX_IMAGE_PIXELS` | 解码后像素上限 |

实际密钥、内部地址和主机专用路径应放入 `.env.native`，不应写入示例文件、插件或技术文档。

## 9. Linux 运行与运维

当前原生部署默认使用：

```text
/data1/softsevice/anaconda3/envs/cp/bin/python
```

从项目根目录执行：

```bash
chmod +x start_background_native_linux.sh
./start_background_native_linux.sh start
./start_background_native_linux.sh status
./start_background_native_linux.sh restart
./start_background_native_linux.sh stop
```

脚本通过以下方式导入 `.env.native`：

```bash
set -a
source .env.native
set +a
```

启动前会校验模型和 GPU 运行时，后台日志默认为 `logs/image-translator.log`，PID 文件默认为 `image-translator.pid`。生产常驻可参考 `deploy/image-translator.service.example` 配置 systemd。

Docker 部署使用 CUDA 基础镜像、单独安装匹配版本的 PaddlePaddle GPU 和 PyTorch，并以只读方式挂载 `models`。宿主机必须安装 NVIDIA 驱动、Docker 和 NVIDIA Container Toolkit。

## 10. 日志与排障

后端为每次请求生成 12 位请求 ID，主要记录：

- 原始图片地址、文件名、类型和字节数。
- 图片解码尺寸。
- OCR 区域、置信度和文字。
- LLM 地址、模型、输入、HTTP 状态和输出。
- 检测语言、翻译结果、区域数和耗时。
- 结果图字节数。

浏览器 Service Worker 控制台记录右键菜单上下文、图片获取和翻译状态。Chrome 可在 `chrome://extensions` 的扩展详情中打开 Service Worker 检查窗口；Edge 使用 `edge://extensions`。

处理公司财务、OA 或个人信息图片时，应认识到当前 INFO 日志会包含 OCR 原文和译文，日志文件必须限制访问、设置轮转，并根据数据要求决定是否降低日志内容。

## 11. 验证方式

不加载实际模型的单元测试：

```bash
python -m unittest discover -s tests -v
python -m compileall -q app tests
```

部署前检查：

```bash
python scripts/validate_models.py --models models --verify-hashes
python scripts/check_linux_runtime.py
python scripts/validate_deployment_config.py
```

LLM 独立连通性：

```bash
python test_llm.py
```

接口冒烟测试：

```bash
curl -X POST http://127.0.0.1:8080/v1/translate-image \
  -F image=@sample.png \
  -F source_language=en \
  -F target_language=zh \
  -o translated.png
```

浏览器验收至少覆盖普通网页图片、直接打开的 HTTP(S) 图片、OA 附件、动态预览、翻译失败、页面中途关闭以及原图/译图/下载操作。

## 12. 相关文档

- `README.md`：项目摘要和快速开始。
- `LINUX_GPU_DEPLOYMENT.md`：Linux GPU 部署与插件使用详解。
- `doc/CURRENT_LIMITATIONS.md`：当前代码不足、风险和建议优先级。

