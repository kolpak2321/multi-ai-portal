#!/bin/sh
set -eu
Xvfb :99 -screen 0 1200x900x24 -nolisten tcp &
sleep 1
x11vnc -display :99 -localhost -forever -shared -nopw -rfbport 5900 -quiet &
websockify --web /usr/share/novnc/ 7900 127.0.0.1:5900 >/dev/null 2>&1 &
exec python browser_worker.py
