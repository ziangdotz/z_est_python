"""
【模块名称】: est_nist_cpp_recode_api.py
【模块功能】: NIST C++ Recode 熵评估 API 路由 — 接收前端请求，调用 est_core_nist_cpp_recode 核心算法，返回 JSON 结果。
"""
import os
import sys

# 将 est_core_nist_cpp_recode 加入导包路径（必须在 ea 导入之前执行）
_recode_dir = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'est_core_nist_cpp_recode'))
if _recode_dir not in sys.path:
    sys.path.insert(0, _recode_dir)

import base64
import io
import tempfile
from contextlib import redirect_stdout

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ea.restart import restart_test
from ea.non_iid_pipeline import run_non_iid_test
from ea.iid_pipeline import run_iid_test

router = APIRouter()


class NistEstRequest(BaseModel):
    datafile: str
    bits_per_symbol: int = 0
    mode: str
    verbose: int = 1
    h_i: float | None = None
    initial: bool = True
    all_bits: bool = True
    run_iid_validation: bool = False


@router.post("/api/v1/entropy/est_nist_cpp_recode")
def run_nist_entropy_est(req: NistEstRequest):
    if req.mode not in ("restart", "iid", "noniid"):
        raise HTTPException(
            status_code=400, detail="mode 必须为 restart / iid / noniid 之一")
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
                result = restart_test(
                    file_path=tmp_path,
                    H_I=req.h_i,
                    iid=req.run_iid_validation,
                    verbose=req.verbose,
                )
                return {
                    "code": 200,
                    "data": {
                        "Restart_Test": {"h_min": result, "H_I": req.h_i},
                        "stdout": stdout_capture.getvalue(),
                    }
                }
            elif req.mode == "iid":
                result = run_iid_test(
                    file_path=tmp_path,
                    bits_per_symbol=req.bits_per_symbol,
                    initial=req.initial,
                    all_bits=req.all_bits,
                    verbose=req.verbose,
                )
                return {
                    "code": 200,
                    "data": {
                        "IID_Test": result.to_dict(),
                        "stdout": stdout_capture.getvalue(),
                    }
                }
            else:
                result = run_non_iid_test(
                    file_path=tmp_path,
                    bits_per_symbol=req.bits_per_symbol,
                    verbose=req.verbose,
                )
                return {
                    "code": 200,
                    "data": {
                        "Non_IID_Test": result.to_dict(),
                        "stdout": stdout_capture.getvalue(),
                    }
                }

    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=f"NIST 熵评估执行失败: {e}")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"NIST 熵评估执行异常: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
