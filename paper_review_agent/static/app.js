const state = {
  taskId: null,
  task: null,
  report: null,
  candidates: [],
  selected: new Set(),
  stream: null,
  pollTimer: null,
  analysisLoaded: false,
};

const $ = (selector) => document.querySelector(selector);
const views = { start: $('#start-view'), tasks: $('#tasks-view'), task: $('#task-view') };
const labels = {
  pending: '待执行', retrieving: '检索中', awaiting_confirmation: '等待文献确认',
  analyzing: '分析中', writing: '撰写中', validating: '校验中', completed: '已完成', failed: '已失败',
};
const agentLabels = {
  retrieval: '检索与证据整备', analysis: '单篇文献分析', comparison: '跨文献对比融合', writing: '结构化综述撰写',
};
const sourceLabels = { arxiv: 'arXiv', pubmed: 'PubMed', fixture: '受控示例', local: '本地论文' };
const scoreLabels = {
  topic_relevance: '主题相关性', coverage: '覆盖与完整性', classification_comparison: '分类与比较质量',
  citation_support: '事实与引用支持', structure_readability: '结构与可读性',
};

document.addEventListener('DOMContentLoaded', init);

function init() {
  bind();
  checkHealth();
  route();
  window.addEventListener('hashchange', route);
}

function bind() {
  $('#topic').addEventListener('input', (event) => {
    $('#topic-count').textContent = event.target.value.trim().length;
  });
  $('#task-form').addEventListener('submit', createTask);
  $('#refresh-tasks').addEventListener('click', loadTaskList);
  $('#refresh-tasks-page').addEventListener('click', loadTaskList);
  $('#candidate-list').addEventListener('change', onCandidateChange);
  document.querySelectorAll('input[name="sources"]').forEach((input) => {
    input.addEventListener('change', normalizeSourceSelection);
  });
  $('#confirm-button').addEventListener('click', confirmSelection);
  $('#retry-button').addEventListener('click', retryTask);
  $('#show-report-tab').addEventListener('click', () => switchReportTab('report'));
  $('#show-analysis-tab').addEventListener('click', () => switchReportTab('analysis'));
  $('#evaluation-form').addEventListener('submit', submitEvaluation);
  document.addEventListener('click', (event) => {
    const evidenceButton = event.target.closest('[data-evidence]');
    if (evidenceButton) openEvidence(evidenceButton.dataset.evidence);
    if (event.target.closest('[data-close-drawer]')) closeEvidence();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeEvidence();
  });
  buildScoreFields();
}

async function checkHealth() {
  const chip = $('#health-chip');
  try {
    const health = await api('/api/v1/health');
    chip.textContent = `${health.engine_mode === 'crewai' ? 'CrewAI' : 'Local'} · ${health.llm_mode}`;
    chip.classList.add('ok');
  } catch (error) {
    chip.textContent = '环境不可用';
    chip.classList.add('degraded');
  }
}

function route() {
  closeStream();
  const hash = window.location.hash || '#/';
  if (hash.startsWith('#/task/')) {
    state.taskId = decodeURIComponent(hash.slice('#/task/'.length));
    state.task = null;
    state.report = null;
    state.analysisLoaded = false;
    state.selected = new Set();
    showView('task');
    loadTask(state.taskId);
  } else if (hash === '#/tasks') {
    state.taskId = null;
    showView('tasks');
    loadTaskList();
  } else {
    state.taskId = null;
    showView('start');
    loadTaskList();
  }
}

function showView(name) {
  Object.entries(views).forEach(([key, element]) => element.classList.toggle('hidden', key !== name));
  $('#nav-home').classList.toggle('active', name === 'start');
  $('#nav-tasks').classList.toggle('active', name === 'tasks' || name === 'task');
}

async function createTask(event) {
  event.preventDefault();
  const errorBox = $('#form-error');
  errorBox.textContent = '';
  const sources = [...document.querySelectorAll('input[name="sources"]:checked')].map((item) => item.value);
  if (!sources.length) {
    errorBox.textContent = '至少选择一个学术数据源。';
    return;
  }
  const payload = {
    topic: $('#topic').value.trim(),
    year_start: Number($('#year-start').value),
    year_end: Number($('#year-end').value),
    candidate_limit: Number($('#candidate-limit').value),
    keywords: $('#keywords').value
      .split(/[,，]/)
      .map((value) => value.trim())
      .filter(Boolean),
    sources,
  };
  const submit = event.currentTarget.querySelector('button[type="submit"]');
  submit.disabled = true;
  try {
    const task = await api('/api/v1/tasks', { method: 'POST', body: JSON.stringify(payload) });
    showToast(
      sources.includes('local')
        ? '任务已创建，正在读取本地论文并建立全文证据'
        : '任务已创建，正在规划检索式并筛选候选文献'
    );
    window.location.hash = `#/task/${encodeURIComponent(task.task_id)}`;
  } catch (error) {
    errorBox.textContent = formatApiError(error);
  } finally {
    submit.disabled = false;
  }
}

