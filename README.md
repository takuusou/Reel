# Reel · 本地媒体下载台

粘贴链接,在自己的电脑上下载 Instagram、YouTube、TikTok、哔哩哔哩的视频、音频或图片。当前正式版 `v2.4.0`,macOS 本地浏览器版。

使用方法见 [使用说明.md](使用说明.md)。

## 设计原则

平台兼容交给持续维护的下载器,Reel 只做一层薄壳:不自己抓网页、不自己解密、没有回退链。

| 平台 | 下载器 |
|---|---|
| Instagram、TikTok(MP4 / 图片) | gallery-dl,整篇帖子含轮播 / 图集全部内容 |
| YouTube、哔哩哔哩,以及所有平台的 MP3 | yt-dlp |
| 抖音 | 不支持:作品接口有反下载签名。DouK-Downloader 在代码里记录的 2026-09-08 实测,带逆向签名也只有约 3/8 成功;yt-dlp 的抖音提取器缺签名(源码标注 TODO) |

- **登录信息**:Instagram、YouTube 需要;哔哩哔哩可选(登录后画质更高);TikTok 按需。macOS 27 起系统禁止其他程序读取 Chrome 的数据文件夹(Application Support 保护),所以不再从浏览器数据库读取,改由 Chrome 扩展 Get cookies.txt LOCALLY 在各网站导出 `<网站>_cookies.txt` 到「下载」。Reel 每次下载前把这些文件移进 `.cookies/<平台>.txt`(权限 600,不入库),每个平台保留最新一份。报错像登录问题时,提示用户在对应网站重新导出。
- **成功判定**:每个任务先下载到 `downloads/.jobs/<任务ID>/`,结束后把成品移到 `downloads/`,按实际移出的文件计数;一个文件都没有就是失败,有文件但下载器报错则标注"部分内容失败"。
- **依赖更新**:gallery-dl 装在项目 `.venv`,yt-dlp、ffmpeg 来自 Homebrew。启动器每天在后台更新一次 gallery-dl 和 yt-dlp。
- **本地安全**:只监听 127.0.0.1,并拒绝非本机 Host 的请求。

## 安装与启动

```bash
brew install yt-dlp ffmpeg
```

双击 `启动 Reel.command`。首次会创建 `.venv` 并安装 `requirements.txt`(Flask、gallery-dl),之后每次启动补齐依赖,默认打开 `http://127.0.0.1:8765/`。

手动启动:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python app.py
```

## 结构

```text
app.py                 Flask 接口、平台分流、登录信息、任务
templates/index.html   页面结构
static/app.js          页面交互与进度轮询
static/style.css       黑白界面样式
requirements.txt       Python 依赖(Flask、gallery-dl)
启动 Reel.command       macOS 启动器
downloads/             下载文件(不入库)
.cookies/              各平台登录信息(不入库)
```

## 已知限制

- 登录信息需要用扩展手动导出,过期后再导出一次;Windows 未适配。
- 任务状态保存在内存,重启后不保留;已下载文件仍在。
- B 站多 P 合集只下当前这一个视频。

## 致谢

Reel 的下载能力与本地运行离不开以下开源项目和工具。感谢它们的开发者、维护者及贡献者。

**以下感谢不分先后。**

- **yt-dlp**：提供 YouTube、哔哩哔哩等平台的媒体解析、下载与音频提取支持。
- **gallery-dl**：提供 Instagram、TikTok 帖子及轮播图集的下载支持。
- **FFmpeg**：提供音视频合并、格式转换与音频转码支持。
- **Flask**：提供本地 Web 服务与接口。
- **Python**：提供应用运行环境。
- **Get cookies.txt LOCALLY**：帮助用户从 Chrome 导出网站登录信息，供下载器使用。
