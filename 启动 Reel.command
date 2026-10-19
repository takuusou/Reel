#!/bin/bash
# ============================================================
#  Reel 启动器 — 双击我即可运行
# ============================================================

# 切换到脚本所在目录(也就是 Reel 项目文件夹)
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
PIP_FAST=(--quiet --timeout 10 --retries 1)
TUNA=(-i https://pypi.tuna.tsinghua.edu.cn/simple)

echo ""
echo "  ┌──────────────────────────────┐"
echo "  │   Reel · 本地媒体下载台        │"
echo "  └──────────────────────────────┘"
echo ""

# 1. 确认 python3 存在
if ! command -v python3 &>/dev/null; then
  echo -e "${RED}没有找到 python3。可运行: brew install python${NC}"
  read -p "按回车键退出..."; exit 1
fi

# 2. 运行环境:首次创建 .venv;之后每次启动补齐依赖(已装好时一两秒就过)
if [ ! -d ".venv" ]; then
  echo -e "${YELLOW}首次启动,正在初始化(安装 Flask 和 gallery-dl,稍等片刻)...${NC}"
  python3 -m venv .venv
  ./.venv/bin/pip install "${PIP_FAST[@]}" --upgrade pip 2>/dev/null \
    || ./.venv/bin/pip install "${PIP_FAST[@]}" --upgrade pip "${TUNA[@]}"
fi
./.venv/bin/pip install "${PIP_FAST[@]}" -r requirements.txt 2>/dev/null \
  || ./.venv/bin/pip install "${PIP_FAST[@]}" -r requirements.txt "${TUNA[@]}" \
  || echo -e "${RED}依赖安装失败,请检查网络后重新双击启动。${NC}"

# 3. yt-dlp / ffmpeg 由 Homebrew 提供
if ! command -v yt-dlp &>/dev/null || ! command -v ffmpeg &>/dev/null; then
  echo -e "${YELLOW}提示:缺少 yt-dlp 或 ffmpeg。请先运行: brew install yt-dlp ffmpeg${NC}"
fi

# 4. 每天在后台更新一次下载器。平台改版导致下载失败时,更新通常就能修好;不影响启动速度
STAMP=".venv/.last-update"
if [ ! -f "$STAMP" ] || [ -n "$(find "$STAMP" -mtime +0 2>/dev/null)" ]; then
  touch "$STAMP"
  nohup bash -c '
    ./.venv/bin/pip install --quiet --upgrade gallery-dl
    if command -v brew >/dev/null; then brew upgrade yt-dlp; fi
  ' > .venv/update.log 2>&1 &
fi

# 5. 如果服务已经在跑,直接打开浏览器
if command -v lsof &>/dev/null && lsof -iTCP:8765 -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo -e "${YELLOW}Reel 已经在运行,正在打开浏览器界面...${NC}"
  open "http://127.0.0.1:8765"
  echo "  如果界面不对,请关闭正在运行的 Reel 窗口后重新双击。"
  read -p "按回车键退出..."
  exit 0
fi

# 6. 启动!(app.py 会自动打开浏览器)
echo -e "${GREEN}正在启动 Reel,浏览器将自动打开界面...${NC}"
echo "  (想停止 Reel,关闭这个窗口即可)"
echo ""
./.venv/bin/python app.py
