const $ = (id) => document.getElementById(id);
const form = $('brief-form');
const fields = ['topic', 'mode', 'stage', 'duration_seconds', 'aspect_ratio', 'quality', 'lyrics', 'language'];
const stageNames = { rooftop: '城市天台', studio: '录音棚', street: '街头', lobby: '大厅' };
let photoURL = null;
let serverPlan = null;
let quoteRequested = false;

function briefPayload() {
  const data = new FormData(form);
  return Object.fromEntries(fields.map((key) => {
    const value = data.get(key);
    return [key, key === 'duration_seconds' ? Number(value) : key === 'topic' ? String(value ?? '').trim() : String(value ?? '')];
  }));
}
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function message(id, text, error = false) {
  const node = $(id);
  node.textContent = text;
  node.hidden = !text;
  node.classList.toggle('error', error);
}
async function request(path, payload) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(path, { method: payload ? 'POST' : 'GET', headers: payload ? { 'Content-Type': 'application/json' } : {}, body: payload ? JSON.stringify(payload) : undefined, signal: controller.signal });
    const data = await response.json();
    if (!response.ok) throw new Error(`${data.error?.code || response.status}：${data.error?.message || '请求失败'}`);
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('请求超时，请稍后重试。');
    throw error;
  } finally { clearTimeout(timeout); }
}
async function busy(button, label, action) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = label;
  try { await action(); } finally { button.disabled = false; button.textContent = original; }
}
function validate() {
  const errors = [];
  if (!$('topic').value.trim()) errors.push(['topic', '请填写 1–240 字的 Rap 主题。']);
  if ($('topic').value.trim().length > 240) errors.push(['topic', '主题最多 240 字。']);
  if ($('lyrics').value.length > 4000) errors.push(['lyrics', '歌词最多 4000 字。']);
  for (const id of ['topic', 'lyrics']) {
    const error = errors.find(([field]) => field === id);
    $(id).setAttribute('aria-invalid', String(Boolean(error)));
    $(`${id}-error`).textContent = error?.[1] || '';
    $(`${id}-error`).hidden = !error;
  }
  const summary = $('validation-errors');
  summary.replaceChildren();
  summary.hidden = !errors.length;
  if (errors.length) {
    summary.append(element('strong', '请先完成以下内容：'));
    for (const [id, text] of errors) {
      const link = element('a', text);
      link.href = `#${id}`;
      link.addEventListener('click', () => $(id).focus());
      summary.append(link);
    }
    summary.focus();
  }
  return !errors.length;
}
function localStoryboard(brief) {
  const first = Math.max(2, Math.round(brief.duration_seconds / 4));
  const final = brief.duration_seconds - first;
  return [
    { time: `0–${first} 秒`, title: '开场 · 建立舞台', description: `以${stageNames[brief.stage]}建立环境，${brief.mode === 'duo' ? '两位主角同框亮相' : '主角面向镜头入场'}。` },
    { time: `${first}–${final} 秒`, title: '主段 · 表达主题', description: brief.lyrics ? `围绕主题安排${brief.mode === 'duo' ? '双人接词' : '单人表演'}，采用已填写歌词；节奏与音轨待制作。` : '围绕主题安排表演；歌词、节奏与音轨均待后续创作。' },
    { time: `${final}–${brief.duration_seconds} 秒`, title: '收尾 · 留下记忆点', description: '用一句主题呼应与定格构图收束，实际镜头及效果待制作确认。' },
  ];
}
function updatePreview() {
  const brief = briefPayload();
  $('topic-count').textContent = `${$('topic').value.length} / 240`;
  $('lyrics-count').textContent = `${$('lyrics').value.length} / 4000`;
  $('preview-topic').textContent = brief.topic || '填写主题，开始构思你的舞台。';
  $('preview-specs').replaceChildren(...[brief.mode === 'duo' ? '双人' : '单人', stageNames[brief.stage], `${brief.duration_seconds} 秒`, brief.aspect_ratio, brief.quality, brief.language === 'zh' ? '中文' : 'English'].map((text) => element('span', text)));
  $('storyboard').replaceChildren(...localStoryboard(brief).map((shot) => {
    const item = element('li');
    item.append(element('strong', `${shot.time} / ${shot.title}`), element('p', shot.description));
    return item;
  }));
}
function download(data, filename) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json;charset=utf-8' }));
  const anchor = element('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function displayValue(value) { return typeof value === 'object' && value !== null ? JSON.stringify(value, null, 2) : String(value ?? '未提供'); }
async function readSaved(id) {
  const data = await request(`/api/briefs/${encodeURIComponent(id)}`);
  if (!data.brief || !data.brief.id) throw new Error('服务端没有返回完整 brief。');
  return data.brief;
}
async function loadBrief(id, button) {
  await busy(button, '读取中…', async () => {
    try {
      const brief = await readSaved(id);
      for (const key of fields) {
        const control = form.elements.namedItem(key);
        control.value = String(brief[key] ?? '');
      }
      invalidateDerived();
      updatePreview();
      validate();
      message('save-status', `已回读保存记录 ${brief.id}。编辑后保存会创建新的 brief。`);
      $('topic').focus();
      $('topic').scrollIntoView({ block: 'center' });
    } catch (error) { message('list-status', `读取失败：${error.message} 请点击「打开」重试。`, true); }
  });
}
async function downloadSaved(id, button) {
  await busy(button, '读取中…', async () => {
    try { download(await readSaved(id), `rap-brief-${id}.json`); }
    catch (error) { message('list-status', `下载失败：${error.message} 请再次点击下载。`, true); }
  });
}
async function loadList() {
  await busy($('refresh-button'), '读取中…', async () => {
    message('list-status', '正在读取已保存 brief…');
    try {
      const data = await request('/api/briefs');
      if (!Array.isArray(data.briefs)) throw new Error('服务端返回的 brief 列表格式不正确。');
      $('saved-list').replaceChildren(...data.briefs.map((brief) => {
        const card = element('article', undefined, 'saved-card');
        const info = element('div');
        const date = new Date(brief.created_at);
        info.append(element('h3', brief.topic), element('p', `${Number.isNaN(date.getTime()) ? brief.created_at : date.toLocaleString('zh-CN')} · ${brief.duration_seconds} 秒 · ${brief.aspect_ratio} · ${brief.quality}`));
        const actions = element('div', undefined, 'saved-actions');
        const open = element('button', '打开', 'button secondary');
        open.type = 'button';
        open.setAttribute('aria-label', `打开 brief：${brief.topic}`);
        open.addEventListener('click', () => loadBrief(brief.id, open));
        const save = element('button', '下载 JSON', 'button quiet');
        save.type = 'button';
        save.setAttribute('aria-label', `下载 brief：${brief.topic}`);
        save.addEventListener('click', () => downloadSaved(brief.id, save));
        actions.append(open, save);
        card.append(info, actions);
        return card;
      }));
      message('list-status', data.briefs.length ? `已读取 ${data.briefs.length} 份 brief。` : '还没有保存的 brief。填写上方表单，保存第一份创作计划。');
    } catch (error) { message('list-status', `列表读取失败：${error.message} 请点击「刷新列表」重试。`, true); }
  });
}
function invalidateDerived() {
  serverPlan = null;
  $('server-storyboard').hidden = true;
  message('preview-status', '');
  if (quoteRequested) {
    $('quote-details').hidden = true;
    message('quote-status', '参数已变更，请重新查询价格参考；无报价不代表 0 元。');
  }
}
form.addEventListener('input', () => { invalidateDerived(); updatePreview(); });
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!validate()) return;
  const payload = briefPayload();
  await busy($('save-button'), '正在保存并回读…', async () => {
    message('save-status', '正在写入本地数据库…');
    let created;
    try {
      const response = await request('/api/briefs', payload);
      created = response.brief;
      if (!created?.id) throw new Error('服务端未返回 brief 编号。');
      const saved = await readSaved(created.id);
      message('save-status', `保存并回读成功 · ${saved.topic} · 编号 ${saved.id}。未进行 AI 视频生成。`);
    } catch (error) {
      message('save-status', created?.id ? `已保存 ${created.id}，但回读失败：${error.message} 请刷新列表后打开记录重试。` : `保存失败：${error.message} 表单已保留，请点击保存重试。`, true);
    }
    await loadList();
  });
});
$('refresh-button').addEventListener('click', loadList);
$('download-plan').addEventListener('click', () => {
  if (!validate()) return;
  download({ kind: 'brief_preview', is_generated_video: false, brief: briefPayload(), storyboard: serverPlan || localStoryboard(briefPayload()), source: serverPlan ? 'server_brief_preview' : 'local_planning' }, 'rap-storyboard.json');
});
$('preview-button').addEventListener('click', async () => {
  if (!validate()) return;
  const brief = briefPayload();
  await busy($('preview-button'), '请求分镜中…', async () => {
    message('preview-status', '正在请求服务端文字分镜规划…');
    try {
      const { job } = await request('/api/jobs', { mode: 'brief_preview', brief });
      if (job?.status !== 'completed' || job?.kind !== 'brief_preview' || job?.result?.is_generated_video !== false || !Array.isArray(job?.result?.storyboard)) throw new Error('服务端未返回约定的完整文字分镜。');
      if (JSON.stringify(briefPayload()) !== JSON.stringify(brief)) { message('preview-status', '参数已变更，请重新请求分镜。'); return; }
      serverPlan = job.result.storyboard;
      $('server-storyboard').replaceChildren(element('strong', '服务端分镜规划'), ...serverPlan.map((shot) => element('p', displayValue(shot))));
      $('server-storyboard').hidden = false;
      message('preview-status', '服务端分镜规划已完成。没有生成视频，可下载分镜 JSON。');
    } catch (error) { message('preview-status', `服务端分镜不可用：${error.message} 可继续查看本地文字规划，并点击此按钮重试。`, true); }
  });
});
$('quote-button').addEventListener('click', async () => {
  const { duration_seconds, quality, aspect_ratio } = briefPayload();
  const payload = { duration_seconds, quality, aspect_ratio };
  quoteRequested = true;
  await busy($('quote-button'), '查询中…', async () => {
    $('quote-details').hidden = true;
    message('quote-status', '正在查询来源支持的可比价格…');
    try {
      const { quote } = await request('/api/quote', payload);
      const current = briefPayload();
      if (Object.entries(payload).some(([key, value]) => current[key] !== value)) { message('quote-status', '参数已变更，请重新查询价格参考。'); return; }
      if (!quote || !Object.hasOwn(quote, 'estimate') || quote.is_vendor_quote !== false) throw new Error('服务端未返回约定的研究价格参考。');
      message('quote-status', quote.estimate === null ? '当前规格暂无可比报价，不代表 0 元。' : `参考估算：${displayValue(quote.estimate)} ${quote.currency || ''}。非供应商实时报价。`);
      const details = [['对比规格', `${duration_seconds} 秒 / ${quality} / ${aspect_ratio}`], ['价格依据', quote.basis], ['适用条件与限制', quote.assumptions]];
      $('quote-details').replaceChildren(...details.flatMap(([label, value]) => [element('dt', label), element('dd', displayValue(value))]));
      $('quote-details').hidden = false;
    } catch (error) { message('quote-status', `价格参考不可用：${error.message} 尚无报价，不代表 0 元。可点击查询重试。`, true); }
  });
});
function clearPhoto() {
  if (photoURL) URL.revokeObjectURL(photoURL);
  photoURL = null;
  $('photo-image').removeAttribute('src');
  $('photo-reference').hidden = true;
  $('photo').value = '';
}
$('photo').addEventListener('change', () => {
  const file = $('photo').files[0];
  if (photoURL) URL.revokeObjectURL(photoURL);
  photoURL = null;
  $('photo-reference').hidden = true;
  $('photo-error').hidden = true;
  if (!file) return;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) {
    $('photo-error').textContent = '请选择不超过 10 MB 的 JPEG、PNG 或 WebP 图片。';
    $('photo-error').hidden = false;
    $('photo').value = '';
    return;
  }
  photoURL = URL.createObjectURL(file);
  $('photo-image').src = photoURL;
  $('photo-reference').hidden = false;
});
$('photo-image').addEventListener('error', () => { clearPhoto(); $('photo-error').textContent = '此图片无法预览，请重新选择有效图片。'; $('photo-error').hidden = false; });
$('remove-photo').addEventListener('click', clearPhoto);
window.addEventListener('pagehide', () => { if (photoURL) URL.revokeObjectURL(photoURL); });
updatePreview();
loadList();
