#!/usr/bin/env python3
"""
Helix Prime - Unified Launcher
===============================
Starts the Streamlit Operations Cockpit.

Usage:
    python launch.py                    # start cockpit
    python launch.py --dash-only        # start cockpit (alias)
    python launch.py --port 8502        # custom port
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
COCKPIT_DIR = os.path.join(ROOT, 'cockpit')
COCKPIT_APP = os.path.join(COCKPIT_DIR, 'cockpit.py')

if not os.path.exists(COCKPIT_APP):
    print(f'Error: Cockpit app not found at {COCKPIT_APP}')
    sys.exit(1)

processes = []


def cleanup():
    print()
    for p in processes:
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
    print('All services stopped.')


def handle_signal(*_):
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def start_cockpit(port=8501):
    print(f'Starting Helix Prime Operations Cockpit on http://127.0.0.1:{port}')
    p = subprocess.Popen(
        [sys.executable, '-m', 'streamlit', 'run', COCKPIT_APP,
         '--server.headless=true', f'--server.port={port}',
         '--server.address=127.0.0.1'],
        cwd=ROOT,
    )
    processes.append(p)
    return p


def wait_for_health(url: str, label: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = urllib.request.urlopen(url, timeout=3)
            if r.status == 200:
                return True
        except (urllib.error.URLError, ConnectionResetError, ConnectionRefusedError):
            pass
        for p in processes:
            if p and p.poll() is not None and p.poll() != 0:
                print(f'{label} exited unexpectedly (code {p.poll()}).')
                return False
        time.sleep(0.5)
    print(f'{label} health check timed out after {timeout}s')
    return False


if __name__ == '__main__':
    port = 8501
    for i, arg in enumerate(sys.argv):
        if arg == '--port' and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])

    start_cockpit(port)

    print()
    print('Waiting for cockpit to start...')

    if wait_for_health(f'http://127.0.0.1:{port}', 'Cockpit'):
        print()
        print(f'Cockpit is running at http://127.0.0.1:{port}')
        print('Press Ctrl+C to stop.')
    else:
        print()
        print('Cockpit failed to start. See errors above.')
        cleanup()

    try:
        while processes and all(p and p.poll() is None for p in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    cleanup()
