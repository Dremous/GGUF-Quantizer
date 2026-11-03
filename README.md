<div align="center">

# GGUF Quantizer

**上传 FP16 GGUF → 选择量化参数 → 下载量化结果**

基于 [llama.cpp](https://github.com/ggml-org/llama.cpp) `llama-quantize` 的 WebUI Docker 应用，
界面美观、组件化易维护。

[![Build & Push](https://github.com/Dremous/GGUF-Quantizer/actions/workflows/build-image.yml/badge.svg)](https://github.com/Dremous/GGUF-Quantizer/actions/workflows/build-image.yml)
[![Docker Image](https://img.shields.io/badge/image-ghcr.io%2Fdremous%2Fgguf--quantizer%3Alatest-10b981?style=flat-square&logo=docker&logoColor=white)](https://github.com/Dremous/GGUF-Quantizer/pkgs/container/gguf-quantizer)
[![llama.cpp](https://img.shields.io/badge/llama.cpp-latest-059669?style=flat-square)](https://github.com/ggml-org/llama.cpp)
[![Platform](https://img.shields.io/badge/platform-amd64%20%7C%20arm64-64748b?style=flat-square)](#-github-action-自动发布)
[![License](https://img.shields.io/badge/license-MIT-10b981?style=flat-square)](LICENSE)

[![Vue 3](https://img.shields.io/badge/Vue_3-42b883?style=flat-square&logo=vue.js&logoColor=white)](https://vuejs.org)
[![Vite](https://img.shields.io/badge/Vite-646cff?style=flat-square&logo=vite&logoColor=white)](https://vitejs.dev)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-38bdf8?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-2496ed?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com)

</div>

---

## ✨ 功能特性

- 📤 **上传**：拖拽或点击上传 FP16（float16）GGUF 模型文件，自动校验文件格式
- ⚙️ **量化参数**：分组选择量化类型（经典 / K-quant / IQ 系），自定义输出文件名
- 📊 **实时进度**：终端式日志实时滚动，进度条 + 状态徽章
- ⬇️ **下载**：量化完成一键下载结果
- 🐳 **自动发布**：GitHub Action 自动编译并发布多架构镜像到 GHCR

---

## 🚀 快速开始

前置要求：已安装 Docker（及 Docker Compose v2）。

### 方式一：使用已发布镜像（推荐，免编译）

```yaml
# docker-compose.pull.yml
services:
  gguf-quantizer:
    image: ghcr.io/dremous/gguf-quantizer:latest
    container_name: gguf-quantizer
    ports:
      - "8000:8000"
    volumes:
      - gguf-data:/data
    restart: unless-stopped
volumes:
  gguf-data:
```

```bash
docker compose -f docker-compose.pull.yml up -d
```

### 方式二：本地源码构建

```bash
git clone https://github.com/Dremous/GGUF-Quantizer.git
cd GGUF-Quantizer
docker compose up -d --build     # 首次需联网编译 llama.cpp，耗时较长
```

构建完成后打开 **http://localhost:8000** 即可使用。

---

## 📖 使用步骤

1. **上传** FP16 GGUF 文件（`.gguf` 后缀，默认上限 4 GiB，可用环境变量调整）
2. **选择量化类型**（见下表），可选填输出文件名
3. 点击 **开始量化**，等待进度与日志
4. 完成后点击 **下载量化结果**

---

## 🧮 量化类型说明

| 类型 | 说明 | 推荐 |
|------|------|:----:|
| q4_0 | 4-bit 经典量化，体积最小 | |
| q5_1 | 5-bit 经典量化，质量/体积均衡 | |
| q8_0 | 8-bit 经典量化，质量高 | |
| q2_K | 2-bit K-quant，体积最小 | |
| q3_K_M | 3-bit K-quant（中等） | |
| **q4_K_M** | **4-bit K-quant（中等）** | ★ |
| q5_K_M | 5-bit K-quant（中等） | |
| q6_K | 6-bit K-quant，质量较高 | |
| q8_K | 8-bit K-quant，质量很高 | |
| iq4_xs / iq4_nl | IQ 混合量化，体积更小 | |
| f16 / f32 | 保持 FP16 / 转 FP32 | |

> 💡 经验值：一般场景推荐 **q4_K_M**（体积约 1/4，质量与速度均衡）；
> 追求质量用 q6_K / q8_K；追求最小体积用 q2_K / iq4_xs。

---

## ⚙️ 配置（环境变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAX_UPLOAD_MB` | `4096` | 单个上传文件大小上限（MB） |
| `CLEANUP_HOURS` | `12` | 上传/输出文件自动清理时间（小时） |
| `AUTO_CLEAN_OUTPUTS` | `1` | 是否自动清理量化结果文件 |
| `DATA_DIR` | `/data` | 数据目录（挂载卷） |
| `WEB_DIST` | `/app/web` | 前端构建产物目录 |
| `APP_VERSION` | `dev` | 镜像版本（注入 `/api/health`） |

---

## 🤖 GitHub Action 自动发布

`.github/workflows/build-image.yml` 会在以下情况自动编译并发布**多架构（amd64/arm64）**镜像到 **GHCR**：

- 推送 `main` 分支或 `v*` 标签
- 手动触发（Actions → Run workflow）
- 每周日自动重建

**每次构建都会自动拉取最新的 llama.cpp 源码并编译最新 `llama-quantize`**：工作流会查询 llama.cpp `master` 的最新 commit，把其 SHA 作为 `LLAMA_CPP_REF` 注入构建——SHA 每次变化会令 Docker 层缓存失效，从而真正重新拉取、重新编译，不会被缓存复用旧版。

发布标签：`latest`、`<日期>`、`<日期>-<commit 短哈希>`，其余层（apt/npm/系统依赖）仍使用 gha 缓存加速，只有 llama.cpp 编译始终全新执行。

> 本地手动构建默认同样拉取最新：`docker compose up -d --build` 使用 `LLAMA_CPP_REF=master`；如需固定版本，可 `--build-arg LLAMA_CPP_REF=v0.8.0`。

> 可选：配置仓库 secret `WEBHOOK_URL`（飞书 / 企微 / 钉钉机器人地址），构建失败时自动推送告警。

---

## 🛠 二次开发 / 本地调试

### 后端

```bash
# 需要本机有 llama-quantize 可执行文件
python3 -m venv .venv && . .venv/bin/activate
pip install -r app/requirements.txt
DATA_DIR=./data python3 -m uvicorn main:app --app-dir app --host 0.0.0.0 --port 8000
```

### 前端（Vite 热更新）

```bash
cd frontend
npm install
npm run dev     # 访问 http://localhost:5173，/api 已代理到后端 8000
```

### 测试

```bash
# 端到端冒烟测试（用假 llama-quantize 二进制验证后端全流程）
.venv/bin/python tests/smoke_test.py
```

---

## 📂 目录结构

```
GGUF-Quantizer/
├── .github/workflows/build-image.yml   # CI：自动编译并发布 GHCR 镜像
├── Dockerfile                          # 三阶段构建（前端 + llama.cpp + 运行时）
├── docker-compose.yml                  # 本地构建编排
├── frontend/                           # Vue3 + Vite + Tailwind 前端
│   ├── src/
│   │   ├── App.vue
│   │   ├── api.js
│   │   └── components/                 # HealthBadge / UploadZone / QuantForm / JobPanel
│   └── package.json
├── app/                                # FastAPI 后端
│   ├── main.py
│   ├── quantizer.py                    # 后台量化作业管理
│   ├── docker-entrypoint.sh            # 入口：校正卷属主后降权运行
│   └── requirements.txt
├── docs/screenshot.png                 # 界面预览
├── tests/smoke_test.py                 # 端到端冒烟测试
└── README.md
```

---

## 🔒 安全说明

- 入口脚本以 root 校正挂载卷 `/data` 属主后立即用 `gosu` 降权，**uvicorn 实际以非 root 用户 `quantizer` 运行**（兼容 root 所有的旧卷）
- 上传文件校验 GGUF 魔数，拒绝非 GGUF 文件
- 量化类型白名单校验，输出文件名做安全清洗，命令参数化调用（无 shell 注入）
- 量化结果为纯 CPU 计算，无需 GPU

---

## 📄 许可

本项目基于 [llama.cpp](https://github.com/ggml-org/llama.cpp)（MIT License）开发，许可协议为 **MIT**，详见 [LICENSE](LICENSE)。
