# Linux GPU 部署与浏览器插件使用说明

本文以服务器已经安装 NVIDIA 驱动、CUDA，并已配置好 Python 虚拟环境为前提。推荐直接使用现有 Python 环境原生部署；Docker 仅作为可选方案。

## 1. 部署前检查

以下示例约定：

```text
项目目录：/opt/image-translator-poc
Python：  /opt/image-translator-venv/bin/python
服务端口：8080
```

请将 Python 路径替换为服务器上的实际环境路径。先检查驱动、CUDA 和 Python：

```bash
nvidia-smi
nvcc --version
/actual/python/env/bin/python --version
/actual/python/env/bin/python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
/actual/python/env/bin/python -c "import paddle; print('paddle', paddle.__version__, 'cuda', paddle.device.is_compiled_with_cuda())"
```

`torch.cuda.is_available()` 和 `paddle.device.is_compiled_with_cuda()` 应为 `True`。如果任一项为 `False`，应先修复现有环境中的 GPU 框架版本，暂时不要启动服务。

## 2. 上传项目与检查模型

将完整项目上传到服务器，例如 `/opt/image-translator-poc`，进入项目并检查模型文件：

```bash
cd /opt/image-translator-poc
/actual/python/env/bin/python scripts/validate_models.py --models models --verify-hashes
```

当前项目要求至少包含：

```text
models/nllb-200-distilled-600M
models/v5/PP-OCRv5_server_det
models/v5/PP-OCRv5_server_rec
models/v5/PP-LCNet_x1_0_textline_ori
```

如果使用本地 NLLB 翻译，自动源语言检测需要额外的 `models/lid.176.bin`。如果使用下文的 LLM 翻译，插件的“自动识别”会由 LLM 从 OCR 文本中判断源语言，不依赖 `lid.176.bin`；但 LLM 服务必须能够稳定返回项目要求的 JSON 格式。

## 3. 安装应用依赖

激活服务器上已经配置好的 Python 环境：

```bash
source /actual/python/env/bin/activate
cd /opt/image-translator-poc
python -m pip install -r requirements.txt
```

`requirements.txt` 不安装或替换 PyTorch、PaddlePaddle 核心包，以免覆盖服务器中已适配 CUDA 的版本；它只补充 Web 服务、OCR 上层库、翻译及图像处理等应用依赖。

安装后执行项目运行时检查：

```bash
python scripts/check_linux_runtime.py
```

如果脚本提示缺包，继续在同一个虚拟环境中安装。不要切换到系统 Python。

## 4. 安装中文字体

结果图需要中文字体。Ubuntu/Debian 可执行：

```bash
sudo apt-get update
sudo apt-get install -y fonts-noto-cjk
fc-match "Noto Sans CJK SC"
```

其他发行版可安装等效的 Noto CJK 字体，并在 `.env.native` 中填写字体文件的绝对路径。

## 5. 配置服务

复制原生部署配置：

```bash
cd /opt/image-translator-poc
cp .env.native.example .env.native
```

编辑 `.env.native`，重点核对：

- OCR 检测、识别和方向分类模型的绝对路径
- NLLB 模型的绝对路径
- 字体文件的绝对路径
- 监听地址为 `0.0.0.0`
- 服务端口为 `8080` 或公司允许的其他端口
- OCR、翻译使用 GPU 的配置

`.env.native` 仅用于服务器本机，不应提交到代码仓库。

### 5.1 使用大模型翻译

OCR 仍使用 PaddleOCR 识别文字和坐标；翻译可以切换为兼容 OpenAI Chat Completions 协议的大模型服务。编辑 `.env.native`：

```env
TRANSLATION_PROVIDER=llm
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_API_KEY=
LLM_MODEL=default/deepseek-v3-2
LLM_TIMEOUT_SECONDS=120
LLM_TEMPERATURE=0.1
LLM_BATCH_SIZE=24
# Do not inherit HTTP(S)_PROXY from the shell unless the endpoint requires it.
LLM_USE_ENV_PROXY=false
LLM_PROXY=
LLM_FALLBACK_TO_NLLB=true
```

`LLM_BASE_URL` 可以指向：

- 公司内部提供的 OpenAI 兼容大模型代理。
- Linux 服务器上通过 vLLM 等方式启动的本地模型服务。
- 其他实现 `/v1/chat/completions` 的内网服务。

项目默认不使用系统环境中的 `HTTP_PROXY`、`HTTPS_PROXY` 和 `ALL_PROXY` 访问 LLM。这样可以避免代理服务器主动关闭到公司 LLM 网关的 HTTPS 连接。如果服务器必须通过代理访问，在 `.env.native` 中设置：

