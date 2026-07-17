@echo off
cd /d "C:\Desarrollos BI\dashboardcontrol"

call .venv\Scripts\activate

start "Dashboard Control (Scheduler)" cmd /k .venv\Scripts\python.exe -m src.scheduler
timeout /t 2 /nobreak > nul
start "Dashboard Control (FastAPI)" cmd /k .venv\Scripts\python.exe -m uvicorn frontend.server:app --host 0.0.0.0 --port 8501