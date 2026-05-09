"""
NIST SP800-90B 熵评估 Web 控制台 — 启动入口
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8888, reload=True)
