@echo off
rem 一键启动本地开发环境：后端 8000 + 前端 5173（各自独立窗口，日志在仓库根目录）
cd /d %~dp0
start "uvicorn-dev" cmd /c "python -m uvicorn main:app --port 8000 > uvicorn-dev.log 2>&1"
start "vite-dev" cmd /c "cd frontend && npm run dev > ..\vite-dev.log 2>&1"
timeout /t 6 /nobreak > NUL
curl -s http://127.0.0.1:8000/health | findstr /c:"ok" > NUL && echo [OK] 后端 http://127.0.0.1:8000 || echo [FAIL] 后端未就绪，看 uvicorn-dev.log
curl -s -o NUL -w "" http://127.0.0.1:5173/ && echo [OK] 前端 http://127.0.0.1:5173 || echo [FAIL] 前端未就绪，看 vite-dev.log
echo 浏览器打开 http://127.0.0.1:5173/teacher/board/tx886 （中介演示账号 tx886 / dev123456）
pause
