#!/bin/sh
# GGUF Quantizer 容器入口脚本
#
# 作用：运行时挂载到 /data 的命名卷可能是 root 所有（或由旧版本镜像创建），
# 非 root 的 quantizer 用户无法写入。这里以 root 启动后先校正 /data 属主，
# 再通过 gosu 降权到 quantizer 运行真正的服务，保证 uvicorn 进程仍是非 root。
set -e

if [ "$(id -u)" = "0" ]; then
    # 确保数据目录存在并归属于 quantizer（对已存在的旧卷同样生效）
    mkdir -p /data/uploads /data/outputs
    chown -R quantizer:quantizer /data
    # 降权执行 CMD（gosu 会直接 exec，信号可正常传递）
    exec gosu quantizer "$@"
fi

# 若以非 root 方式启动（如 docker run --user 指定），直接执行
exec "$@"
