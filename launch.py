#!/usr/bin/env python3
"""
Helix Prime - Unified Launcher
===============================
Starts both the Flask webapp (helix-story) and the Streamlit dashboard
(Ecosystem) from a single command.

Usage:
    python launch.py                    # start both
    python launch.py --web-only         # start only webapp
    python launch.py --dash-only        # start only dashboard
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
WEBAPP_DIR = os.path.join(ROOT, 'helix-story')
DASHBOARD_DIR = os.path.join(
    ROOT, 'AI Automation Engineering', '04_helix_mini', 'Helix Prime Ecosystem'
)

# Check if dashboard path exists; if not, warn user and disable dashboard launch
if not os.path.exists(DASHBOARD_DIR):
    print(f'Warning: Dashboard directory not found at {DASHBOARD_DIR}')
    print('   Launching webapp only. To enable dashboard, ensure the module is present.')
    DASHBOARD_DIR = None

# Check if webapp path exists; if not, warn user and disable webapp launch
if not os.path.exists(WEBAPP_DIR):
    print(f'Warning: Webapp directory not found at {WEBAPP_DIR}')
    print('   Launching dashboard only. To enable webapp, ensure helix-story is present.')
    WEBAPP_DIR = None

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


def start_webapp():
    if WEBAPP_DIR is None:
        print('Skipping webapp: directory not found.')
        return None
    print('Starting Helix Prime Story (webapp) on http://localhost:5000')
    env = os.environ.copy()
    env['PORT'] = '5000'
    env['PYTHONUNBUFFERED'] = '1'
    p = subprocess.Popen(
        [sys.executable, 'app.py'],
        cwd=WEBAPP_DIR,
        env=env,
    )
    processes.append(p)
    return p


def start_dashboard():
    if DASHBOARD_DIR is None:
        print('Skipping dashboard: directory not found.')
        return None
    print('Starting Helix Prime Dashboard on http://localhost:8501')
    p = subprocess.Popen(
        [sys.executable, 'run.py'],
        cwd=DASHBOARD_DIR,
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
    web_only = '--web-only' in sys.argv
    dash_only = '--dash-only' in sys.argv

    if not dash_only:
        start_webapp()
    if not web_only:
        time.sleep(1.5)
        start_dashboard()

    print()
    print('Waiting for services to start...')

    all_healthy = True
    if WEBAPP_DIR and not dash_only:
        all_healthy &= wait_for_health('http://localhost:5000/health', 'Webapp')
    if DASHBOARD_DIR and not web_only:
        all_healthy &= wait_for_health('http://localhost:8501', 'Dashboard')

    if all_healthy:
        print()
        print('All services are running!')
        print('Press Ctrl+C to stop both services.')
    else:
        print()
        print('Some services failed to start. See errors above.')
        cleanup()

    try:
        while processes and all(p and p.poll() is None for p in processes):
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    cleanup()
