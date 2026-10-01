import os
import socket
import subprocess
import sys
import threading
import time
import json
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
from aobana import paths

HOST, PORT = "127.0.0.1", paths.server_port()
URL = f"http://{HOST}:{PORT}/"


def server_up():
    try:
        with socket.create_connection((HOST, PORT), timeout=0.3):
            return True
    except OSError:
        return False


def is_aobana():
    try:
        with urllib.request.urlopen(f"{URL}api/library", timeout=3) as r:
            return "data_dir" in json.loads(r.read().decode("utf-8"))
    except Exception:
        return False


def port_taken_message():
    msg_ja = (f"ポート {PORT} は別のプログラムが使用しているため、Aobana を起動できません。\n\n"
              f"{paths.CONFIG_PATH}\nに  \"port\": 5050  （1024〜65535 の空いている番号）を"
              f"追加して、もう一度起動してください。起動後は設定タブでも変更できます。")
    msg_en = (f"Another program is already using port {PORT}, so Aobana cannot start.\n\n"
              f"Give Aobana another port: add  \"port\": 5050  (any free number from 1024 to "
              f"65535) to\n{paths.CONFIG_PATH}\nand start it again. Once it runs, the port can "
              f"also be changed in the Settings tab.")
    text = msg_ja + "\n\n" + msg_en
    print(text)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, "露草 / Aobana", 0x30)
        except Exception:
            pass


def page_waiting():
    try:
        with urllib.request.urlopen(f"{URL}api/update", timeout=3) as r:
            return bool(json.loads(r.read().decode("utf-8")).get("page_waiting"))
    except Exception:
        return False


def wait_and_open(proc=None, timeout=120.0, after_update=False):
    end = time.monotonic() + timeout
    while time.monotonic() < end and (proc is None or proc.poll() is None):
        if server_up():
            if after_update:
                wait_end = time.monotonic() + 8
                while time.monotonic() < wait_end:
                    if page_waiting():
                        return True
                    time.sleep(0.5)
            webbrowser.open(URL)
            return True
        time.sleep(0.1)
    return False


def console_python():
    exe = sys.executable
    if os.path.basename(exe).lower() == "pythonw.exe":
        candidate = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(candidate):
            return candidate
    return exe


def main():
    if "--open-only" in sys.argv[1:]:
        if server_up() and is_aobana():
            webbrowser.open(URL)
            return 0
        return 3
    if server_up():
        if not is_aobana():
            port_taken_message()
            return 1
        webbrowser.open(URL)
        return 0
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW("露草 / Aobana")
        except Exception:
            pass
    from aobana.server import updater
    after_update = updater.after_update() is not None
    os.chdir(HERE)
    with subprocess.Popen([console_python(), "-m", "aobana.server.app"]) as proc:
        threading.Thread(target=wait_and_open, kwargs={"proc": proc, "after_update": after_update},
                         daemon=True).start()
        try:
            return proc.wait()
        except BaseException:
            proc.kill()
            raise


if __name__ == "__main__":
    sys.exit(main())
