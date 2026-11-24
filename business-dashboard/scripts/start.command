#!/bin/bash
# macOS 双击启动。找不到依赖时自动退到离线版。
cd "$(dirname "$0")/.." || exit 1
mkdir -p data

PY=""
for candidate in ./venv/bin/python3 /opt/anaconda3/bin/python3 /usr/local/bin/python3 "$(command -v python3)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then
    if "$candidate" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
      PY="$candidate"
      break
    fi
    if [ -z "$PY" ]; then PY="$candidate"; fi
  fi
done

if [ -z "$PY" ]; then
  echo "没找到 Python，打开离线版。"
  open "index.html"
  exit 0
fi

if ! "$PY" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "正在安装 fastapi / uvicorn / pydantic…"
  "$PY" -m pip install --quiet fastapi uvicorn pydantic >> data/start.log 2>&1
  if ! "$PY" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
    echo ""
    echo "依赖装不上（可能是网络或权限）。已打开离线版。"
    open "index.html"
    exit 0
  fi
fi

exec "$PY" run.py