```env
LLM_USE_ENV_PROXY=true
```

或者显式指定代理：

```env
LLM_USE_ENV_PROXY=false
LLM_PROXY=http://proxy.company:8080
```

修改配置后需要重启服务：

```bash
./start_background_native_linux.sh restart
```

如果接口需要密钥，将其写入服务器 `.env.native` 的 `LLM_API_KEY`。不要将密钥写入插件、代码或 `.env.*.example` 文件。

当本地大模型服务和图片翻译后端位于同一台 Linux 服务器时，优先使用 `127.0.0.1` 地址，不需要向客户端开放大模型端口。可先单独验证接口：

```bash
curl "$LLM_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$LLM_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Translate hello to Chinese.\"}],\"stream\":false}"
```

也可以使用项目提供的独立测试程序验证模型接口。它只发送一条文本，不加载 OCR 或图片翻译模型：

```bash
cd /opt/image-translator-poc
${PYTHON_BIN:-/data1/softsevice/anaconda3/envs/cp/bin/python} \
  test_llm.py
```

默认发送“你好”。也可以传入自定义文本：

```bash
/data1/softsevice/anaconda3/envs/cp/bin/python \
  test_llm.py "请用一句话介绍你自己"
```

脚本默认读取项目根目录的 `.env.native`，并使用其中的 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`、`LLM_USE_ENV_PROXY` 和 `LLM_PROXY`。不要在终端命令或日志中打印 API Key。

`LLM_FALLBACK_TO_NLLB=true` 表示大模型超时、返回非法 JSON 或缺少译文时自动使用 NLLB。NLLB 采用延迟加载，不会在大模型正常工作时占用额外 GPU 显存。如果服务器没有安装 Torch 或不再保留 NLLB 模型，应设置：

```env
LLM_FALLBACK_TO_NLLB=false
```

使用 LLM 的“自动识别”时，服务会要求模型返回 `source_language`（小写 ISO-639-1 代码，例如土耳其语为 `tr`）和译文数组。若 LLM 自动识别失败并启用了 NLLB 回退，则 NLLB 仍需要 `LANGUAGE_ID_MODEL` 指向 `lid.176.bin`；否则接口会返回明确的配置错误。为了提高小语种稳定性，建议使用支持 JSON 输出或 JSON schema 的模型服务。

需要完全离线使用旧方案时设置：

```env
TRANSLATION_PROVIDER=nllb
```

## 6. 前台启动验证

方式一，直接加载配置并启动：

```bash
cd /opt/image-translator-poc
set -a
source .env.native
set +a
/actual/python/env/bin/python run.py
```

方式二，使用启动脚本：

```bash
cd /opt/image-translator-poc
chmod +x scripts/start_native_linux.sh
PROJECT_DIR=/opt/image-translator-poc \
PYTHON_BIN=/actual/python/env/bin/python \
scripts/start_native_linux.sh
```

### 6.1 后台运行脚本

项目根目录提供了适用于当前服务器 Python 环境的后台启动脚本：

```text
/data1/softsevice/anaconda3/envs/cp/bin/python
```

首次使用时执行：

```bash
cd /opt/image-translator-poc
chmod +x start_background_native_linux.sh
./start_background_native_linux.sh
```

脚本支持启动、重启、停止和状态查询：

```bash
./start_background_native_linux.sh start
./start_background_native_linux.sh restart
./start_background_native_linux.sh stop
./start_background_native_linux.sh status
```

其中，`restart` 会先读取 `image-translator.pid`，只停止该 PID 文件对应的本项目进程，等待进程退出后再重新执行模型校验、GPU 运行时检查并启动服务。不会使用 `pkill -f` 批量终止其他 Python 服务。

脚本内部会先定位项目根目录，再执行以下配置加载流程，并将环境变量传递给后台服务：

```bash
set -a
source .env.native
set +a
```

默认文件位置如下：

```text
PID 文件：image-translator.pid
日志文件：logs/image-translator.log
Python：  /data1/softsevice/anaconda3/envs/cp/bin/python
```

查看运行状态和日志：

```bash
cat image-translator.pid
ps -fp "$(cat image-translator.pid)"
tail -f logs/image-translator.log
curl http://127.0.0.1:8080/health
```

停止后台进程：

```bash
kill "$(cat image-translator.pid)"
rm -f image-translator.pid
```

如果 Conda 环境、配置文件或日志目录不同，可以通过环境变量覆盖默认值：

```bash
CONDA_ENV_PATH=/data1/softsevice/anaconda3/envs/cp \
ENV_FILE=/data1/service/image-translator-poc/.env.native \
LOG_DIR=/data1/service/image-translator-poc/logs \
./start_background_native_linux.sh
```

后台脚本启动前会执行模型校验和 GPU 运行时检查；任一检查失败时不会启动服务。脚本也会通过 PID 文件避免同一个项目被重复启动。

启动脚本会先校验模型和 GPU 运行时，再启动 API 服务。在服务器上验证：

```bash
curl http://127.0.0.1:8080/health
```

使用 LLM 翻译时预期返回类似：

```json
{"status":"ok","auto_language_detection":true,"translation_provider":"llm"}
```

再从安装插件的客户端电脑访问 `http://SERVER_IP:8080/health`。客户端无法访问时，检查服务监听地址、服务器防火墙、安全组和公司网络路由。