async function loadTask(taskId) {
  try {
    const task = await api(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
    state.task = task;
    renderTask(task);
    subscribeTask(task);
    if (task.status === 'awaiting_confirmation') await loadCandidates(taskId);
    if (task.status === 'completed') await loadReport(taskId);
  } catch (error) {
    renderTaskError(error);
  }
}

function normalizeSourceSelection(event) {
  const changed = event.currentTarget;
  if (!changed.checked) return;
  const inputs = [...document.querySelectorAll('input[name="sources"]')];
  if (changed.value === 'local') {
    inputs.filter((input) => input !== changed).forEach((input) => { input.checked = false; });
  } else {
    const local = inputs.find((input) => input.value === 'local');
    if (local) local.checked = false;
  }
}

function renderTask(task) {
  $('#task-id-label').textContent = task.task_id;
  $('#task-topic').textContent = task.topic;
  $('#task-meta').innerHTML = `
    <span>${task.year_start}—${task.year_end}</span>
    <span>${escapeHtml((task.keywords || []).join(' / ') || '无附加关键词')}</span>
    <span>${task.sources.map((source) => sourceLabels[source] || source).join(' / ')}</span>
    <span>候选上限 ${task.candidate_limit}</span>
    <span>${task.source_mode === 'local' ? '本地论文模式' : task.source_mode === 'demo' ? '受控语料模式' : task.source_mode === 'mixed' ? '混合来源' : '实时检索模式'}</span>
  `;
  $('#task-status').textContent = labels[task.status] || task.status;
  $('#task-progress').style.width = `${task.progress || 0}%`;
  $('#task-updated').textContent = `更新于 ${formatDate(task.updated_at)}`;
  const errorBox = $('#task-error');
  if (task.error_message) {
    errorBox.classList.remove('hidden');
    errorBox.innerHTML = `<strong>${escapeHtml(task.error_stage || '任务失败')}</strong><br>${escapeHtml(task.error_message)}`;
  } else {
    errorBox.classList.add('hidden');
    errorBox.innerHTML = '';
  }
  renderWarnings(task.warnings || []);
  renderAgents(task.agents || []);
  toggleTaskSections(task);
}

function renderAgents(agents) {
  const container = $('#agent-timeline');
  const statusText = { pending: '待执行', running: '执行中', succeeded: '已成功', failed: '已失败' };
  container.innerHTML = agents.map((agent, index) => `
    <li class="agent-step ${agent.status}">
      <span class="agent-dot">${agent.status === 'succeeded' ? '✓' : index + 1}</span>
      <div><strong>${escapeHtml(agentLabels[agent.role] || agent.role)}</strong><p>${escapeHtml(statusText[agent.status] || agent.status)}${agent.output_ref ? ` · ${escapeHtml(agent.output_ref)}` : ''}</p></div>
    </li>
  `).join('');
}

function renderWarnings(warnings) {
  $('#task-warnings').innerHTML = warnings.map((warning) => `<div class="warning-item">${escapeHtml(warning)}</div>`).join('');
}

function toggleTaskSections(task) {
  const generation = $('#generation-section');
  $('#candidate-section').classList.toggle('hidden', task.status !== 'awaiting_confirmation');
  generation.classList.toggle('hidden', !['pending', 'retrieving', 'analyzing', 'writing', 'validating'].includes(task.status));
  $('#report-section').classList.toggle('hidden', task.status !== 'completed');
  $('#evaluation-section').classList.toggle('hidden', task.status !== 'completed');
  $('#failed-section').classList.toggle('hidden', task.status !== 'failed');
  if (task.status === 'failed') $('#failed-message').textContent = task.error_message || '任务未完成，请联系管理员查看日志。';
  if (!generation.classList.contains('hidden')) {
    const latest = (task.events || []).slice(-1)[0];
    $('#generation-title').textContent = `${labels[task.status] || task.status} · ${task.progress || 0}%`;
    $('#generation-message').textContent = latest ? latest.message : '状态与阶段变化会实时更新。';
  }
}

async function loadCandidates(taskId) {
  try {
    const data = await api(`/api/v1/tasks/${encodeURIComponent(taskId)}/candidates`);
    state.candidates = data.candidates || [];
    state.selected = new Set();
    renderCandidates(data);
  } catch (error) {
    showToast(formatApiError(error), true);
  }
}

function renderCandidates(data) {
  state.candidates = data.candidates || [];
  const localMode = data.source_mode === 'local';
  if (localMode) {
    state.selected = new Set(
      state.candidates.filter((paper) => paper.has_evidence).map((paper) => paper.paper_id)
    );
  }
  renderSearchPlan(data);
  $('#candidate-intro').textContent = localMode
    ? '候选来自本地论文文件夹，系统已提取全文证据并默认全选。取消不需要的论文后即可开始生成。'
    : '候选来自模型规划的多条检索式，并经过逐篇相关性筛选。仅选择具备可定位摘要或全文证据的文献；确认后选择快照固定。';
  $('#candidate-count').textContent = `${state.candidates.length} 篇`;
  $('#candidate-list').innerHTML = state.candidates.map((paper) => {
    const checked = localMode && paper.has_evidence ? 'checked' : '';
    const relevance = Number.isFinite(paper.llm_relevance_score) ? paper.llm_relevance_score : null;
    const decision = paper.llm_decision;
    const decisionLabel = { include: '建议纳入', borderline: '边界候选', exclude: '建议排除' }[decision] || '';
    const matched = (paper.matched_keywords || []).map((item) => `<span class="badge keyword">${escapeHtml(item)}</span>`).join('');
    return `
      <article class="candidate-card">
        <input type="checkbox" data-paper-id="${escapeAttr(paper.paper_id)}" ${checked} ${paper.has_evidence ? '' : 'disabled'}>
        <div>
          <h3>${escapeHtml(paper.title)}</h3>
          <div class="candidate-meta">
            <span class="badge">${paper.year}</span>
            ${(paper.source_records || []).map((record) => `<span class="badge source">${escapeHtml(sourceLabels[record.source] || record.source)}</span>`).join('')}
            <span class="badge">${paper.evidence_scope === 'fulltext' ? '全文证据' : '摘要证据'} · ${paper.evidence_count || 0} 段</span>
            ${relevance !== null ? `<span class="badge relevance ${decision || ''}">相关性 ${relevance}/100</span>` : ''}
            ${decisionLabel ? `<span class="badge decision ${decision}">${decisionLabel}</span>` : ''}
            ${paper.is_fixture ? '<span class="badge warning">受控示例</span>' : ''}
            ${paper.suspected_duplicate ? '<span class="badge warning">疑似重复</span>' : ''}
            ${matched}
          </div>
          ${paper.llm_reason ? `<p class="screening-reason"><strong>筛选理由：</strong>${escapeHtml(paper.llm_reason)}</p>` : ''}
          <p>${escapeHtml((paper.abstract || '该文献暂无可用摘要。').slice(0, 360))}${(paper.abstract || '').length > 360 ? '…' : ''}</p>
          ${paper.url ? `<a class="candidate-link" href="${escapeAttr(paper.url)}" target="_blank" rel="noreferrer">查看文献来源 ↗</a>` : ''}
        </div>
      </article>
    `;
  }).join('') || `<div class="empty-state">${localMode ? '本地文件夹中没有可用论文。' : '模型筛选后没有合适候选文献。'}</div>`;
  updateSelectedSummary();
}

function renderSearchPlan(data) {
  const panel = $('#search-plan-panel');
  const plan = data.search_plan;
  if (!plan && data.source_mode !== 'local') {
    panel.classList.add('hidden');
    return;
  }
  panel.classList.remove('hidden');
  const localMode = data.source_mode === 'local';
  const badge = $('#screening-mode-badge');
  $('#search-plan-heading-label').textContent = localMode ? '本地论文模式' : '本次检索策略';
  if (localMode) {
    badge.textContent = '无需联网 · 全文解析';
    badge.className = 'badge llm';
    $('#search-plan-rationale').textContent = '系统直接读取 local_papers/inbox/ 中的论文文件，建立带页码定位的全文证据，不调用 arXiv、PubMed 或检索模型。';
    $('#search-plan-queries').innerHTML = '';
    return;
  }
  const isLlm = data.screening_mode === 'llm';
  badge.textContent = isLlm ? '模型规划 + 模型筛选' : '规则回退';
  badge.className = `badge ${isLlm ? 'llm' : 'warning'}`;
  $('#search-plan-rationale').textContent = plan.rationale || '未提供检索策略说明。';
  $('#search-plan-queries').innerHTML = (plan.queries || [])
    .map((query) => `<li>${escapeHtml(query)}</li>`)
    .join('');
}

function onCandidateChange(event) {
  if (event.target.matches('input[data-paper-id]')) {
    const paperId = event.target.dataset.paperId;
    if (event.target.checked) state.selected.add(paperId); else state.selected.delete(paperId);
    updateSelectedSummary();
  }
}

function updateSelectedSummary() {
  $('#selected-summary').textContent = `已选择 ${state.selected.size} 篇`;
  $('#confirm-button').disabled = state.selected.size === 0;
}

async function confirmSelection() {
  if (!state.taskId || !state.selected.size) return;
  const button = $('#confirm-button');
  button.disabled = true;
  button.textContent = '正在固定选择…';
  try {
    const task = await api(`/api/v1/tasks/${encodeURIComponent(state.taskId)}/confirm`, {
      method: 'POST', body: JSON.stringify({ paper_ids: [...state.selected] }),
    });
    state.task = task;
    renderTask(task);
    subscribeTask(task);
    showToast('文献选择已固定，开始生成综述');
  } catch (error) {
    button.disabled = false;
    button.textContent = '开始生成综述';
    showToast(formatApiError(error), true);
  }
}

async function loadReport(taskId) {
  try {
    const report = await api(`/api/v1/tasks/${encodeURIComponent(taskId)}/report`);
    state.report = report;
    renderReport(report);
    await loadEvaluations(report.report_id);
    if (!state.analysisLoaded) await loadAnalysis(taskId);
  } catch (error) {
    showToast(formatApiError(error), true);
  }
}

function renderReport(report) {
  $('#report-title').textContent = report.title;
  $('#report-coverage').textContent = `参考文献 ${report.references.length} 篇 · 证据片段 ${Object.keys(report.evidence || {}).length} 条`;
  const sectionMarkup = (report.sections || []).map((section) => `
    <article class="report-section-card">
      <h3>${escapeHtml(section.title)} <span>${section.claims.length} CLAIMS</span></h3>
      ${section.claims.map((claim) => renderClaim(claim)).join('')}
    </article>
  `).join('');
  const notes = [...(report.coverage_notes || []), ...(report.warnings || [])];
  const references = (report.references || []).map((reference) => `
    <div class="reference-item">
      <span class="reference-index">[${reference.index}]</span>
      <div><strong>${escapeHtml(reference.title)}</strong><p>${escapeHtml(reference.authors.join(', '))} · ${reference.year} · ${escapeHtml(reference.sources.map((source) => sourceLabels[source] || source).join(', '))}</p></div>
    </div>
  `).join('');
  $('#report-content').innerHTML = `${sectionMarkup}
    ${notes.length ? `<div class="report-notes"><h3>覆盖范围与限制</h3><ul>${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join('')}</ul></div>` : ''}
    <div class="references"><h3>参考文献</h3>${references || '<p class="muted">暂无参考文献。</p>'}</div>`;
}

function renderClaim(claim) {
  const citations = (claim.evidence_ids || []).map((evidenceId) => {
    const evidence = state.report?.evidence?.[evidenceId];
    const number = evidence ? evidence.paper.index : '?';
    return `<button class="citation" type="button" data-evidence="${escapeAttr(evidenceId)}">[${number}]</button>`;
  }).join('');
  return `<p class="claim ${claim.kind === 'limitation' ? 'limitation' : ''}">${escapeHtml(claim.text)}${citations}</p>`;
}

async function loadAnalysis(taskId) {
  try {
    const data = await api(`/api/v1/tasks/${encodeURIComponent(taskId)}/analysis`);
    state.analysisLoaded = true;
    const paperCards = (data.analysis?.papers || []).map((paper) => `
      <div class="analysis-card"><h3>${escapeHtml(paper.title)}</h3><dl>
        <dt>方法</dt><dd>${escapeHtml(paper.methods.join('；'))}</dd>
        <dt>实验设计</dt><dd>${escapeHtml(paper.experimental_design)}</dd>
        <dt>创新点</dt><dd>${escapeHtml(paper.innovations.join('；'))}</dd>
        <dt>局限</dt><dd>${escapeHtml(paper.limitations.join('；'))}</dd>
        <dt>证据范围</dt><dd>${paper.evidence_scope === 'fulltext' ? '全文' : '摘要'}</dd>
      </dl></div>
    `).join('');
    const comparison = data.comparison || {};
    const comparisonMarkup = `
      <div class="comparison-block"><h3>跨文献融合</h3>
        <p><strong>类别：</strong>${escapeHtml((comparison.categories || []).join('、'))}</p>
        <p><strong>共同点：</strong>${escapeHtml((comparison.similarities || []).map((item) => item.text).join('；'))}</p>
        <p><strong>演进：</strong>${escapeHtml((comparison.evolution || []).map((item) => item.text).join('；'))}</p>
        <p><strong>未解决问题：</strong>${escapeHtml((comparison.open_questions || []).map((item) => item.text).join('；'))}</p>
      </div>`;
    $('#analysis-content').innerHTML = `<div class="analysis-grid">${paperCards}${comparisonMarkup}</div>`;
  } catch (error) {
    $('#analysis-content').innerHTML = '<div class="empty-state">分析结果尚未生成。</div>';
  }
}

function switchReportTab(tab) {
  $('#show-report-tab').classList.toggle('active', tab === 'report');
  $('#show-analysis-tab').classList.toggle('active', tab === 'analysis');
  $('#report-content').classList.toggle('hidden', tab !== 'report');
  $('#analysis-content').classList.toggle('hidden', tab !== 'analysis');
}

function openEvidence(evidenceId) {
  const evidence = state.report?.evidence?.[evidenceId];
  if (!evidence) return;
  $('#evidence-quote').textContent = evidence.quote;
  $('#evidence-locator').textContent = evidence.locator;
  $('#evidence-scope').textContent = evidence.scope === 'fulltext' ? '全文片段' : '摘要片段';
  $('#evidence-paper').textContent = `${evidence.paper.title}（${evidence.paper.year}）`;
  $('#evidence-source').textContent = (evidence.paper.sources || []).join(', ');
  const link = $('#evidence-link');
  if (evidence.paper.url) {
    link.href = evidence.paper.url;
    link.classList.remove('hidden');
  } else {
    link.classList.add('hidden');
    link.removeAttribute('href');
  }
  $('#evidence-drawer').classList.add('open');
  $('#evidence-drawer').setAttribute('aria-hidden', 'false');
}

function closeEvidence() {
  $('#evidence-drawer').classList.remove('open');
  $('#evidence-drawer').setAttribute('aria-hidden', 'true');
}

function buildScoreFields() {
  $('#score-fields').innerHTML = Object.entries(scoreLabels).map(([key, label]) => `
    <label class="score-item"><span>${label}</span><select data-score="${key}" required>${[5,4,3,2,1].map((value) => `<option value="${value}" ${value === 4 ? 'selected' : ''}>${value} 分</option>`).join('')}</select></label>
  `).join('');
}

async function submitEvaluation(event) {
  event.preventDefault();
  const message = $('#evaluation-message');
  message.textContent = '';
  if (!state.report) return;
  const scores = {};
  document.querySelectorAll('[data-score]').forEach((select) => { scores[select.dataset.score] = Number(select.value); });
  try {
    await api(`/api/v1/reports/${encodeURIComponent(state.report.report_id)}/evaluations`, {
      method: 'POST',
      body: JSON.stringify({ reviewer_id: $('#reviewer-id').value.trim(), scale_version: 'v1.0', scores, comments: $('#review-comments').value.trim() }),
    });
    message.textContent = '评价已保存。';
    $('#review-comments').value = '';
    await loadEvaluations(state.report.report_id);
  } catch (error) {
    message.textContent = formatApiError(error);
  }
}

async function loadEvaluations(reportId) {
  try {
    const evaluations = await api(`/api/v1/reports/${encodeURIComponent(reportId)}/evaluations`);
    $('#evaluation-list').innerHTML = evaluations.map((item) => `
      <div class="eval-card"><strong>${escapeHtml(item.reviewer_id)}</strong> · ${escapeHtml(item.scale_version)} · ${formatDate(item.created_at)}
        <p>${Object.entries(item.scores).map(([key, value]) => `${escapeHtml(scoreLabels[key] || key)} ${value}`).join(' / ')}</p>
        ${item.comments ? `<p>${escapeHtml(item.comments)}</p>` : ''}
      </div>
    `).join('');
  } catch (error) {
    $('#evaluation-list').innerHTML = '';
  }
}

async function loadTaskList() {
  const containers = [$('#task-list'), $('#task-list-page')];
  try {
    const tasks = await api('/api/v1/tasks');
    if (!tasks.length) {
      containers.forEach((element) => { element.className = 'task-list empty-state'; element.innerHTML = '暂无任务记录。'; });
      return;
    }
    const markup = tasks.map((task) => `
      <a class="task-card" href="#/task/${encodeURIComponent(task.task_id)}">
        <span class="task-pill ${task.status}">${labels[task.status] || task.status}</span>
        <h3>${escapeHtml(task.topic)}</h3>
        <p>${task.year_start}—${task.year_end} · ${escapeHtml(task.sources.map((source) => sourceLabels[source] || source).join(' / '))} · ${formatDate(task.created_at)}</p>
        <div class="task-card-footer"><span class="muted">${task.progress || 0}%</span><span>查看详情 →</span></div>
      </a>
    `).join('');
    containers.forEach((element) => { element.className = 'task-list'; element.innerHTML = markup; });
  } catch (error) {
    containers.forEach((element) => { element.className = 'task-list empty-state'; element.textContent = formatApiError(error); });
  }
}

function subscribeTask(task) {
  closeStream();
  if (!task || ['completed', 'failed'].includes(task.status)) return;
  if (window.EventSource) {
    state.stream = new EventSource(`/api/v1/tasks/${encodeURIComponent(task.task_id)}/events`);
    state.stream.addEventListener('task', (event) => {
      try {
        const next = JSON.parse(event.data);
        state.task = next;
        renderTask(next);
        if (next.status === 'awaiting_confirmation') loadCandidates(next.task_id);
        if (next.status === 'completed') { closeStream(); loadReport(next.task_id); }
        if (next.status === 'failed') closeStream();
      } catch (error) {
        startPolling(task.task_id);
      }
    });
    state.stream.onerror = () => { closeStream(); startPolling(task.task_id); };
  } else {
    startPolling(task.task_id);
  }
}

function startPolling(taskId) {
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    try {
      const task = await api(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
      state.task = task;
      renderTask(task);
      if (task.status === 'awaiting_confirmation') await loadCandidates(task.task_id);
      if (task.status === 'completed') { clearInterval(state.pollTimer); await loadReport(task.task_id); }
      if (task.status === 'failed') clearInterval(state.pollTimer);
    } catch (error) {
      clearInterval(state.pollTimer);
      showToast(formatApiError(error), true);
    }
  }, 1600);
}

