"""本地冒烟测试：用假 llama-quantize 二进制验证后端全流程。

用法（在项目根目录）：
    .venv/bin/python tests/smoke_test.py
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ["DATA_DIR"] = str(ROOT / "data-test")

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

# ---------- 准备假 llama-quantize 二进制 ----------
FAKE_BIN = ROOT / "data-test" / "fake-llama-quantize"
FAKE_BIN.parent.mkdir(parents=True, exist_ok=True)
FAKE_BIN.write_text(
    '#!/usr/bin/env python3\n'
    'import sys, shutil, time\n'
    'args = [a for a in sys.argv[1:] if a != "--allow-requantize"]\n'
    'if "--help" in args:\n'
    '    print("llama-quantize help"); sys.exit(0)\n'
    'src, dst, qtype = args[0], args[1], args[2]\n'
    'print("main: model size = 1.00 GiB")\n'
    'print("quantizing  layer.0.attn.weight to Q4_K_M ...")\n'
    'print("quantizing  layer.1.attn.weight to Q4_K_M ...")\n'
    'print("quantizing  output.weight        to Q4_K_M ...")\n'
    'time.sleep(0.1)\n'
    'import os; os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)\n'
    'shutil.copyfile(src, dst)\n'
    'print("main: quant size  = 0.25 GiB")\n'
    'print("llama_quantize_internal: model size = 1.00 GiB -> 0.25 GiB")\n'
    'sys.exit(0)\n',
    encoding="utf-8",
)
FAKE_BIN.chmod(0o755)

os.environ["QUANT_BINARY"] = str(FAKE_BIN)
# 重新导入以获得新配置
import importlib
import main as main_mod
importlib.reload(main_mod)
app = main_mod.app
main_mod.manager = main_mod.JobManager(main_mod.UPLOAD_DIR, main_mod.OUTPUT_DIR, binary=str(FAKE_BIN))


def make_gguf(size: int = 1024) -> bytes:
    return b"GGUF" + b"\x00" * (size - 4)


client = TestClient(app)
failures = []


def check(name, cond):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}")
    if not cond:
        failures.append(name)


# 1. health
r = client.get("/api/health")
check("health", r.status_code == 200 and r.json()["status"] == "ok")

# 2. quant types
r = client.get("/api/quant-types")
qt = r.json()
check("quant-types has q4_K_M", "q4_K_M" in qt["types"] and qt["default"] == "q4_K_M")
check("quant-types groups", set(qt["groups"]) == {"classic", "k-quant", "iq", "other"})

# 3. upload 非法文件
r = client.post("/api/upload", files={"file": ("bad.bin", b"\x00\x01\x02", "application/octet-stream")})
check("reject non-GGUF", r.status_code == 400)

# 4. upload 合法 GGUF
r = client.post("/api/upload", files={"file": ("model-f16.gguf", make_gguf(), "application/octet-stream")})
check("upload ok", r.status_code == 200)
up = r.json()
check("upload returns id", "upload_id" in up)

# 5. 非法量化类型
r = client.post("/api/quantize", json={"upload_id": up["upload_id"], "quant_type": "not-a-type"})
check("reject bad quant type", r.status_code == 400)

# 6. 发起量化
r = client.post("/api/quantize", json={
    "upload_id": up["upload_id"], "quant_type": "q4_K_M",
    "output_name": "../evil/out", "source_name": "model-f16.gguf",
})
check("quantize ok", r.status_code == 200)
job_id = r.json()["job_id"]

# 7. 轮询直到完成
state, output_name = None, None
for _ in range(30):
    r = client.get(f"/api/jobs/{job_id}")
    j = r.json()
    state = j["state"]
    if state in ("done", "error", "cancelled"):
        output_name = j["output_name"]
        break
    time.sleep(0.2)
check("job finished done", state == "done")
check("output name sanitized (no path traversal)",
      output_name == "evil_out.gguf" and "/" not in output_name and ".." not in output_name)
check("job log captured", len(client.get(f"/api/jobs/{job_id}").json()["log"]) > 0)

# 8. 下载
r = client.get(f"/api/jobs/{job_id}/download")
check("download ok", r.status_code == 200 and r.headers.get("content-disposition", "").endswith("out.gguf\""))

# 9. 上传文件已清理
check("upload cleaned after job", not (main_mod.UPLOAD_DIR / f"{up['upload_id']}.gguf").exists())

print("\n==== RESULT:", "ALL PASS" if not failures else f"FAILURES: {failures}", "====")
sys.exit(1 if failures else 0)
