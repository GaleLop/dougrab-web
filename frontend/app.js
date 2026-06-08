// DouGrab v4.3 — 按账号+日期归类，7天限制
const VERSION = '4.3.1';
const MAX_DAYS = 999;

const state = {
  videos: [], selectedIds: new Set(),
  accounts: [], activeAccount: 'all',
  dateStart: null, dateEnd: null,
};

function init() {
  const today = new Date();
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 6);
  document.getElementById('dateEnd').value = fmtDate(today);
  document.getElementById('dateStart').value = fmtDate(weekAgo);
  state.dateStart = weekAgo;
  state.dateEnd = today;
  pollStatus();
  setInterval(pollStatus, 5000);
}

function fmtDate(d) { return d.toISOString().split('T')[0]; }

function setDatePreset(preset) {
  const today = new Date();
  const end = document.getElementById('dateEnd');
  const start = document.getElementById('dateStart');
  end.value = fmtDate(today);
  switch(preset) {
    case 'today': start.value = fmtDate(today); break;
    case 'yesterday': const y = new Date(today); y.setDate(y.getDate()-1); start.value = fmtDate(y); break;
    case '3days': const d3 = new Date(today); d3.setDate(d3.getDate()-2); start.value = fmtDate(d3); break;
    case 'week': const w = new Date(today); w.setDate(w.getDate()-6); start.value = fmtDate(w); break;
  }
  validateDateRange();
}

function validateDateRange() {
  // 不限制天数，用户自由选择
  const warn = document.getElementById('dateWarn');
  warn.textContent = '';
  warn.className = 'date-warn';
}

// ===== 状态轮询 =====
let lastLoggedIn = false;
async function pollStatus() {
  try {
    const r = await (await fetch('/api/status')).json();
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    const btn = document.getElementById('btnOpenDouyin');
    let cls = 'offline', msg = '';
    if (!r.cdp_ready) { msg = 'Chrome 未就绪 — 正在启动...'; cls = 'offline'; if(btn)btn.style.display='none'; }
    else if (!r.logged_in) {
      if (activeTab === 'batch') {
        // 批量下载模式：不需要登录，只需要抖音页面用于刷新CDN
        msg = '链接批量下载模式 — 无需登录抖音';
        cls = 'online';
        if(btn){
          btn.textContent = '打开抖音页面（用于CDP）';
          btn.style.display = '';
        }
      } else {
        msg = '未登录抖音 — 点击打开抖音登录';
        cls = 'connecting';
        if(btn)btn.style.display='';
      }
    }
    else { msg = '已登录 — 可以开始抓取'; cls = 'online'; if(btn)btn.style.display='none'; }
    dot.className = 'status-dot ' + cls;
    text.textContent = msg;
    if (r.logged_in && !lastLoggedIn) toast('登录成功！', 'success');
    lastLoggedIn = r.logged_in;
  } catch(e) {}
}

async function openDouyinLogin() {
  const btn = document.getElementById('btnOpenDouyin');
  btn.disabled = true;
  const label = activeTab === 'batch' ? '打开抖音页面...' : '打开中...';
  btn.textContent = label;
  try {
    const r = await (await fetch('/api/open_douyin')).json();
    if (r.ok) toast('已打开抖音页面，请扫码登录', 'success');
    else toast(r.error || '失败', 'error');
  } catch(e) { toast('请求失败', 'error'); }
  btn.disabled = false; btn.textContent = '打开抖音登录';
}

