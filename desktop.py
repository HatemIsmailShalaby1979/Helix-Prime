#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import time
import webview

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(ROOT, ".helix_server.log")

def start_server(port):
    log = open(LOG_FILE, "w", buffering=1)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.app:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port)],
        stdout=log, stderr=log, cwd=ROOT,
    )
    for _ in range(30):
        time.sleep(0.1)
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
            return proc
        except Exception:
            pass
    raise RuntimeError(f"Server did not start on port {port}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-server", action="store_true")
    args = parser.parse_args()

    server_proc = None
    if not args.no_server:
        print(f"Starting server on port {args.port}...")
        server_proc = start_server(args.port)
        print(f"Server running. Log: {LOG_FILE}")

    print("Opening desktop window...")
    window = webview.create_window(
        title="Helix Codex OS",
        url=f"http://127.0.0.1:{args.port}",
        width=1400, height=900, resizable=True, text_select=True,
    )
    def on_closing():
        if server_proc:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()
        sys.exit(0)
    window.events.closing += on_closing
    webview.start(debug=False)

if __name__ == "__main__":
    main()
