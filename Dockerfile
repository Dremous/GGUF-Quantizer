# ============================================================================
# GGUF Quantizer — 三阶段构建
#   阶段 1 (frontend-build): Vue/Vite 前端构建（Tailwind）
#   阶段 2 (llama-fetch)   : 下载 llama.cpp 官方预编译 llama-quantize（CPU）
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


# ---------- 阶段 2：下载官方预编译量化工具 ----------
FROM ubuntu:24.04 AS llama-fetch

ENV DEBIAN_FRONTEND=noninteractive
# ca-certificates/curl 用于下载；git 仅在需要自动解析最新 bXXXX 标签时使用（git ls-remote）
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# 目标发布版本：留空则构建时自动解析最新 bXXXX；也可传入具体标签（如 b12171）固定版本。
# TARGETARCH 由 BuildKit 自动注入（amd64 / arm64），映射到官方对应的预编译包。
ARG TARGETARCH
ARG LLAMA_CPP_RELEASE=
# 指定版本优先尝试；同时始终解析最近 10 个 b 标签作为回退候选（去重），
# 即使指定标签“release 已发布但资产 CDN 尚未就绪”（短暂 404），也能自动回退到上一个可用版本。
RUN set -eux; \
    case "${TARGETARCH}" in \
        amd64) LLAMA_PKG="ubuntu-x64" ;; \
        arm64) LLAMA_PKG="ubuntu-arm64" ;; \
        *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    if [ -n "${LLAMA_CPP_RELEASE}" ]; then PINNED="${LLAMA_CPP_RELEASE}"; else PINNED=""; fi; \
    AUTO_TAGS=$(git ls-remote --tags https://github.com/ggml-org/llama.cpp 'refs/tags/b*' \
        | awk '{print $2}' \
        | sed -e 's#refs/tags/##' -e 's#\^{}##' \
        | grep -E '^b[0-9]+$' \
        | sort -V -r | head -10); \
    CANDIDATES=$( { printf '%s\n' "${PINNED}"; printf '%s\n' ${AUTO_TAGS}; } \
        | grep -E '^b[0-9]+$' | awk '!seen[$0]++'); \
    FOUND=""; \
    for TAG in ${CANDIDATES}; do \
        LLAMA_FILE="llama-${TAG}-bin-${LLAMA_PKG}.tar.gz"; \
        LLAMA_URL="https://github.com/ggml-org/llama.cpp/releases/download/${TAG}/${LLAMA_FILE}"; \
        echo "trying ${LLAMA_URL}"; \
        if curl -fsSL --retry 2 "${LLAMA_URL}" -o /tmp/llama.tar.gz; then \
            FOUND="${TAG}"; break; \
        fi; \
        echo "asset not ready for ${TAG}, trying previous..."; \
    done; \
    test -n "${FOUND}"; \
    echo "using llama.cpp release: ${FOUND}"; \
    mkdir -p /opt/llama; \
    tar -xzf /tmp/llama.tar.gz -C /opt/llama --strip-components=1; \
    rm -f /tmp/llama.tar.gz; \
    echo "${FOUND}" > /opt/llama/RELEASE; \
    test -x /opt/llama/llama-quantize


# ---------- 阶段 3：运行时 ----------
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    DATA_DIR=/data \
    WEB_DIST=/app/web \
    QUANT_BINARY=/opt/llama/llama-quantize \
    MAX_UPLOAD_MB=102400 \
    CLEANUP_HOURS=12 \
    PYTHONUNBUFFERED=1

# 镜像版本（如 20261103-abc1234），注入 /api/health
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# libgomp1：官方预编译的 ggml CPU 后端启用 OpenMP，运行时仍动态依赖 libgomp.so.1
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        ca-certificates \
        gosu \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 官方预编译为动态链接（RUNPATH=$ORIGIN），整包放在同一目录，二进制即可自动找到配套 .so
COPY --from=llama-fetch /opt/llama /opt/llama
COPY --from=frontend-build /web/dist /app/web

# 确保非 root 用户可读、可执行（大写 X 仅对目录与已有可执行文件赋执行权限）
RUN chmod -R a+rX /opt/llama

WORKDIR /app

COPY app/requirements.txt ./
# Ubuntu 24.04 系统 Python 为外部托管环境（PEP 668），需 --break-system-packages 才能 pip 安装
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY app/ ./

# 构建期语法闸门：任一后端文件存在语法错误立即让构建失败，避免坏镜像拖到运行时才崩溃
RUN python3 -m py_compile /app/*.py && rm -rf /app/__pycache__

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
