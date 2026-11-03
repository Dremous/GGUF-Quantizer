# GGUF Quantizer

上传 **FP16 GGUF** → 选择量化参数 → 下载量化结果 的 WebUI Docker 应用。

基于 [llama.cpp](https://github.com/ggml-org/llama.cpp) 的 `llama-quantize` 工具，提供简单直观的网页界面进行 GGUF 模型量化。

## 功能

- 📤 **上传**：拖拽或点击上传 FP16（float16）GGUF 模型文件
- ⚙️ **量化参数**：选择量化类型（q4_K_M、q5_K_M、q8_0、IQ 系等），自定义输出文件名
- 📊 **实时进度**：量化过程中实时展示日志输出
- ⬇️ **下载**：完成后一键下载量化结果

## 快速开始

前置要求：已安装 Docker（及 Docker Compose v2）。

```bash
git clone https://github.com/Dremous/GGUF-Quantizer.git
cd GGUF-Quantizer

# 构建并启动（首次构建需编译 llama.cpp，耗时较长，需联网）
docker compose up -d --build
```

打开浏览器访问 **http://localhost:8000**

## 使用步骤

1. **上传** FP16 GGUF 文件（`.gguf` 后缀，默认上限 4 GiB，可用环境变量调整）
2. **选择量化类型**（详见下表），可选填输出文件名
3. 点击 **开始量化**，等待进度与日志
4. 完成后点击 **下载量化结果**

## 量化类型说明

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

> 经验值：一般场景推荐 **q4_K_M**（体积约 1/4，质量与速度均衡）；追求质量用 q6_K / q8_K；追求最小体积用 q2_K / iq4_xs。

## 配置（环境变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAX_UPLOAD_MB` | `4096` | 单个上传文件大小上限（MB） |
| `CLEANUP_HOURS` | `12` | 上传/输出文件自动清理时间（小时） |
| `AUTO_CLEAN_OUTPUTS` | `1` | 是否自动清理量化结果文件 |
| `DATA_DIR` | `/data` | 数据目录（挂载卷） |

## 安全说明

- 服务以非 root 用户运行
- 上传文件校验 GGUF 魔数，拒绝非 GGUF 文件
- 量化类型白名单校验，输出文件名做安全清洗，命令参数化调用（无 shell 注入）
- 量化结果为纯 CPU 计算，无需 GPU

## 目录结构

```
gguf-quantizer/
├── Dockerfile              # 两阶段构建：编译 llama-quantize + Python 运行时
├── docker-compose.yml      # 一键启动编排
├── app/
│   ├── main.py             # FastAPI Web 服务
│   ├── quantizer.py        # 后台量化作业管理
│   ├── requirements.txt
│   └── static/index.html   # 单页前端
└── README.md
```

## 二次开发 / 本地测试（无需 Docker）

```bash
# 需要本机有 llama-quantize 可执行文件
pip install -r app/requirements.txt
cd app
DATA_DIR=./data python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

## 许可

本项目基于 llama.cpp（MIT License）开发，许可协议为 **MIT**。
