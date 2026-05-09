"""
【模块名称】: est_api.py
【模块功能】: 熵评估 API 路由 — 接收前端请求，调用 est_core 核心算法，返回 JSON 结果。
"""
import base64
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 将 est_core 加入导包路径
_est_core_dir = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'est_core'))
if _est_core_dir not in sys.path:
    sys.path.insert(0, _est_core_dir)

from main_restart import main_restart
from main_iid import main_iid
from main_noniid import main_noniid

router = APIRouter()


class EstRequest(BaseModel):
    datafile: str
    bits_per_symbol: int = 8
    mode: str
    verbose: bool = False
    h_i: float | None = None
    use_bits: int | None = None


@router.post("/api/v1/entropy/est")
def run_entropy_est(req: EstRequest):
    if req.mode not in ("restart", "iid", "noniid"):
        raise HTTPException(status_code=400, detail="mode 必须为 restart / iid / noniid 之一")
    if not (1 <= req.bits_per_symbol <= 8):
        raise HTTPException(status_code=400, detail="bits_per_symbol 必须在 1~8 之间")
    if req.mode == "restart" and req.h_i is None:
        raise HTTPException(status_code=400, detail="Restart 模式下 h_i 为必填参数")

    try:
        raw = base64.b64decode(req.datafile)
    except Exception:
        raise HTTPException(status_code=400, detail="Base64 数据解码失败")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        stdout_capture = io.StringIO()

        with redirect_stdout(stdout_capture):
            if req.mode == "restart":
                result = main_restart(
                    tmp_path, req.bits_per_symbol, req.h_i, req.verbose)
                return {
                    "code": 200,
                    "data": {
                        "Restart_Test": result,
                        "stdout": stdout_capture.getvalue(),
                    }
                }
            elif req.mode == "iid":
                result = main_iid(
                    tmp_path, req.bits_per_symbol, req.verbose)
                return {
                    "code": 200,
                    "data": {
                        "IID_Test": result,
                        "stdout": stdout_capture.getvalue(),
                    }
                }
            else:
                result = main_noniid(
                    tmp_path, req.bits_per_symbol, req.use_bits, req.verbose)
                return {
                    "code": 200,
                    "data": {
                        "Non_IID_Test": result,
                        "stdout": stdout_capture.getvalue(),
                    }
                }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"熵评估执行异常: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
