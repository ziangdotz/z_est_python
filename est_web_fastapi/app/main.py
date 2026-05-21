"""
应用核心 — FastAPI 应用实例定义与路由挂载。
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.pages import router as pages_router
from app.routes.est_api import router as est_api_router
from app.routes.est_nist_cpp_recode_api import router as est_nist_cpp_recode_router

app = FastAPI(title="NIST SP800-90B 熵评估 Web 控制台")

app.include_router(pages_router)
app.include_router(est_api_router)
app.include_router(est_nist_cpp_recode_router)

app.mount("/static", StaticFiles(directory="static"), name="static")