## 7. 配置 systemd 常驻运行

仓库提供了 `deploy/image-translator.service.example`。其中的项目目录、Python 路径、运行用户均为示例，必须按服务器实际情况修改。

可选地创建专用用户并授权项目目录：

```bash
sudo useradd --system --home /opt/image-translator-poc --shell /usr/sbin/nologin image-translator
sudo chown -R image-translator:image-translator /opt/image-translator-poc
```

复制服务文件：

```bash
sudo cp /opt/image-translator-poc/deploy/image-translator.service.example \
  /etc/systemd/system/image-translator.service
sudo editor /etc/systemd/system/image-translator.service
```

至少修改 `User`、`Group`、`WorkingDirectory`、`EnvironmentFile`、`PROJECT_DIR` 和 `PYTHON_BIN`。然后启用服务并查看日志：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now image-translator
sudo systemctl status image-translator
sudo journalctl -u image-translator -f
```

修改 `.env.native` 后执行：

```bash
sudo systemctl restart image-translator
```

## 8. 浏览器插件安装与使用

### 8.1 加载插件

插件支持 Chromium 内核浏览器。

Chrome：

1. 打开 `chrome://extensions`。
2. 开启右上角“开发者模式”。
3. 点击“加载已解压的扩展程序”。
4. 选择项目中的 `extension` 目录。

Edge：

1. 打开 `edge://extensions`。
2. 开启“开发人员模式”。
3. 点击“加载解压缩的扩展”。
4. 选择项目中的 `extension` 目录。

插件代码更新后，需要回到扩展管理页点击该插件的“重新加载”，并刷新已经打开的网页，使新版页面脚本生效。

### 8.2 连接翻译服务

1. 点击浏览器工具栏中的插件图标。
2. 服务地址填写 `http://SERVER_IP:8080`，末尾不需要 `/`。
3. 点击“测试连接”。
4. 选择源语言。列表现在显示中文和英文名称，例如“英语 / English”“土耳其语 / Turkish”。使用 LLM 翻译时可以选择“自动识别”；使用纯 NLLB 翻译时只有配置 `lid.176.bin` 后才能使用自动识别。
5. 选择目标语言“中文”或“英文”。
6. 点击“保存”。

对于混合语言图片，自动识别会以 OCR 文本批次检测出的主要语言为准；要求结果稳定时，建议手动选择占比最高的主要源语言。

### 8.3 右键翻译图片

1. 打开包含普通网页图片的页面。
2. 在图片上点击右键。
3. 选择“翻译此图片”。
4. 图片附近会显示“正在识别并翻译”的状态条。
5. 插件将图片地址和语言配置提交给服务器。
6. 处理完成后，当前网页中的原图片会直接替换为译图，不再打开新页面。
7. 状态条支持切换“原图 / 译图”、下载译图和关闭状态条。

耗时主要取决于图片尺寸、文字区域数量、首次模型加载和 GPU 性能。服务启动后的第一次请求通常会比后续请求慢。

### 8.4 插件使用限制

