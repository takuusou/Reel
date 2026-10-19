/* ============================================================
   Reel — 前端交互
   ============================================================ */

const $ = (sel) => document.querySelector(sel);

const urlInput   = $('#urlInput');
const clearBtn   = $('#clearBtn');
const inputWrap  = document.querySelector('.input-wrap');
const parseHint  = $('#parseHint');
const preview    = $('#preview');
const thumbImg   = $('#thumbImg');
const durBadge   = $('#durBadge');
const vidTitle   = $('#vidTitle');
const vidUploader= $('#vidUploader');
const downloadBtn= $('#downloadBtn');
const qualityRow = $('#qualityRow');
const toastContainer = $('#toastContainer');

/* ---------- Toast 系统 ---------- */
function showToast(message, type = 'info', duration = 5000) {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span class="toast-msg">${escapeHtml(message)}</span><button class="toast-close" aria-label="关闭">×</button>`;
  toast.querySelector('.toast-close').addEventListener('click', () => dismissToast(toast));
  toastContainer.appendChild(toast);
  if (duration > 0) setTimeout(() => dismissToast(toast), duration);
}
function dismissToast(toast) {
  if (!toast.parentNode) return;
  toast.classList.add('toast-out');
  setTimeout(() => toast.remove(), 220);
}
const jobsSection= $('#jobsSection');
const jobsList   = $('#jobsList');
const historyList= $('#historyList');
const openFolderBtn= $('#openFolderBtn');
const coreState = $('#coreState');
const historyCount = $('#historyCount');
const downloadLabel = downloadBtn.querySelector('[data-role="download-label"]');

let currentFmt = 'mp4';
let currentQuality = '1080';
let lastTitle = '';
let parseTimer = null;
let historyPage = 1;
let historyPages = 1;

/* ---------- 健康检查(右上角状态灯) ---------- */
async function checkHealth() {
  try {
    const r = await fetch('/api/health');
    const d = await r.json();
    const dot = $('#statusDot');
    const txt = $('#statusText');
    if (d.ytdlp && d.ffmpeg && !d.gallerydl) {
      dot.className = 'status-dot bad';
      txt.textContent = '缺少 gallery-dl,请重新启动';
      if (coreState) {
        coreState.className = 'mini-pill warn';
        coreState.textContent = 'Missing gallery-dl';
      }
    } else if (d.ytdlp && d.ffmpeg) {
      dot.className = 'status-dot ok';
      txt.textContent = '内核就绪';
      if (coreState) {
        coreState.className = 'mini-pill ready';
        coreState.textContent = 'Ready';
      }
    } else if (d.ytdlp) {
      dot.className = 'status-dot bad';
      txt.textContent = '缺少 ffmpeg';
      if (coreState) {
        coreState.className = 'mini-pill warn';
        coreState.textContent = 'Missing ffmpeg';
      }
    } else {
      dot.className = 'status-dot bad';
      txt.textContent = '未检测到 yt-dlp';
      if (coreState) {
        coreState.className = 'mini-pill warn';
        coreState.textContent = 'Missing yt-dlp';
      }
    }
  } catch (e) {
    $('#statusDot').className = 'status-dot bad';
    $('#statusText').textContent = '服务异常';
    if (coreState) {
      coreState.className = 'mini-pill warn';
      coreState.textContent = 'Offline';
    }
  }
}

/* ---------- 输入框:解析预览 ---------- */
urlInput.addEventListener('input', () => {
  const val = urlInput.value.trim();
  inputWrap.classList.toggle('filled', val.length > 0);
  clearTimeout(parseTimer);
  if (!val) {
    hidePreview();
    parseHint.className = 'parse-hint';
    parseHint.textContent = '等待链接';
    return;
  }
  // 输入停顿 700ms 后再解析,避免一边打字一边请求
  parseHint.className = 'parse-hint loading';
  parseHint.textContent = '解析中';
  parseTimer = setTimeout(() => fetchInfo(val), 700);
});

clearBtn.addEventListener('click', () => {
  urlInput.value = '';
  inputWrap.classList.remove('filled');
  hidePreview();
  parseHint.className = 'parse-hint';
  parseHint.textContent = '等待链接';
  urlInput.focus();
});

function hidePreview() {
  preview.classList.add('hidden');
  lastTitle = '';
}

async function fetchInfo(url) {
  try {
    const r = await fetch('/api/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const d = await r.json();
    if (urlInput.value.trim() !== url) return;
    if (!d.ok) {
      // 预览只是锦上添花,失败不影响下载(例如 Instagram 图片帖)
      hidePreview();
      parseHint.className = d.unsupported ? 'parse-hint error' : 'parse-hint';
      parseHint.textContent = d.unsupported ? d.error : '无法预览,可直接下载';
      return;
    }
    lastTitle = d.title || '';
    vidTitle.textContent = d.title || '未知标题';
    vidUploader.textContent = d.uploader || '';
    if (d.thumbnail) {
      thumbImg.src = d.thumbnail;
      thumbImg.style.display = 'block';
      preview.classList.remove('no-thumb');
    } else {
      thumbImg.style.display = 'none';
      preview.classList.add('no-thumb');
    }
    durBadge.textContent = d.duration ? formatDuration(d.duration) : '';
    durBadge.style.display = d.duration ? 'block' : 'none';
    preview.classList.remove('hidden');
    parseHint.className = 'parse-hint';
    parseHint.textContent = '已识别';
  } catch (e) {
    if (urlInput.value.trim() !== url) return;
    hidePreview();
    parseHint.className = 'parse-hint';
    parseHint.textContent = '无法预览,可直接下载';
  }
}

function formatDuration(sec) {
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (n) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

/* ---------- 格式 / 画质 切换 ---------- */
$('#fmtSeg').addEventListener('click', (e) => {
  const btn = e.target.closest('.seg');
  if (!btn) return;
  document.querySelectorAll('#fmtSeg .seg').forEach(b => {
    b.classList.remove('active');
    b.setAttribute('aria-pressed', 'false');
  });
  btn.classList.add('active');
  btn.setAttribute('aria-pressed', 'true');
  currentFmt = btn.dataset.fmt;
  // 只有 MP4 需要画质选项
  qualityRow.classList.toggle('hidden', currentFmt !== 'mp4');
  if (currentFmt === 'image') {
    parseHint.className = 'parse-hint';
    parseHint.textContent = '图片模式适合图片帖 / 图文链接';
  } else if (!urlInput.value.trim()) {
    parseHint.className = 'parse-hint';
    parseHint.textContent = '等待链接';
  }
});

$('#qSeg').addEventListener('click', (e) => {
  const btn = e.target.closest('.seg');
  if (!btn) return;
  document.querySelectorAll('#qSeg .seg').forEach(b => {
    b.classList.remove('active');
    b.setAttribute('aria-pressed', 'false');
  });
  btn.classList.add('active');
  btn.setAttribute('aria-pressed', 'true');
  currentQuality = btn.dataset.q;
});

/* ---------- 开始下载 ---------- */
downloadBtn.addEventListener('click', async () => {
  const url = urlInput.value.trim();
  if (!url) {
    parseHint.className = 'parse-hint error';
    parseHint.textContent = '请先粘贴一个链接';
    return;
  }
  const title = lastTitle || '下载任务';
  try {
    downloadBtn.disabled = true;
    downloadLabel.textContent = '创建任务中';
    const r = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        format: currentFmt,
        quality: currentQuality,
      }),
    });
    const d = await r.json();
    if (!d.ok) {
      parseHint.className = 'parse-hint error';
      parseHint.textContent = d.error || '无法开始下载';
      return;
    }
    addJobCard(d.job_id, title, currentFmt);
    pollJob(d.job_id);
  } catch (e) {
    parseHint.className = 'parse-hint error';
    parseHint.textContent = '请求失败,请重试';
  } finally {
    downloadBtn.disabled = false;
    downloadLabel.textContent = '开始下载';
  }
});

/* ---------- 任务卡片 ---------- */
function addJobCard(jobId, title, fmt) {
  jobsSection.classList.remove('hidden');
  const tag = fmt === 'mp3' ? 'MP3' : (fmt === 'image' ? '图片' : 'MP4');
  const card = document.createElement('div');
  card.className = 'job-card';
  card.id = 'job-' + jobId;
  card.innerHTML = `
    <div class="job-top">
      <span class="job-name">${escapeHtml(title)} · ${tag}</span>
      <span class="job-state" data-role="state">排队中</span>
    </div>
    <div class="bar"><div class="bar-fill" data-role="fill"></div></div>
    <div class="job-bottom">
      <span data-role="speed"></span>
      <span data-role="eta"></span>
    </div>
  `;
  jobsList.prepend(card);
}

function pollJob(jobId) {
  const timer = setInterval(async () => {
    try {
      const r = await fetch('/api/status/' + jobId);
      const d = await r.json();
      if (!d.ok) { clearInterval(timer); return; }
      updateJobCard(jobId, d);
      if (d.status === 'done' || d.status === 'error') {
        clearInterval(timer);
        if (d.status === 'done') {
          loadHistory(historyPage);
          showToast(d.message || '下载完成，文件已保存', 'success');
        } else {
          showToast('下载失败：' + (d.error || '未知错误'), 'error', 8000);
        }
      }
    } catch (e) { /* 网络抖动,下次再试 */ }
  }, 700);
}

function updateJobCard(jobId, d) {
  const card = $('#job-' + jobId);
  if (!card) return;
  const state = card.querySelector('[data-role="state"]');
  const fill  = card.querySelector('[data-role="fill"]');
  const speed = card.querySelector('[data-role="speed"]');
  const eta   = card.querySelector('[data-role="eta"]');

  const pct = parseFloat((d.percent || '').replace('%', '')) || 0;

  if (d.status === 'downloading') {
    state.textContent = (d.percent || '0%').trim();
    state.className = 'job-state';
    fill.className = 'bar-fill';
    fill.style.width = pct + '%';
    speed.textContent = d.speed ? '速度 ' + d.speed : '';
    eta.textContent = d.eta ? '剩余 ' + d.eta : '';
  } else if (d.status === 'processing') {
    state.textContent = '处理中';
    state.className = 'job-state';
    fill.className = 'bar-fill indeterminate';
    speed.textContent = d.speed || '处理中…';
    eta.textContent = '';
  } else if (d.status === 'done') {
    state.textContent = '完成';
    state.className = 'job-state done';
    fill.className = 'bar-fill done';
    fill.style.width = '100%';
    speed.textContent = d.message || '已保存到文件夹';
    eta.textContent = '';
  } else if (d.status === 'error') {
    state.textContent = '失败';
    state.className = 'job-state error';
    fill.className = 'bar-fill error';
    fill.style.width = '100%';
    speed.textContent = '';
    eta.textContent = '';
    let msg = card.querySelector('.job-error-msg');
    if (!msg) {
      msg = document.createElement('div');
      msg.className = 'job-error-msg';
      card.appendChild(msg);
    }
    msg.textContent = d.error || '下载失败';
  } else {
    state.textContent = '排队中';
  }
}

/* ---------- 历史 ---------- */
async function loadHistory(page = 1) {
  try {
    const r = await fetch('/api/history?page=' + page);
    const d = await r.json();
    if (!d.ok) return;
    historyPage = d.page;
    historyPages = d.pages;
    if (historyCount) historyCount.textContent = d.total || '0';
    if (!d.total) {
      historyList.innerHTML = '<div class="empty" id="historyEmpty">还没有下载记录</div>';
      updateHistoryPager();
      return;
    }
    historyList.innerHTML = d.items.map(it => `
      <div class="history-item">
        <span class="history-name">${escapeHtml(it.name)}</span>
        <span class="history-size">${it.size}</span>
      </div>
    `).join('');
    updateHistoryPager();
  } catch (e) { /* 忽略 */ }
}

function updateHistoryPager() {
  const pager = $('#historyPager');
  const prevBtn = $('#historyPrev');
  const nextBtn = $('#historyNext');
  const info = $('#historyPageInfo');
  if (!pager) return;
  if (historyPages <= 1) { pager.classList.add('hidden'); return; }
  pager.classList.remove('hidden');
  prevBtn.disabled = historyPage <= 1;
  nextBtn.disabled = historyPage >= historyPages;
  info.textContent = historyPage + ' / ' + historyPages;
}

$('#historyPrev').addEventListener('click', () => {
  if (historyPage > 1) loadHistory(historyPage - 1);
});
$('#historyNext').addEventListener('click', () => {
  if (historyPage < historyPages) loadHistory(historyPage + 1);
});

openFolderBtn.addEventListener('click', async () => {
  try {
    openFolderBtn.disabled = true;
    await fetch('/api/open-folder', { method: 'POST' });
  } catch (e) { /* 忽略 */ }
  finally {
    openFolderBtn.disabled = false;
  }
});

/* ---------- 小工具 ---------- */
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ---------- 启动 ---------- */
checkHealth();
loadHistory();
urlInput.focus();
