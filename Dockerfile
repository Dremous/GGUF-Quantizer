# ============================================================================
# GGUF Quantizer — 三阶段构建
#   阶段 1 (frontend-build): Vue/Vite 前端构建（Tailwind）
#   阶段 2 (llama-build)   : llama.cpp llama-quantize 源码编译（CPU-only）
#   阶段 3 (runtime)       : 精简运行时 + Python Web 服务
#
# 版本号通过 --build-arg APP_VERSION=<tag> 注入（GitHub Action 会自动填写）。
# ============================================================================

# ---------- 阶段 1：前端构建 ----------
FROM node:22-alpine AS frontend-build

WORKDIR /web

# 先装依赖，充分利用层缓存
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# ---------- 阶段 2：编译量化工具 ----------
FROM ubuntu:24.04 AS llama-build

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 每次构建都拉取最新的 llama.cpp 源码（默认 master 分支 = 最新）。
# CI 会把当前 master 的最新 commit SHA 注入 LLAMA_CPP_REF：
#   SHA 每次变化 → Docker 层缓存自动失效 → 每次构建都会重新拉取并编译最新的 llama-quantize。
# 本地手动构建也可用 --build-arg LLAMA_CPP_REF=<tag|SHA> 固定到某个版本。
ARG LLAMA_CPP_REF=master

RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp \
    && if [ "${LLAMA_CPP_REF}" != "master" ]; then \
         git -C /opt/llama.cpp fetch --depth 1 origin "${LLAMA_CPP_REF}" \
         && git -C /opt/llama.cpp checkout "${LLAMA_CPP_REF}"; \
       fi

WORKDIR /opt/llama.cpp

# CPU-only 构建：量化本身是纯 CPU 任务，无需 CUDA/ROCm/Metal/Vulkan。
# 关键：BUILD_SHARED_LIBS=OFF 让 llama-quantize-impl / llama / ggml 全部静态链接，
# 产出自包含的单一可执行文件，避免运行时还要拷贝 libllama-quantize-impl.so 等一整串共享库。
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_SHARED_LIBS=OFF \
        -DGGML_CUDA=OFF \
        -DGGML_METAL=OFF \
        -DGGML_VULKAN=OFF \
        -DGGML_SYCL=OFF \
        -DGGML_HIP=OFF \
        -DLLAMA_CURL=OFF \
    && cmake --build build --config Release --target llama-quantize -j"$(nproc)" \
    && cp build/bin/llama-quantize /usr/local/bin/llama-quantize

# 构建产物自检：确认可执行文件已生成且可执行。
# 注意 llama-quantize 对 --help 返回非 0，故不能用 --help 判断，改用存在性/可执行校验。
RUN test -x /usr/local/bin/llama-quantize && test -s /usr/local/bin/llama-quantize


# ---------- 阶段 3：运行时 ----------
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    DATA_DIR=/data \
    WEB_DIST=/app/web \
    MAX_UPLOAD_MB=102400 \
    CLEANUP_HOURS=12 \
    PYTHONUNBUFFERED=1

# 镜像版本（如 20261103-abc1234），注入 /api/health
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# libgomp1：ggml CPU 后端默认启用 OpenMP(GGML_OPENMP=ON)，静态链接的量化二进制仍动态依赖 libgomp.so.1
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        ca-certificates \
        gosu \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=llama-build /usr/local/bin/llama-quantize /usr/local/bin/llama-quantize
COPY --from=frontend-build /web/dist /app/web

WORKDIR /app

COPY app/requirements.txt ./
# Ubuntu 24.04 系统 Python 为外部托管环境（PEP 668），需 --break-system-packages 才能 pip 安装
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY app/ ./

# 创建非 root 运行用户；镜像内 /data 先置好属主，并给 entrypoint 加可执行权限。
# 运行时挂载卷的属主由 docker-entrypoint.sh 再次校正（兼容已存在的旧卷）。
RUN mkdir -p /data/uploads /data/outputs \
    && useradd -m -u 10001 quantizer \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R quantizer:quantizer /app /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

# entrypoint 以 root 校正挂载卷属主后降权到 quantizer，故实际 uvicorn 进程仍为非 root
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
