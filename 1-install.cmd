@echo off
cd /d "%~dp0"
python -m venv .venv || goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto failed
.venv\Scripts\python.exe -m alembic upgrade head || goto failed
echo Installation complete. Run 2-start.cmd
pause
exit /b 0
:failed
echo Installation failed. See error above.
pause
exit /b 1
