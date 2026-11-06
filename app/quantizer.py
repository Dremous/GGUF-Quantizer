"""
GGUF Quantizer - 后台量化作业管理器

职责：
  - 在独立线程中调用 llama-quantize，将 FP16 GGUF 量化为目标类型
  - 维护作业状态机 (queued -> running -> done | error | cancelled)
  - 实时累积日志，供前端轮询展示
  - 负责磁盘空间预检、结果清理

本模块仅依赖 Python 标准库，方便在无 Web 框架环境下单独测试。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

logger = logging.getLogger("quantizer")

# ---------------------------------------------------------------------------
# 量化类型定义
# ---------------------------------------------------------------------------
# name: (说明, 分组, 是否推荐)
# 分组: classic / k-quant / iq / other
QUANT_TYPES: dict[str, tuple[str, str, bool]] = {
    # ---- 经典量化 ----
    "q4_0": ("4-bit 经典量化，体积最小，质量较低", "classic", False),
    "q4_1": ("4-bit 经典量化，比 q4_0 略大、略准", "classic", False),
    "q5_0": ("5-bit 经典量化，质量/体积较均衡", "classic", False),
    "q5_1": ("5-bit 经典量化，比 q5_0 略大、略准", "classic", False),
    "q8_0": ("8-bit 经典量化，质量高，体积约为一半", "classic", False),
    # ---- K-quant ----
    "q2_K": ("2-bit K-quant，体积最小，质量较低", "k-quant", False),
    "q3_K_S": ("3-bit K-quant（小型）", "k-quant", False),
    "q3_K_M": ("3-bit K-quant（中等）", "k-quant", False),
    "q3_K_L": ("3-bit K-quant（大型，更准）", "k-quant", False),
    "q4_K_S": ("4-bit K-quant（小型）", "k-quant", False),
    "q4_K_M": ("4-bit K-quant（中等）★ 通用推荐", "k-quant", True),
    "q5_K_S": ("5-bit K-quant（小型）", "k-quant", False),
    "q5_K_M": ("5-bit K-quant（中等）", "k-quant", False),
    "q6_K": ("6-bit K-quant，质量较高", "k-quant", False),
    "q8_K": ("8-bit K-quant，质量很高", "k-quant", False),
    # ---- IQ 混合量化（体积更小，要求新内核）----
    "iq4_xs": ("4-bit IQ 混合量化，体积更小", "iq", False),
    "iq4_nl": ("4-bit IQ 混合量化（非分层）", "iq", False),
    # ---- 其它 ----
    "f16": ("保持 FP16（用于再转换/测试）", "other", False),
    "f32": ("转为 FP32，体积最大", "other", False),
}

# 该组别的排序标签（前端也按此分组展示）
QUANT_GROUPS: dict[str, str] = {
    "classic": "经典量化 (4/5/8-bit)",
    "k-quant": "K-quant (K 系，推荐)",
    "iq": "IQ 混合量化（体积优先）",
    "other": "其它",
}

DEFAULT_QUANT_TYPE = "q4_K_M"


class JobState:
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class QuantizeError(Exception):
    """业务层可预期错误，message 可直接展示给用户。"""


# 磁盘空间余量校验：目标文件体积约占源文件的估算比例
_SPACE_FACTOR = {
    "q4_0": 0.30, "q4_1": 0.32, "q5_0": 0.37, "q5_1": 0.39, "q8_0": 0.55,
    "q2_K": 0.25, "q3_K_S": 0.29, "q3_K_M": 0.31, "q3_K_L": 0.33,
    "q4_K_S": 0.33, "q4_K_M": 0.36, "q5_K_S": 0.41, "q5_K_M": 0.44,
    "q6_K": 0.49, "q8_K": 0.58, "iq4_xs": 0.32, "iq4_nl": 0.32,
    "f16": 1.0, "f32": 2.0,
}


def _space_factor(quant_type: str) -> float:
    return _SPACE_FACTOR.get(quant_type, 0.5)


def free_bytes(path: Path) -> int:
    """返回 path 所在文件系统的可用字节数。"""
    return shutil.disk_usage(path).free


class Job:
    """单个量化作业（内存态）。"""

    __slots__ = (
        "id", "upload_path", "source_name", "source_size", "quant_type",
        "output_filename", "output_path", "state", "progress", "log",
        "error", "created_at", "finished_at", "_proc", "_lock",
    )

    def __init__(self, job_id: str, upload_path: Path, source_name: str,
                 source_size: int, quant_type: str, output_filename: str,
                 output_path: Path):
        self.id = job_id
        self.upload_path = upload_path
        self.source_name = source_name
        self.source_size = source_size
        self.quant_type = quant_type
        self.output_filename = output_filename
        self.output_path = output_path
        self.state = JobState.QUEUED
        self.progress = 0          # 0-100，尽力估算；无百分比时用于显示“处理中”
        self.log: list[str] = []
        self.error: str | None = None
        self.created_at = time.time()
        self.finished_at = float | None = None
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    # -- 线程安全的日志访问 --
    def append_log(self, line: str) -> None:
        with self._lock:
            self.log.append(line)
            if len(self.log) > 2000:      # 限制日志上限，防止内存无限增长
                del self.log[:-2000]

    def snapshot_log(self, offset: int = 0) -> tuple[list[str], int]:
        with self._lock:
            tail = list(self.log[offset:])
            return tail, len(self.log)

    def set_state(self, state: str, progress: int | None = None,
                  error: str | None = None) -> None:
        with self._lock:
            self.state = state
            if progress is not None:
                self.progress = progress
            if error is not None:
                self.error = error
            if state in (JobState.DONE, JobState.ERROR, JobState.CANCELLED):
                self.finished_at = time.time()
                self.progress = 100 if state == JobState.DONE else self.progress

    def request_cancel(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass


class JobManager:
    """作业注册表 + 并发上限控制。"""

    def __init__(self, upload_dir: Path, output_dir: Path,
                 binary: str = "llama-quantize", max_concurrent: int = 1):
        self.upload_dir = upload_dir
        self.output_dir = output_dir
        self.binary = binary
        self.max_concurrent = max_concurrent
        self._jobs: dict[str, Job] = {}
        self._sem = threading.Semaphore(max_concurrent)
        self._lock = threading.Lock()

    def register(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def remove(self, job_id: str) -> None:
        """从注册表移除作业（文件已由调用方删除）。"""
        with self._lock:
            self._jobs.pop(job_id, None)

    def start(self, job: Job) -> None:
        """启动作业：立即排队，交给线程池执行。"""
        self.register(job)
        threading.Thread(
            target=self._run_wrapper, args=(job,), daemon=True, name=f"quant-{job.id}"
        ).start()

    def _run_wrapper(self, job: Job) -> None:
        with self._sem:
            if job.state == JobState.CANCELLED:
                return
            try:
                self._check_space(job)
                job.set_state(JobState.RUNNING, progress=0)
                self._run_quantize(job)
            except (QuantizeError, OSError) as exc:
                job.set_state(JobState.ERROR, error=str(exc))
                job.append_log(f"[error] {exc}")
                logger.exception("quantization failed for job %s", job.id)
            except Exception as exc:  # noqa: BLE001 - 兜底，避免线程静默死亡
                job.set_state(JobState.ERROR, error=f"内部错误: {exc}")
                job.append_log(f"[error] 内部错误: {exc}")
                logger.exception("unexpected failure for job %s", job.id)
            finally:
                self._cleanup_after_job(job)

    def _check_space(self, job: Job) -> None:
        need = int(job.source_size * _space_factor(job.quant_type)) + (256 << 20)
        free = free_bytes(self.output_dir)
        if free < need:
            raise QuantizeError(
                f"磁盘空间不足：量化后预计需要约 {need / (1 << 30):.2f} GiB，"
                f"当前可用 {free / (1 << 30):.2f} GiB。请清理磁盘或调低量化位宽。"
            )

    def _run_quantize(self, job: Job) -> None:
        job.append_log(f"$ llama-quantize --allow-requantize "
                       f"'{job.upload_path.name}' '{job.output_filename}' {job.quant_type}")
        job.append_log(f"源文件: {job.source_name} ({job.source_size / (1 << 30):.2f} GiB)")

        cmd = [
            self.binary,
            "--allow-requantize",
            str(job.upload_path),
            str(job.output_path),
            job.quant_type,
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
        job._proc = proc

        tensor_re = re.compile(r"quantizing\s+(\S+)\s+to\s+(\S+)", re.IGNORECASE)
        # llama-quantize 输出里可能带有进度百分比（不同版本格式不一），兼容匹配
        pct_re = re.compile(r"(\d{1,3})\s*%")

        for line in proc.stdout:
            line = line.rstrip("\n")
            job.append_log(line)

            m = tensor_re.search(line)
            if m:
                job.append_log(f"   → {m.group(1)} → {m.group(2)}")

            m2 = pct_re.search(line)
            if m2:
                try:
                    job.progress = max(0, min(100, int(m2.group(1))))
                except ValueError:
                    pass

        ret = proc.wait()
        job._proc = None

        if job.state == JobState.CANCELLED:
            job.append_log("作业已被取消。")
            return

        if ret != 0:
            # 已量化的文件若残缺则删除，避免下载到坏文件
            if job.output_path.exists():
                try:
                    job.output_path.unlink()
                except OSError:
                    pass
            raise QuantizeError(f"量化进程退出码 {ret}，请查看上方日志。")

        if not job.output_path.exists():
            raise QuantizeError("量化完成但未找到输出文件。")

        job.set_state(JobState.DONE, progress=100)
        size = job.output_path.stat().st_size
        job.append_log(f"完成：{job.output_filename} ({size / (1 << 30):.2f} GiB)")

    def _cleanup_after_job(self, job: Job) -> None:
        """作业结束后删除源上传文件，仅保留量化结果。"""
        try:
            if job.upload_path.exists():
                job.upload_path.unlink()
        except OSError:
            logger.warning("failed to remove upload %s", job.upload_path)


def sanitize_output_name(name: str, default_stem: str) -> str:
    """清洗用户提供的输出文件名：仅保留安全字符，强制 .gguf 后缀。"""
    name = name.strip()
    # 去掉路径分隔符与危险字符
    safe = re.sub(r"[^\w.\-]", "_", name)
    safe = safe.strip("._")
    if not safe:
        safe = default_stem
    if not safe.lower().endswith(".gguf"):
        safe += ".gguf"
    return safe


def generate_output_filename(stem: str, quant_type: str) -> str:
    """按源文件名与量化类型生成默认输出名，例如 model-q4_K_M.gguf。"""
    return f"{stem}-{quant_type}.gguf"
