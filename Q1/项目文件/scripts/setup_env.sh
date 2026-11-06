#!/usr/bin/env bash
# 一键创建（或复用）虚拟环境并安装依赖。
# 用法：bash scripts/setup_env.sh
# 兼容 Git Bash / PowerShell(Git) / macOS / Linux。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON:-python}"

if [ ! -d .venv ]; then
    echo "[1/3] 创建虚拟环境 .venv（解释器：$($PYTHON_BIN -V 2>&1)）"
    "$PYTHON_BIN" -m venv .venv
else
    echo "[1/3] 复用已有 .venv"
fi

# Windows 的 venv 在 Scripts/，POSIX 在 bin/
if [ -f .venv/Scripts/activate ]; then
    # shellcheck disable=SC1091
    . .venv/Scripts/activate
else
    # shellcheck disable=SC1091
    . .venv/bin/activate
fi

echo "[2/3] 升级 pip"
python -m pip install --upgrade pip --quiet || echo "    pip 升级失败，跳过"

echo "[3/3] 安装 requirements.txt"
# 默认走本机 pip 配置的源；失败则回退官方 PyPI，避免镜像抽风卡住环境
if ! python -m pip install -r requirements.txt; then
    echo "    默认源安装失败，回退官方 PyPI 重试"
    python -m pip install -r requirements.txt --index-url https://pypi.org/simple
fi

echo
python - <<'PY'
import sys
import pandas
import requests
import tqdm
print(f"环境就绪：Python {sys.version.split()[0]} | requests {requests.__version__} | "
      f"pandas {pandas.__version__} | tqdm {tqdm.__version__}")
print(f"解释器路径：{sys.executable}")
PY

echo
echo "激活：source .venv/Scripts/activate   （Git Bash / Windows）"
echo "      .venv\\Scripts\\activate          （cmd）"
echo "运行：python main.py"