// ===== 解析账号 =====
function parseAccounts() {
  const raw = document.getElementById('accountUrls').value.trim();
  if (!raw) return [];
  const lines = raw.split(/[\n\r]+/).filter(l => l.trim());
  const accounts = [];
  for (const line of lines) {
    // 支持: URL 或 URL,名称
    let url = line.trim(), name = '';
    const commaIdx = url.indexOf(',');
    if (commaIdx > 0) {
      name = url.slice(commaIdx + 1).trim();
      url = url.slice(0, commaIdx).trim();
    }
    const m = url.match(/\/user\/([^?&#\s]+)/);
    if (m) {
      if (!name) name = m[1].slice(0, 20);
      accounts.push({ url, secUid: m[1], name });
    }
  }
  return accounts;
}

// ===== 开始抓取 =====
async function doStart() {
  validateDateRange();
  const s = new Date(document.getElementById('dateStart').value);
  const e = new Date(document.getElementById('dateEnd').value);
  e.setHours(23, 59, 59, 999);
  state.dateStart = s;
  state.dateEnd = e;

  const accounts = parseAccounts();
  if (!accounts.length) { toast('请粘贴至少一个抖音账号链接', 'error'); return; }

  state.videos = [];
  state.selectedIds.clear();
  state.accounts = accounts;
  state.activeAccount = 'all';
  document.getElementById('toolbar').style.display = 'none';
  document.getElementById('videoGrid').innerHTML = '';
  document.getElementById('btnStart').disabled = true;
  document.getElementById('btnStart').textContent = '抓取中...';

  const allVideos = [];
  const seen = new Set();
  const total = accounts.length;
  let done = 0;

  setProgress(0, total, '准备抓取 ' + total + ' 个账号...');

  for (let i = 0; i < accounts.length; i++) {
    const acct = accounts[i];
    setProgress(i, total, '正在抓取 (' + (i+1) + '/' + total + '): ' + acct.name);
    try {
      let data = null;
      let success = false;
      for (let retry = 0; retry < 3; retry++) {
        try {
          setProgress(i, total, '正在抓取 (' + (i+1) + '/' + total + '): ' + acct.name + (retry > 0 ? ' (重试' + retry + ')' : ''));
          const resp = await fetch('/api/fetch?sec_uid=' + encodeURIComponent(acct.secUid));
          const resData = await resp.json();
          if (resData.error) throw new Error(resData.error);
          if (!resData.aweme_list || !resData.aweme_list.length) throw new Error('无视频');
          data = resData;
          success = true;
          break;
        } catch(err) {
          if (retry < 2) {
            const wait = 3000 * (retry + 2);  // 6s, 9s
            await new Promise(r => setTimeout(r, wait));
          } else {
            toast('抓取失败 ' + acct.name + ': ' + (err.message || '未知错误'), 'error');
          }
        }
      }
      if (!success || !data) continue;

      for (const v of data.aweme_list) {
        const vid = String(v.aweme_id);
        if (seen.has(vid)) continue;
        seen.add(vid);
        const vi = v.video || {};
        const ct = v.create_time || 0;
        // 日期筛选
        if (ct > 0) {
          const cdate = new Date(ct * 1000);
          if (cdate < s || cdate > e) continue;
        }
        allVideos.push({
          id: vid,
          desc: (v.desc || '').replace(/[\x00-\x1f\x7f-\x9f]/g, ''),
          createTime: ct,
          duration: v.duration || vi.duration || 0,
          cover: (vi.cover?.url_list || [])[0] || '',
          cdnUrl: (vi.play_addr?.url_list || [])[0] || '',
          author: acct.name,
          secUid: acct.secUid,
        });
      }
      done++;
    } catch(e) {
      toast('抓取失败 ' + acct.name + ': ' + e.message, 'error');
    }
  }

  state.videos = allVideos;
  renderAll();
  setProgress(done, total, '完成！共抓取 ' + allVideos.length + ' 个视频（' +
    fmtDate(s) + ' ~ ' + fmtDate(e) + '）');
  document.getElementById('btnStart').disabled = false;
  document.getElementById('btnStart').textContent = '开始抓取';
}

// ===== 按账号+日期分组渲染 =====
function renderAll() {
  renderAccountFilter();
  renderGroupedVideos();
  updateToolbar();
}

function renderAccountFilter() {
  const filter = document.getElementById('accountFilter');
  const unique = [...new Set(state.accounts.map(a => a.secUid))];
  filter.innerHTML = '<option value="all">全部账号 (' + state.videos.length + ')</option>';
  for (const uid of unique) {
    const acct = state.accounts.find(a => a.secUid === uid);
    const cnt = state.videos.filter(v => v.secUid === uid).length;
    filter.innerHTML += '<option value="' + uid + '">' + (acct?.name || uid) + ' (' + cnt + ')</option>';
  }
}

// 按账号分组，每个账号内按日期分组
function renderGroupedVideos() {
  let vids = [...state.videos];
  if (state.activeAccount !== 'all') vids = vids.filter(v => v.secUid === state.activeAccount);

  const grid = document.getElementById('videoGrid');
  grid.innerHTML = '';

  if (!vids.length) {
    grid.innerHTML = '<div class="empty">' +
      (state.videos.length ? '当前筛选条件下无视频，请切换账号或日期范围' : '粘贴账号链接，设定日期范围，点击「开始抓取」') +
      '</div>';
    return;
  }

  // 按账号分组
  const accountGroups = {};
  for (const v of vids) {
    const key = v.secUid;
    if (!accountGroups[key]) accountGroups[key] = { name: v.author, videos: [] };
    accountGroups[key].videos.push(v);
  }

  for (const [secUid, group] of Object.entries(accountGroups)) {
    // 账号标题
    const vCount = group.videos.length;
    grid.innerHTML += '<div class="account-section"><div class="account-header">' +
      '<span class="account-name">' + escapeHtml(group.name) + '</span>' +
      '<span class="account-count">' + vCount + ' 个视频</span>' +
      '</div>';

    // 按日期分组
    const dateGroups = {};
    for (const v of group.videos) {
      const d = v.createTime ? fmtDate(new Date(v.createTime * 1000)) : '未知';
      if (!dateGroups[d]) dateGroups[d] = [];
      dateGroups[d].push(v);
    }

    const sortedDates = Object.keys(dateGroups).sort().reverse();
    for (const date of sortedDates) {
      const dv = dateGroups[date];
      grid.innerHTML += '<div class="video-date-group"><div class="date-header">' +
        '<span class="date-label">' + date + '</span>' +
        '<span class="date-count">' + dv.length + ' 个</span>' +
        '<button class="btn btn-xs btn-outline" onclick="selectAccountGroup(\'' + secUid + '\')">全选此账号</button>' +
        '</div><div class="video-grid">';

      for (const v of dv) {
        const sel = state.selectedIds.has(v.id);
        const dur = formatDuration(v.duration);
        const time = v.createTime ? new Date(v.createTime * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '';
        grid.innerHTML += '<div class="video-card ' + (sel ? 'selected' : '') + '" onclick="toggleSelect(\'' + v.id + '\')">' +
          '<div class="check-mark">' + (sel ? '✓' : '') + '</div>' +
          '<img class="cover-img" src="' + v.cover + '" loading="lazy" onerror="this.style.display=\'none\'" alt="">' +
          '<div class="card-info"><div class="card-desc">' + escapeHtml(v.desc || '无描述') + '</div>' +
          '<div class="card-meta">' + dur + (time ? ' · ' + time : '') + '</div></div></div>';
      }

      grid.innerHTML += '</div></div>';
    }
    grid.innerHTML += '</div>';
  }
}

function selectDateGroup(date, secUid) {
  const vids = state.videos.filter(v => {
    if (secUid && v.secUid !== secUid) return false;
    if (state.activeAccount !== 'all' && v.secUid !== state.activeAccount) return false;
    const d = v.createTime ? fmtDate(new Date(v.createTime * 1000)) : '未知';
    return d === date;
  });
  for (const v of vids) state.selectedIds.add(v.id);
  renderGroupedVideos();
  updateToolbar();
}

function selectAccountGroup(secUid) {
  const vids = state.videos.filter(v => v.secUid === secUid);
  for (const v of vids) state.selectedIds.add(v.id);
  renderGroupedVideos();
  updateToolbar();
}

function renderVideoList() { renderGroupedVideos(); }

function toggleSelect(id) {
  if (state.selectedIds.has(id)) state.selectedIds.delete(id);
  else state.selectedIds.add(id);
  renderGroupedVideos();
  updateToolbar();
}

function selectAll() {
  let vids = [...state.videos];
  if (state.activeAccount !== 'all') vids = vids.filter(v => v.secUid === state.activeAccount);
  for (const v of vids) state.selectedIds.add(v.id);
  renderGroupedVideos();
  updateToolbar();
}

function deselectAll() {
  state.selectedIds.clear();
  renderGroupedVideos();
  updateToolbar();
}

function updateToolbar() {
  const tb = document.getElementById('toolbar');
  const selCnt = state.selectedIds.size;
  if (selCnt > 0) {
    tb.style.display = 'flex';
    document.getElementById('selCount').textContent = selCnt;
  } else {
    tb.style.display = 'none';
  }
}

// ===== 下载 =====
async function downloadSelected() {
  const ids = [...state.selectedIds];
  if (!ids.length) { toast('请先选择视频', 'error'); return; }

  toast('开始下载 ' + ids.length + ' 个视频...', 'info');

  let idx = 0;
  let failed = 0;
  for (const id of ids) {
    idx++;
    setProgress(idx - 1, ids.length, '刷新链接 ' + idx + '/' + ids.length + (failed ? ' (' + failed + ' 失败)' : ''));
    // 先刷新 CDN 链接
    let cdnUrl = '';
    try {
      const r = await fetch('/api/refresh_url?aweme_id=' + id, { timeout: 15000 });
      const d = await r.json();
      if (d.url) cdnUrl = d.url;
    } catch(e) {}
    if (!cdnUrl) {
      // 用存在的缓存 URL
      const v = state.videos.find(v => v.id === id);
      cdnUrl = v ? v.cdnUrl : '';
    }
    if (!cdnUrl) { failed++; continue; }

    setProgress(idx - 1, ids.length, '正在下载 ' + idx + '/' + ids.length + (failed ? ' (' + failed + ' 失败)' : ''));
    try {
      const a = document.createElement('a');
      a.href = '/api/download?aweme_id=' + id + '&url=' + encodeURIComponent(cdnUrl);
      a.download = id + '.mp4';
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      await new Promise(r => setTimeout(r, 3500));
    } catch(e) { failed++; }
  }

  const ok = ids.length - failed;
  setProgress(ids.length, ids.length, '下载完成！' + ok + ' 个成功' + (failed ? ', ' + failed + ' 个失败（CDN链接可能过期，请重新抓取）' : ''));
  state.selectedIds.clear();
  renderGroupedVideos();
  updateToolbar();
  toast('下载完成！', 'success');
}

// ===== 工具 =====
function filterByAccount() {
  state.activeAccount = document.getElementById('accountFilter').value;
  state.selectedIds.clear();
  renderAll();
}

function formatDuration(sec) {
  if (!sec) return '00:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return m + ':' + String(s).padStart(2, '0');
}

function setProgress(cur, total, text) {
  const bar = document.getElementById('progressBar');
  const textEl = document.getElementById('progressText');
  bar.style.display = 'block';
  const pct = total ? Math.round(cur / total * 100) : 0;
  bar.querySelector('.bar-fill').style.width = pct + '%';
  textEl.textContent = text + ' (' + pct + '%)';
}

function toast(msg, type) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + (type || 'info');
  t.style.display = 'block';
  clearTimeout(t._tid);
  t._tid = setTimeout(() => { t.style.display = 'none'; }, 3000);
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ===== Tab 切换 =====
let activeTab = 'fetch';
function switchTab(tab) {
  activeTab = tab;
  document.getElementById('tabFetch').className = 'tab-btn' + (tab === 'fetch' ? ' active' : '');
  document.getElementById('tabBatch').className = 'tab-btn' + (tab === 'batch' ? ' active' : '');
  document.getElementById('fetchPanel').style.display = tab === 'fetch' ? '' : 'none';
  document.getElementById('batchPanel').style.display = tab === 'batch' ? '' : 'none';
  if (tab === 'fetch') {
    const tb = document.getElementById('toolbar');
    tb.style.display = state.selectedIds.size > 0 ? 'flex' : 'none';
    document.getElementById('progressBar').style.display = 'none';
    document.getElementById('progressText').textContent = '';
    document.getElementById('videoGrid').style.display = '';
  } else {
    document.getElementById('toolbar').style.display = 'none';
    document.getElementById('progressBar').style.display = 'none';
    document.getElementById('progressText').textContent = '';
    document.getElementById('videoGrid').style.display = 'none';
  }
  pollStatus();  // 立即刷新状态显示
}

// ===== 链接批量下载 =====
let batchState = { awemeIds: [], results: [] };

async function parseLinks() {
  const raw = document.getElementById('videoLinks').value.trim();
  if (!raw) { toast('请粘贴视频链接', 'error'); return; }

  const btn = document.getElementById('btnParse');
  btn.disabled = true; btn.textContent = '解析中...';

  try {
    const resp = await fetch('/api/parse_links', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ links: raw })
    });
    const data = await resp.json();
    if (data.error) { toast(data.error, 'error'); return; }

    batchState.awemeIds = data.aweme_ids;
    batchState.results = [];
    toast('解析到 ' + data.count + ' 个视频ID', 'success');
    document.getElementById('btnDownBatch').disabled = false;

    // 预览列表
    const container = document.getElementById('batchResults');
    container.innerHTML = '<div class="batch-list"><div class="batch-header">' +
      '<span class="batch-label">待下载: ' + data.count + ' 个视频</span>' +
      '</div><div class="batch-ids">' +
      data.aweme_ids.map(id => '<span class="batch-id-tag" title="' + id + '">' + id + '</span>').join('') +
      '</div></div>';
  } catch(e) {
    toast('解析失败: ' + e.message, 'error');
  }
  btn.disabled = false; btn.textContent = '解析链接';
}

async function downloadBatch() {
  const ids = batchState.awemeIds;
  if (!ids.length) { toast('请先解析链接', 'error'); return; }

  // 确保抖音页面存在（用于CDP刷新CDN链接），不需要登录
  try {
    const st = await (await fetch('/api/status')).json();
    if (!st.has_douyin) {
      toast('正在打开抖音页面...', 'info');
      await fetch('/api/open_douyin');
      await new Promise(r => setTimeout(r, 5000));
    }
  } catch(e) {}

  const btn = document.getElementById('btnDownBatch');
  btn.disabled = true; btn.textContent = '下载中...';

  const progBar = document.getElementById('batchProgress');
  const barFill = document.getElementById('batchBarFill');
  const progText = document.getElementById('batchProgressText');
  const resultsDiv = document.getElementById('batchResults');

  progBar.style.display = 'block';
  resultsDiv.innerHTML = '';

  try {
    const resp = await fetch('/api/download_batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ aweme_ids: ids })
    });
    const data = await resp.json();

    const okCount = data.ok || 0;
    const failCount = data.fail || 0;
    const total = okCount + failCount;

    barFill.style.width = '100%';
    progText.textContent = '下载完成！' + okCount + ' 成功, ' + failCount + ' 失败';

    // 显示结果列表
    let html = '<div class="batch-list"><div class="batch-header">' +
      '<span class="batch-label">下载结果</span>' +
      '<span class="batch-summary">成功 ' + okCount + ' / 失败 ' + failCount + '</span>' +
      '</div>';

    if (data.save_dir) {
      html += '<div class="batch-savedir">保存目录: ' + escapeHtml(data.save_dir) + '</div>';
    }

    for (const r of (data.results || [])) {
      const cls = r.status === 'ok' ? 'dl-ok' : 'dl-fail';
      const status = r.status === 'ok' ? '✓' : '✗';
      const info = r.status === 'ok'
        ? ('大小: ' + formatSize(r.size))
        : (r.error || '未知错误');
      html += '<div class="batch-result-item ' + cls + '">' +
        '<span class="result-status">' + status + '</span>' +
        '<span class="result-id">' + r.aweme_id + '</span>' +
        '<span class="result-info">' + escapeHtml(info) + '</span>' +
        '</div>';
    }
    html += '</div>';
    resultsDiv.innerHTML = html;

    if (failCount === 0) {
      toast('全部下载成功！保存到 downloads 目录', 'success');
    } else {
      toast(okCount + ' 成功, ' + failCount + ' 失败', 'info');
    }

    // 清空待下载列表
    if (okCount === total) {
      batchState.awemeIds = [];
      btn.disabled = true;
    }
  } catch(e) {
    toast('下载失败: ' + e.message, 'error');
  }
  btn.disabled = false; btn.textContent = '批量下载';
}

function clearBatchList() {
  batchState = { awemeIds: [], results: [] };
  document.getElementById('batchResults').innerHTML = '';
  document.getElementById('btnDownBatch').disabled = true;
  document.getElementById('videoLinks').value = '';
  document.getElementById('batchProgress').style.display = 'none';
}

function formatSize(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}
