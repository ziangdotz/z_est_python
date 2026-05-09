"""
页面路由定义 — FastAPI APIRouter 页面级路由。
"""
import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


def _load_template(name: str) -> str:
    path = os.path.normpath(os.path.join(_TEMPLATES_DIR, name))
    with open(path, encoding="utf-8") as f:
        return f.read()


@router.get("/", response_class=HTMLResponse)
@router.get("/index.html", response_class=HTMLResponse)
async def index():
    return _load_template("index.html")
