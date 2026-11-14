"""Desktop launcher: starts the local server and opens its browser page."""
import ctypes
import json
import msvcrt
import subprocess
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / '.venv' / 'Scripts' / 'python.exe'
URL = 'http://127.0.0.1:8000'

def ready():
    try:
        with urllib.request.urlopen(URL + '/api/health', timeout=1) as response:
            return json.load(response).get('status') == 'ok'
    except Exception:
        return False

def main():
    (ROOT / 'data').mkdir(exist_ok=True)
    with open(ROOT / 'data' / 'launcher.lock', 'a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return  # Another shortcut invocation is starting the server.
        try:
            if not ready():
                if not PYTHON.exists():
                    raise RuntimeError('Не найдено окружение .venv. См. инструкцию README.md.')
                with open(ROOT / 'data' / 'server.log', 'ab', buffering=0) as log:
                    migration = subprocess.run([str(PYTHON), '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
                    if migration.returncode:
                        raise RuntimeError('Ошибка подготовки базы. Подробности: data/server.log')
                    process = subprocess.Popen([str(PYTHON), '-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', '8000'], cwd=ROOT, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
                for _ in range(60):
                    if ready():
                        break
                    if process.poll() is not None:
                        raise RuntimeError('Сервер не запустился. Подробности: data/server.log')
                    time.sleep(.5)
                else:
                    raise RuntimeError('Сервер не ответил вовремя. Подробности: data/server.log')
            webbrowser.open(URL)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(None, str(error), 'Destination Tickets — запуск', 0x10)