- 当前不支持 `blob:` 图片地址。
- 需要登录态、Referer 或特殊 Cookie 才能访问的受保护图片可能下载失败。
- CSS `background-image` 背景图不会出现图片右键菜单。
- LLM 模式支持自动识别源语言；纯 NLLB 模式需要配置 `lid.176.bin`。
- 一张图片包含多种语言时，只能按所选主要源语言翻译。
- 后端当前没有身份认证，只适合受控的公司内网。
- 某些公司浏览器策略可能限制扩展访问 HTTP 服务。
- Chrome 内置页、扩展商店和浏览器设置页不允许 content script 注入，不能原位替换图片。
- 对于直接打开的 HTTP(S) 附件图片，例如 `http://fssc.svolt.cn:8008/kkPreview/PROD_xxx/0.jpg`，插件会优先使用右键菜单提供的 `srcUrl` 直接下载原图并提交后端，不依赖预览页 DOM，也不会显示“未找到刚才选择的图片”。翻译完成后会打开插件结果页。
- 浏览器原生图片预览页无法注入 content script。插件会尝试截取当前可见浏览器区域，提交截图翻译，并在新的插件结果页中提供原图/译图切换和下载；截图可能包含浏览器预览工具栏或其他可见内容。
- 如果浏览器拒绝 `captureVisibleTab`（例如受保护页面、权限策略或特殊浏览器页面），这是浏览器安全限制，插件无法绕过，只能在普通网页中打开图片后再翻译。
- 当前初版一次操作一张图片；网页批量翻译和可视区域自动翻译留待后续迭代。

共享使用时，建议通过 Nginx 配置公司内网 HTTPS 域名，再将该 HTTPS 地址填入插件。这样更利于证书、访问日志、请求大小限制和后续身份认证的统一管理。

## 9. API 冒烟测试

健康检查：

```bash
curl http://127.0.0.1:8080/health
```

实际翻译接口参数以项目 API 文档为准。服务启动后可打开 `http://SERVER_IP:8080/docs`。

先使用一张文字清晰、尺寸适中的图片验证 OCR、NLLB 翻译和结果图渲染，再测试小语种、长图和复杂背景图片。

## 10. 可选：Docker GPU 部署

服务器已有稳定 Python GPU 环境时，原生部署路径最短。需要环境隔离或后续标准化发布时，可改用仓库中的 `Dockerfile`、`compose.yaml` 和 `.env.linux.example`。

Docker 方式额外要求 Docker Engine、NVIDIA Container Toolkit，以及与宿主机驱动兼容的容器 CUDA 运行时。基本流程：

```bash
cd /opt/image-translator-poc
cp .env.linux.example .env
docker compose build
docker compose up -d
docker compose logs -f
```

使用前仍应执行模型校验，并通过 `docker compose exec` 检查容器中的 Torch、Paddle GPU 可用性。Docker 不是本次部署的必需条件。

## 11. 常见问题

### 服务启动时找不到模型

检查 `.env.native` 中是否使用绝对路径，并执行：

```bash
cd /opt/image-translator-poc
/actual/python/env/bin/python scripts/validate_models.py --models models --verify-hashes
```

### 服务能启动但没有使用 GPU

在启动服务的同一个 Python 环境中执行：

```bash
/actual/python/env/bin/python scripts/check_linux_runtime.py
nvidia-smi
```

同时通过 `journalctl` 检查启动日志。不要只依据服务器安装过 CUDA 就判断 Python 框架已启用 GPU。

### 插件测试连接失败

依次确认：

1. 服务器本机 `curl http://127.0.0.1:8080/health` 成功。
2. 客户端浏览器能直接打开 `http://SERVER_IP:8080/health`。
3. `.env.native` 的监听地址不是 `127.0.0.1`。
4. 端口未被防火墙、安全组或代理拦截。
5. 插件中没有误填 `/docs`、`/health` 等路径。
6. 公司浏览器策略是否禁止扩展访问非 HTTPS 地址。

### LLM 请求出现 ProxyError

例如：

```text
requests.exceptions.ProxyError: HTTPSConnectionPool(host='llmproxy.gwm.cn', port=443)
```

这通常表示 Python `requests` 继承了服务器的 `HTTPS_PROXY` 或 `ALL_PROXY`，但代理服务器关闭了连接。先确认 `.env.native` 中为：

```env
LLM_USE_ENV_PROXY=false
LLM_PROXY=
```

然后重启服务并查看日志：

```bash
./start_background_native_linux.sh restart
tail -f logs/image-translator.log
```

可在服务器上分别检查直连和代理环境，但不要在命令行或日志中打印 API Key：

```bash
env | grep -iE '^(http|https|all|no)_proxy=' || true
curl -I --connect-timeout 10 https://llmproxy.gwm.cn/v1/models
```

如果直连失败而公司网络要求代理，则改为配置 `LLM_USE_ENV_PROXY=true`，或填写 `LLM_PROXY`。如果直连和代理都失败，需要由网络管理员确认服务器到 `llmproxy.gwm.cn:443` 的 DNS、防火墙、路由和代理白名单。

### 中文渲染为方框

安装 Noto CJK 字体，确认 `.env.native` 中字体路径正确，然后重启服务。