function closeStream() {
  if (state.stream) { state.stream.close(); state.stream = null; }
  clearInterval(state.pollTimer);
  state.pollTimer = null;
}

async function retryTask() {
  if (!state.task) return;
  const button = $('#retry-button');
  button.disabled = true;
  try {
    const task = await api(`/api/v1/tasks/${encodeURIComponent(state.task.task_id)}/retry`, { method: 'POST' });
    showToast('已创建关联重试任务');
    window.location.hash = `#/task/${encodeURIComponent(task.task_id)}`;
  } catch (error) {
    button.disabled = false;
    showToast(formatApiError(error), true);
  }
}

function renderTaskError(error) {
  $('#task-topic').textContent = '任务不可用';
  $('#task-status').textContent = '错误';
  $('#task-error').classList.remove('hidden');
  $('#task-error').textContent = formatApiError(error);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.message || payload.detail || `HTTP ${response.status}`);
    error.payload = payload;
    throw error;
  }
  return payload;
}

function formatApiError(error) {
  const fields = error.payload?.fields;
  if (fields && Object.keys(fields).length) {
    return `${error.message}\n${Object.entries(fields).map(([key, value]) => `${key}: ${value}`).join('；')}`;
  }
  return error.message || '请求失败';
}

function showToast(message, isError = false) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.toggle('error', isError);
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 3200);
}

function formatDate(value) {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
  } catch {
    return value;
  }
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, '&#096;');
}

