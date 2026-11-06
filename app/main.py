from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from quantizer import (
    DEFAULT_QUANT_TYPE,
    QUANT_GROUPS,
    QUANT_TYPES,
    Job,
    JobManager,
    QuantizeError,
    generate_output_filename,
    sanitize_output_name,
)

# ---------------------------------------------------------------------------
# 配置（均可通过环境变量覆盖）
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
QUANT_BINARY = os.environ.get("QUANT_BINARY", "llama-quantize")
# 单个上传文件上限：默认 100 GiB（102400 MB）；设为 0 表示不限制，仅受磁盘空间约束
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "102400")) * 1024 * 1024
CLEANUP_HOURS = float(os.environ.get("CLEANUP_HOURS", "12"))
APP_VERSION = os.environ.get("APP_VERSION", "dev")


def _resolve_web_dist() -> Path:
    """定位前端构建产物目录（Vue/Vite 构建输出）。"""
    env = os.environ.get("WEB_DIST")
    if env:
        return Path(env)
    pkg = Path(__file__).parent.parent / "frontend" / "dist"
    if pkg.is_dir():
        return pkg
    return Path(__file__).parent / "static"


WEB_DIST = _resolve_web_dist()
WEB_DIST.mkdir(parents=True, exist_ok=True)
(WEB_DIST / "assets").mkdir(parents=True, exist_ok=True)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="GGUF Quantizer",
    description="上传 FP16 GGUF → 选择量化参数 → 下载量化结果",
    version="1.0.0",
)

manager = JobManager(UPLOAD_DIR, OUTPUT_DIR, binary=QUANT_BINARY)

# 前端静态资源（Vue/Vite 构建产物）
app.mount("/assets", StaticFiles(directory=str(WEB_DIST / "assets")), name="assets")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _require_quant_type(quant_type: str) -> str:
    if quant_type not in QUANT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的量化类型: {quant_type!r}。可选: {', '.join(QUANT_TYPES)}",
        )
    return quant_type


def _validate_gguf(path: Path) -> None:
    """校验文件为合法 GGUF（魔数 GGUF）。"""
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"无法读取上传文件: {exc}")
    if magic != b"GGUF":
        raise HTTPException(
            status_code=400,
            detail="文件不是 GGUF 格式（魔数错误）。请上传 llama.cpp 导出的 FP16 GGUF 文件。",
        )


def _get_job_or_404(job_id: str) -> Job:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="作业不存在")
    return job


def _cleanup_expired() -> None:
    """清理超时的上传文件（未进入量化的），释放空间。"""
    now = time.time()
    for f in UPLOAD_DIR.glob("*.gguf"):
        try:
            if now - f.stat().st_mtime > CLEANUP_HOURS * 3600:
                f.unlink()
        except OSError:
            pass
    # 保留的量化结果也做同样清理（若开启了自动清理）
    if os.environ.get("AUTO_CLEAN_OUTPUTS", "1") == "1":
        for f in OUTPUT_DIR.glob("*.gguf"):
            try:
                if now - f.stat().st_mtime > CLEANUP_HOURS * 3600:
                    f.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    _cleanup_expired()
    return {
        "status": "ok",
        "version": APP_VERSION,
        "quant_binary": QUANT_BINARY,
        "disk_free_gib": round(shutil.disk_usage(OUTPUT_DIR).free / (1 << 30), 2),
        "active_jobs": sum(
            1 for j in manager.all() if j.state in ("queued", "running")
        ),
    }


@app.get("/api/quant-types")
def list_quant_types() -> dict:
    return {
        "groups": QUANT_GROUPS,
        "types": QUANT_TYPES,
        "default": DEFAULT_QUANT_TYPE,
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".gguf"):
        raise HTTPException(status_code=400, detail="仅接受 .gguf 文件")

    upload_id = uuid.uuid4().hex
    dest = UPLOAD_DIR / f"{upload_id}.gguf"

    written = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if MAX_UPLOAD_BYTES and written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过大小限制 {MAX_UPLOAD_BYTES // (1 << 20)} MB",
                    )
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except OSError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"保存上传文件失败: {exc}")

    try:
        _validate_gguf(dest)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise

    return JSONResponse(
        content={
            "upload_id": upload_id,
            "filename": file.filename,
            "size": written,
            "size_gib": round(written / (1 << 30), 3),
        }
    )


class QuantizeRequest(BaseModel):
    upload_id: str
    quant_type: str = DEFAULT_QUANT_TYPE
    output_name: str | None = None
    source_name: str | None = None


@app.post("/api/quantize")
def quantize(req: QuantizeRequest) -> JSONResponse:
    quant_type = _require_quant_type(req.quant_type)
    src = UPLOAD_DIR / f"{req.upload_id}.gguf"
    if not src.exists():
        raise HTTPException(
            status_code=404, detail="上传文件不存在或已过期，请重新上传"
        )

    stem = src.stem.replace("upload-", "")
    output_name = sanitize_output_name(
        req.output_name or generate_output_filename(stem, quant_type),
        generate_output_filename(stem, quant_type),
    )

    job = Job(
        job_id=uuid.uuid4().hex,
        upload_path=src,
        source_name=req.source_name or src.name,
        source_size=src.stat().st_size,
        quant_type=quant_type,
        output_filename=output_name,
        output_path=OUTPUT_DIR / f"{uuid.uuid4().hex}.gguf",
    )
    manager.start(job)
    return JSONResponse(content={"job_id": job.id, "status": job.state})


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, offset: int = 0) -> JSONResponse:
    job = _get_job_or_404(job_id)
    new_log, total = job.snapshot_log(offset)
    return JSONResponse(
        content={
            "id": job.id,
            "state": job.state,
            "progress": job.progress,
            "error": job.error,
            "output_name": job.output_filename,
            "source_name": job.source_name,
            "quant_type": job.quant_type,
            "log": new_log,
            "log_total": total,
            "finished_at": job.finished_at,
        }
    )


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> JSONResponse:
    job = _get_job_or_404(job_id)
    if job.state in ("queued", "running"):
        job.request_cancel()
        if job.state == "queued":
            job.set_state("cancelled")
        return JSONResponse(content={"id": job.id, "status": "cancelling"})
    return JSONResponse(content={"id": job.id, "status": job.state})


@app.post("/api/jobs/{job_id}/delete")
def delete_job_files(job_id: str) -> JSONResponse:
    job = _get_job_or_404(job_id)
    if job.state in ("queued", "running"):
        raise HTTPException(status_code=409, detail="作业进行中，请先取消再清理")

    # 删除量化结果与可能残留的源上传文件，累计释放空间
    freed = 0
    for p in (job.output_path, job.upload_path):
        try:
            if p.exists():
                freed += p.stat().st_size
                p.unlink()
        except OSError:
            pass

    manager.remove(job_id)
    return JSONResponse(
        content={"deleted": True, "freed_gib": round(freed / (1 << 30), 3)}
    )


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str) -> FileResponse:
    job = _get_job_or_404(job_id)
    if job.state != "done" or not job.output_path.exists():
        raise HTTPException(status_code=404, detail="量化结果不可用（作业未完成或文件已清理）")
    return FileResponse(
        job.output_path,
        filename=job.output_filename,
        media_type="application/octet-stream",
    )


@app.post("/api/uploads/{upload_id}/delete")
def delete_upload(upload_id: str) -> JSONResponse:
    src = UPLOAD_DIR / f"{upload_id}.gguf"
    if src.exists():
        src.unlink(missing_ok=True)
    return JSONResponse(content={"deleted": True})


# 前端单页
@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(WEB_DIST / "index.html"))
