# -*- coding: utf-8 -*-
"""
Reel — 本地媒体下载台
粘贴链接 → 自动选择下载器 → 文件落地,其余全部在后台完成。

- Instagram、TikTok:gallery-dl(整篇帖子,含轮播 / 图集里的全部图片和视频)
- YouTube / 哔哩哔哩,以及所有平台的 MP3:yt-dlp
- 抖音不支持:抖音给作品接口加了反下载签名,主流开源项目的成功率也只有约 3/8
- 各平台的登录信息:由 Chrome 扩展「Get cookies.txt LOCALLY」
  导出到「下载」文件夹,Reel 下载时自动收进 .cookies/。
  (macOS 27 起,其他程序已无法直接读取 Chrome 的数据。)

纯本地运行,只监听 127.0.0.1,仅供自己使用。
"""

import os
import re
import sys
import json
import uuid
import shutil
import platform
import threading
import subprocess
import webbrowser
import urllib.parse
from pathlib import Path

from flask import Flask, render_template, request, jsonify

# ----------------------------------------------------------------------
# 基本配置
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"          # 下载好的文件放这里
JOBS_DIR = DOWNLOAD_DIR / ".jobs"              # 每个任务先下到自己的临时目录
COOKIE_DIR = BASE_DIR / ".cookies"             # 各平台登录信息(不入库)
INBOX_DIR = Path.home() / "Downloads"          # 浏览器扩展导出登录信息的默认位置
DOWNLOAD_DIR.mkdir(exist_ok=True)

PORT = int(os.environ.get("REEL_PORT", "8765"))
APP_VERSION = "2.4.0"

# 需要登录信息的平台 → 在 Chrome 里打开哪个网站导出。
# macOS 27 起,系统只允许 Chrome 自己读它的数据文件夹,其他程序都读不到,
# 所以登录信息由 Chrome 扩展「Get cookies.txt LOCALLY」导出到「下载」文件夹,Reel 自动收走。
LOGIN_SITES = {
    "instagram": "instagram.com",
    "youtube": "youtube.com",
    "tiktok": "tiktok.com",
    "bilibili": "bilibili.com",   # 登录后可下更高画质
}
# 扩展导出的文件名:www.instagram.com_cookies.txt,重名时 Chrome 会加 " (1)"
EXPORT_RE = re.compile(
    r"^(?:[\w-]+\.)*(instagram\.com|youtube\.com|tiktok\.com|bilibili\.com)_cookies(?: \(\d+\))?\.txt$", re.I)
SITE_TO_PLATFORM = {site: plat for plat, site in LOGIN_SITES.items()}
COOKIE_LOCK = threading.Lock()
DOUYIN_UNSUPPORTED = "Reel 不支持抖音(抖音给作品接口加了反下载签名)。请用抖音 App 的「分享 → 保存本地」"

app = Flask(__name__)

JOBS = {}
JOBS_LOCK = threading.Lock()

URL_RE = re.compile(r"https?://[^\s]+")
# 下载器的中间文件,不算成品
PARTIAL_RE = re.compile(r"\.(part|ytdl|tmp|temp)$|\.part-Frag|\.f\d+\.\w+$", re.I)
# 这些报错说明需要(新的)登录信息
LOGIN_ERROR_RE = re.compile(
    r"login|log in|sign in|not a bot|cookie|401|403|private|redirect", re.I)

# ----------------------------------------------------------------------
# 下载器
# ----------------------------------------------------------------------
def find_binary(name):
    """双击 .command 启动时 PATH 可能不全,额外检查 Homebrew 的安装位置。"""
    path = shutil.which(name)
    if path:
        return path
    for p in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
        if os.path.exists(p):
            return p
    return name


YTDLP = find_binary("yt-dlp")
FFMPEG = find_binary("ffmpeg")
GALLERYDL = [sys.executable, "-m", "gallery_dl"]  # 装在 Reel 自己的 .venv 里


def binary_ok(path):
    return bool(shutil.which(path) or os.path.exists(path))


def gallerydl_ok():
    try:
        import gallery_dl  # noqa: F401
        return True
    except ImportError:
        return False


# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------
def clean_error(text):
    """从下载器输出里挑出最像"错误原因"的一行。"""
    lines = [l for l in (text or "").splitlines() if l.strip()]
    if not lines:
        return "下载失败,请检查链接或网络。"
    err_lines = [l for l in lines if "error" in l.lower()]
    return (err_lines[-1] if err_lines else lines[-1]).strip()[:300]


def human_size(num):
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.0f}{unit}" if unit == "B" else f"{num:.1f}{unit}"
        num /= 1024
    return f"{num:.1f}TB"


def extract_first_url(text):
    """允许直接粘贴 B 站等分享文案,自动抓出第一条链接。"""
    match = URL_RE.search((text or "").strip())
    return match.group(0).strip() if match else ""


def detect_platform(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    if "douyin.com" in host:
        return "douyin"
    if "tiktok.com" in host:
        return "tiktok"
    if any(d in host for d in ("instagram.com", "instagr.am")):
        return "instagram"
    if any(d in host for d in ("youtube.com", "youtu.be")):
        return "youtube"
    if any(d in host for d in ("bilibili.com", "b23.tv")):
        return "bilibili"
    return "other"


def platform_extra_args(url):
    """yt-dlp 针对个别平台需要的请求头。"""
    plat = detect_platform(url)
    if plat == "instagram":
        return ["--add-header", "Referer:https://www.instagram.com/"]
    return []


# ----------------------------------------------------------------------
# 登录信息:Chrome 扩展导出到「下载」文件夹,Reel 自动收走
# ----------------------------------------------------------------------
def collect_cookie_exports():
    """把「下载」里扩展导出的登录信息移进 .cookies/,每个平台只留最新一份。"""
    try:
        candidates = [p for p in INBOX_DIR.iterdir() if EXPORT_RE.match(p.name) and p.is_file()]
    except OSError:
        return
    with COOKIE_LOCK:
        for p in sorted(candidates, key=lambda x: x.stat().st_mtime):   # 旧的先处理,新的覆盖
            plat = SITE_TO_PLATFORM[EXPORT_RE.match(p.name).group(1).lower()]
            try:
                with open(p, encoding="utf-8", errors="replace") as fp:
                    if "Netscape" not in fp.readline():
                        continue
                COOKIE_DIR.mkdir(mode=0o700, exist_ok=True)
                target = COOKIE_DIR / f"{plat}.txt"
                shutil.move(str(p), str(target))
                os.chmod(target, 0o600)
            except OSError:
                continue


def login_args(url):
    plat = detect_platform(url)
    if plat not in LOGIN_SITES:
        return []
    collect_cookie_exports()
    path = COOKIE_DIR / f"{plat}.txt"
    return ["--cookies", str(path)] if path.exists() else []


def explain_error(url, raw):
    """需要登录的平台报登录类错误时,告诉用户怎么导出登录信息。"""
    plat = detect_platform(url)
    if plat in LOGIN_SITES and LOGIN_ERROR_RE.search(raw):
        site = LOGIN_SITES[plat]
        state = "登录信息过期了" if (COOKIE_DIR / f"{plat}.txt").exists() else "需要登录信息"
        return (f"{state}:用 Chrome 打开 {site}(确认已登录),点工具栏里的 "
                f"Get cookies.txt LOCALLY → Export,然后重新点下载。原始报错:{raw[:120]}")
    return raw


# ----------------------------------------------------------------------
# 任务
# ----------------------------------------------------------------------
def update_job(job_id, **fields):
    with JOBS_LOCK:
        JOBS[job_id].update(fields)


def run_streaming(cmd, on_line):
    """运行下载器,逐行回调输出,返回 (退出码, 最后 20 行)。"""
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    tail = []
    for line in proc.stdout:
        line = line.rstrip("\n")
        if line.strip():
            tail = (tail + [line])[-20:]
        on_line(line)
    return proc.wait(), tail


def ytdlp_command(url, fmt, quality, job_dir, cookies):
    cmd = [
        YTDLP, "--newline", "--no-playlist",
        "--progress-template",
        "download:DLPROG|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
        "-P", str(job_dir),
        "-o", "%(title).80B [%(id)s].%(ext)s",
    ]
    cmd += cookies + platform_extra_args(url)
    if FFMPEG != "ffmpeg":
        cmd += ["--ffmpeg-location", FFMPEG]

    if fmt == "image":
        # 视频平台的"图片"就是封面
        cmd += ["--skip-download", "--write-thumbnail", "--convert-thumbnails", "jpg"]
    elif fmt == "mp3":
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        # 优先 H.264 + AAC(QuickTime / 剪辑软件兼容最好),没有再退到任意最佳
        h = {"720": "[height<=720]", "1080": "[height<=1080]"}.get(quality, "")
        selector = (f"bv*[vcodec^=avc1]{h}+ba[acodec^=mp4a]/"
                    f"bv*[vcodec^=avc1]{h}+ba/"
                    f"b[vcodec^=avc1]{h}/"
                    f"bv*{h}+ba/b{h}")
        cmd += ["-f", selector, "--merge-output-format", "mp4", "--recode-video", "mp4"]
    cmd.append(url)
    return cmd


def run_ytdlp(job_id, url, fmt, quality, job_dir, cookies):
    def on_line(line):
        if line.startswith("DLPROG|"):
            parts = line.split("|")
            update_job(job_id,
                       status="downloading",
                       percent=parts[1].strip() if len(parts) > 1 else "",
                       speed=parts[2].strip() if len(parts) > 2 else "",
                       eta=parts[3].strip() if len(parts) > 3 else "")
        elif any(k in line for k in ("[Merger]", "[ExtractAudio]", "[VideoConvertor]",
                                     "Merging formats", "[ThumbnailsConvertor]")):
            update_job(job_id, status="processing", speed="正在合并 / 转码…")

    return run_streaming(ytdlp_command(url, fmt, quality, job_dir, cookies), on_line)


def run_gallerydl(job_id, url, job_dir, cookies):
    count = 0

    def on_line(line):
        nonlocal count
        # gallery-dl 每下载完一个文件就输出一行路径;日志行以 "[" 开头
        if line.strip() and not line.startswith("["):
            count += 1
            update_job(job_id, status="processing", speed=f"已获取 {count} 个文件")

    update_job(job_id, status="processing", speed="正在读取帖子…")
    cmd = GALLERYDL + ["--destination", str(job_dir), "--no-part"] + cookies + [url]
    return run_streaming(cmd, on_line)


def collect_files(job_dir):
    """把任务目录里的成品移到 downloads/(保持子目录),返回成品列表。"""
    saved = []
    for p in sorted(job_dir.rglob("*")):
        if not p.is_file() or p.name.startswith(".") or PARTIAL_RE.search(p.name):
            continue
        target = DOWNLOAD_DIR / p.relative_to(job_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(p, target)
        saved.append(target)
    shutil.rmtree(job_dir, ignore_errors=True)
    return saved


def run_job(job_id, url, fmt, quality):
    """按平台选下载器:Instagram、TikTok 走 gallery-dl(MP3 除外),其余走 yt-dlp。"""
    use_gallerydl = detect_platform(url) in ("instagram", "tiktok") and fmt != "mp3"
    job_dir = JOBS_DIR / job_id

    if use_gallerydl and not gallerydl_ok():
        update_job(job_id, status="error",
                   error="缺少 gallery-dl,请关闭 Reel 后重新双击「启动 Reel.command」")
        return

    shutil.rmtree(job_dir, ignore_errors=True)
    job_dir.mkdir(parents=True)
    cookies = login_args(url)
    try:
        if use_gallerydl:
            code, tail = run_gallerydl(job_id, url, job_dir, cookies)
        else:
            code, tail = run_ytdlp(job_id, url, fmt, quality, job_dir, cookies)
    except Exception as e:
        code, tail = 1, [str(e)]

    saved = collect_files(job_dir)
    error = explain_error(url, clean_error("\n".join(tail)))
    if saved:
        message = f"已保存 {len(saved)} 个文件"
        if code != 0:
            message += f",部分内容失败:{error}"
        update_job(job_id, status="done", percent="100%", message=message)
    else:
        update_job(job_id, status="error", error=error)


# ----------------------------------------------------------------------
# 路由(前端会调用这些接口)
# ----------------------------------------------------------------------
@app.before_request
def only_local():
    """只接受本机地址访问,挡住其他网页借浏览器调用本地接口。"""
    if (request.host or "").split(":")[0] not in ("127.0.0.1", "localhost"):
        return jsonify({"ok": False, "error": "forbidden"}), 403


@app.route("/")
def index():
    return render_template("index.html", version=APP_VERSION)


@app.route("/api/health")
def api_health():
    return jsonify({
        "ok": True,
        "ytdlp": binary_ok(YTDLP),
        "ffmpeg": binary_ok(FFMPEG),
        "gallerydl": gallerydl_ok(),
        "version": APP_VERSION,
    })


@app.route("/api/info", methods=["POST"])
def api_info():
    """粘上链接后,先解析出标题/封面/时长给用户预览。预览失败不影响下载。"""
    body = request.get_json(silent=True) or {}
    url = extract_first_url(body.get("url", ""))
    if not url:
        return jsonify({"ok": False, "error": "请输入链接"}), 400
    if detect_platform(url) == "douyin":
        return jsonify({"ok": False, "unsupported": True, "error": DOUYIN_UNSUPPORTED}), 400
    try:
        cmd = [YTDLP, "-J", "--no-playlist", "--no-warnings", "--ignore-no-formats-error"]
        cmd += login_args(url) + platform_extra_args(url) + [url]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60)
        if proc.returncode != 0:
            return jsonify({"ok": False, "error": explain_error(url, clean_error(proc.stderr))}), 400
        data = json.loads(proc.stdout)
        return jsonify({
            "ok": True,
            "title": data.get("title") or "未知标题",
            "uploader": data.get("uploader") or data.get("channel") or "",
            "duration": data.get("duration") or 0,
            "thumbnail": data.get("thumbnail") or "",
        })
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "解析超时"}), 408
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/download", methods=["POST"])
def api_download():
    """开始一个下载任务,立即返回任务 id,前端凭它去轮询进度。"""
    body = request.get_json(silent=True) or {}
    url = extract_first_url(body.get("url", ""))
    fmt = body.get("format", "mp4")
    quality = body.get("quality", "1080")
    if not url:
        return jsonify({"ok": False, "error": "请输入链接"}), 400
    if fmt not in ("mp4", "mp3", "image"):
        fmt = "mp4"
    if detect_platform(url) == "douyin":
        return jsonify({"ok": False, "error": DOUYIN_UNSUPPORTED}), 400

    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "queued", "percent": "", "speed": "",
                        "eta": "", "error": "", "message": ""}
    threading.Thread(target=run_job, args=(job_id, url, fmt, quality), daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/status/<job_id>")
def api_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        return jsonify({"ok": True, **job})


@app.route("/api/history")
def api_history():
    """列出 downloads 里的文件(含子目录),最新的在前,每页 5 条。"""
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 5

    files = []
    for p in DOWNLOAD_DIR.rglob("*"):
        rel = p.relative_to(DOWNLOAD_DIR)
        if p.is_file() and not any(part.startswith(".") for part in rel.parts):
            files.append(p)
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    total = len(files)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    start = (page - 1) * per_page
    items = [{"name": p.name, "size": human_size(p.stat().st_size)}
             for p in files[start:start + per_page]]
    return jsonify({"ok": True, "items": items, "total": total, "page": page, "pages": pages})


@app.route("/api/open-folder", methods=["POST"])
def api_open_folder():
    """在访达/资源管理器里打开下载文件夹。"""
    try:
        system = platform.system()
        if system == "Darwin":
            subprocess.run(["open", str(DOWNLOAD_DIR)])
        elif system == "Windows":
            os.startfile(str(DOWNLOAD_DIR))  # noqa
        else:
            subprocess.run(["xdg-open", str(DOWNLOAD_DIR)])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ----------------------------------------------------------------------
# 启动
# ----------------------------------------------------------------------
if __name__ == "__main__":
    shutil.rmtree(JOBS_DIR, ignore_errors=True)   # 清理上次异常退出留下的临时目录
    local_url = f"http://127.0.0.1:{PORT}"
    if os.environ.get("REEL_OPEN_BROWSER", "1") != "0":
        threading.Timer(1.3, lambda: webbrowser.open(local_url)).start()
    print("\n" + "=" * 46)
    print(f"   Reel v{APP_VERSION} 已启动")
    print(f"   界面地址: {local_url}")
    print("   关闭这个窗口即可停止 Reel。")
    print("=" * 46 + "\n")
    app.run(host="127.0.0.1", port=PORT, threaded=True)
