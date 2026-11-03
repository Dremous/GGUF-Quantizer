# ============================================================================
# GGUF Quantizer — 两阶段构建
#   阶段 1 (llama-build): 源码编译 llama.cpp 的 llama-quantize（CPU-only）
#   阶段 2 (runtime)   : 精简运行时 + Python Web 服务
# ============================================================================

# ---------- 阶段 1：编译量化工具 ----------
FROM ubuntu:24.04 AS llama-build

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# llama.cpp 版本标签（可用 --build-arg LLAMA_CPP_VERSION=<tag> 覆盖）
ARG LLAMA_CPP_VERSION=v0.8.0

RUN git clone --depth 1 --branch "${LLAMA_CPP_VERSION}" \
        https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp

WORKDIR /opt/llama.cpp

# CPU-only 构建：量化本身是纯 CPU 任务，无需 CUDA/ROCm/Metal/Vulkan
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release \
        -DGGML_CUDA=OFF \
        -DGGML_METAL=OFF \
        -DGGML_VULKAN=OFF \
        -DGGML_SYCL=OFF \
        -DGGML_HIP=OFF \
        -DLLAMA_CURL=OFF \
    && cmake --build build --config Release --target llama-quantize -j"$(nproc)" \
    && cp build/bin/llama-quantize /usr/local/bin/llama-quantize

# 构建产物自检
RUN llama-quantize --help >/dev/null

# ---------- 阶段 2：运行时 ----------
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    DATA_DIR=/data \
    MAX_UPLOAD_MB=4096 \
    CLEANUP_HOURS=12 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=llama-build /usr/local/bin/llama-quantize /usr/local/bin/llama-quantize

WORKDIR /app

COPY app/requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app/ ./

# 数据目录（上传、输出）
RUN mkdir -p /data/uploads /data/outputs

# 以非 root 运行
RUN useradd -m -u 10001 quantizer \
    && chown -R quantizer:quantizer /app /data
USER quantizer

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
