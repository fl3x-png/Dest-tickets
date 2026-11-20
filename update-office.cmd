@echo off
setlocal
cd /d "%~dp0"
if not exist .git goto missing
if not exist data\destination.db goto missing
if not exist .env goto missing
echo Stop the ticket server before updating. Keep this window open.
python -c "import socket,sys; s=socket.socket(); sys.exit(1 if s.connect_ex(('127.0.0.1',8000))==0 else 0)" || goto failed
python -c "import sqlite3,datetime,pathlib; p=pathlib.Path('backups'); p.mkdir(exist_ok=True); dst=sqlite3.connect(p/('before-update-'+datetime.datetime.now().strftime('%%Y%%m%%d-%%H%%M%%S-%%f')+'.db')); src=sqlite3.connect('file:data/destination.db?mode=ro',uri=True); src.backup(dst); assert dst.execute('PRAGMA integrity_check').fetchone()==('ok',); dst.close(); src.close()" || goto failed
git pull --ff-only origin main || goto failed
if not exist .venv\Scripts\python.exe python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto failed
.venv\Scripts\python.exe -m alembic upgrade head || goto failed
echo Update installed. Starting Destination Tickets.
.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
exit /b %errorlevel%
:missing
echo Use a Git clone with the office database and .env first.
:failed
echo Update stopped. See the message above. If port 8000 is in use, stop the server first.
pause
exit /b 1
