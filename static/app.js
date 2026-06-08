const state = {
  sessionId: null,
  stage: null,
  finalPackage: null,
  markdown: "",
  activeTab: "summary",
  deleteMode: false,
  selectedSessionIds: new Set(),
};

const els = {
  runtimeStatus: document.querySelector("#runtimeStatus"),
  startForm: document.querySelector("#startForm"),
  answerForm: document.querySelector("#answerForm"),
  answerInput: document.querySelector("#answerInput"),
  submitAnswer: document.querySelector("#submitAnswer"),
  finalizeBtn: document.querySelector("#finalizeBtn"),
  chatLog: document.querySelector("#chatLog"),
  stageStrip: document.querySelector("#stageStrip"),
  stageStatus: document.querySelector("#stageStatus"),
  questionSource: document.querySelector("#questionSource"),
  roundStatus: document.querySelector("#roundStatus"),
  sessionList: document.querySelector("#sessionList"),
  refreshSessions: document.querySelector("#refreshSessions"),
  selectDeleteBtn: document.querySelector("#selectDeleteBtn"),
  cancelDeleteBtn: document.querySelector("#cancelDeleteBtn"),
  deleteAllBtn: document.querySelector("#deleteAllBtn"),
  deleteHint: document.querySelector("#deleteHint"),
  progressLog: document.querySelector("#progressLog"),
  resultTabs: document.querySelector("#resultTabs"),
  resultView: document.querySelector("#resultView"),
  copyMarkdown: document.querySelector("#copyMarkdown"),
};

const stageLabels = {
  overview: "项目定位",
  role: "个人职责",
  technical: "技术难点",
  impact: "结果量化",
  finalizing: "生成中",
  done: "完成",
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function addMessage(role, name, body) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.innerHTML = `
    <div class="message-name">${escapeHtml(name)}</div>
    <div class="message-body">${escapeHtml(body).replace(/\n/g, "<br>")}</div>
  `;
  els.chatLog.appendChild(node);
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function setStage(stage) {
  state.stage = stage;
  [...els.stageStrip.children].forEach((item) => {
    item.classList.toggle("active", item.dataset.stage === stage);
  });
}

function updateQuestionMeta({ stage, questionSource, stageRound, maxStageRounds, readyToFinalize }) {
  const label = stageLabels[stage] || "等待";
  els.stageStatus.textContent = readyToFinalize ? "信息收集完成，可以生成报告" : label;
  els.questionSource.textContent = `来源：${sourceLabel(questionSource)}`;
  if (stage === "finalizing" || stage === "done") {
    els.roundStatus.textContent = "完成";
  } else {
    els.roundStatus.textContent = `${stageRound || 0}/${maxStageRounds || 4}`;
  }
}

function applyAgentResponse(data) {
  state.sessionId = data.session_id;
  setStage(data.stage);
  updateQuestionMeta({
    stage: data.stage,
    questionSource: data.question_source,
    stageRound: data.stage_round,
    maxStageRounds: data.max_stage_rounds,
    readyToFinalize: data.ready_to_finalize,
  });
  if (data.message) addMessage("assistant", "工作流", data.message);
  if (data.stage_complete_reason) addProgress(`阶段判断：${data.stage_complete_reason}`);
  if (data.question) {
    const name = `项目追问Agent · ${sourceLabel(data.question_source)} · ${data.stage_round}/${data.max_stage_rounds}`;
    addMessage("assistant", name, data.question);
  }
  els.answerInput.disabled = !data.question;
  els.submitAnswer.disabled = !data.question;
  els.finalizeBtn.disabled = !data.ready_to_finalize;
  if (data.question) {
    els.answerInput.value = "";
    els.answerInput.focus();
  }
  if (data.final_package) {
    state.finalPackage = data.final_package;
    renderPackage();
  }
}

function addProgress(message) {
  const item = document.createElement("div");
  item.className = "progress-item";
  item.textContent = message;
  els.progressLog.appendChild(item);
  els.progressLog.scrollTop = els.progressLog.scrollHeight;
}

async function startSession(event) {
  event.preventDefault();
  els.chatLog.innerHTML = "";
  els.progressLog.innerHTML = "";
  state.finalPackage = null;
  state.markdown = "";
  renderEmptyResult();

  const payload = {
    project_name: document.querySelector("#projectName").value.trim(),
    target_role: document.querySelector("#targetRole").value.trim(),
    tech_stack: document.querySelector("#techStack").value.trim(),
    rough_description: document.querySelector("#roughDescription").value.trim(),
  };
  addMessage("user", "你", `创建项目：${payload.project_name}\n${payload.rough_description}`);
  const data = await api("/api/session/start", { method: "POST", body: JSON.stringify(payload) });
  applyAgentResponse(data);
  await loadSessions();
}

async function submitAnswer(event) {
  event.preventDefault();
  const answer = els.answerInput.value.trim();
  if (!answer || !state.sessionId) return;
  addMessage("user", "你", answer);
  els.answerInput.value = "";
  els.submitAnswer.disabled = true;
  const data = await api("/api/session/submit", {
    method: "POST",
    body: JSON.stringify({ session_id: state.sessionId, answer }),
  });
  applyAgentResponse(data);
  await loadSessions();
}

async function finalize() {
  if (!state.sessionId) return;
  els.finalizeBtn.disabled = true;
  els.answerInput.disabled = true;
  els.submitAnswer.disabled = true;
  els.progressLog.innerHTML = "";
  state.markdown = "";
  renderEmptyResult("正在生成...");

  const response = await fetch(`/api/session/${state.sessionId}/finalize/stream`, { method: "POST" });
  if (!response.ok || !response.body) {
    throw new Error(await response.text());
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) handleSse(part);
  }
  await loadSessions();
}

function handleSse(raw) {
  const lines = raw.split("\n");
  const event = (lines.find((line) => line.startsWith("event:")) || "event: message").slice(6).trim();
  const dataLine = lines.find((line) => line.startsWith("data:"));
  if (!dataLine) return;
  const data = JSON.parse(dataLine.slice(5));

  if (event === "progress") addProgress(data.message);
  if (event === "chunk") {
    state.markdown += data.content;
    els.resultView.classList.remove("empty");
    els.resultView.textContent = state.markdown;
  }
  if (event === "done") {
    state.finalPackage = data.final_package;
    setStage("done");
    updateQuestionMeta({
      stage: "done",
      questionSource: "unknown",
      stageRound: 0,
      maxStageRounds: 4,
      readyToFinalize: false,
    });
    renderPackage();
    addProgress("生成完成。");
  }
  if (event === "error") {
    addProgress(`生成失败：${data.message}`);
  }
}

async function loadSessions() {
  const data = await api("/api/session/list");
  renderSessionList(data.sessions || []);
}

function renderSessionList(sessions) {
  els.sessionList.innerHTML = "";
  if (!sessions.length) {
    const empty = document.createElement("div");
    empty.className = "session-empty";
    empty.textContent = "暂无历史会话";
    els.sessionList.appendChild(empty);
    return;
  }

  sessions.forEach((session) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "session-item";
    item.classList.toggle("selected", state.selectedSessionIds.has(session.session_id));
    item.innerHTML = `
      <span class="session-check" aria-hidden="true">${state.selectedSessionIds.has(session.session_id) ? "✓" : ""}</span>
      <strong>${escapeHtml(session.project_name || session.session_id)}</strong>
      <span>${escapeHtml(session.target_role || "")}</span>
      <span>${escapeHtml(stageLabels[session.stage] || session.stage || "")} · ${escapeHtml(session.updated_at || "")}</span>
    `;
    item.addEventListener("click", () => {
      if (state.deleteMode) {
        toggleSessionSelection(session.session_id);
        return;
      }
      loadSession(session.session_id).catch(showError);
    });
    els.sessionList.appendChild(item);
  });
}

async function loadSession(sessionId) {
  const session = await api(`/api/session/${sessionId}`);
  state.sessionId = session.session_id;
  setStage(session.current_stage);
  els.chatLog.innerHTML = "";
  els.progressLog.innerHTML = "";
  addMessage("assistant", "会话", `已载入：${session.project_name}`);
  session.rounds.forEach((record) => {
    addMessage("assistant", `项目追问Agent · ${sourceLabel(record.question_source)}`, record.question);
    addMessage("user", "你", record.answer);
  });
  const currentRound = countStageRounds(session, session.current_stage) + (session.current_question ? 1 : 0);
  updateQuestionMeta({
    stage: session.current_stage,
    questionSource: session.current_question_source,
    stageRound: currentRound,
    maxStageRounds: 4,
    readyToFinalize: session.current_stage === "finalizing",
  });
  if (session.current_question) {
    addMessage(
      "assistant",
      `项目追问Agent · ${sourceLabel(session.current_question_source)} · ${currentRound}/4`,
      session.current_question,
    );
  }
  els.answerInput.disabled = !session.current_question;
  els.submitAnswer.disabled = !session.current_question;
  els.finalizeBtn.disabled = session.current_stage !== "finalizing";
  if (session.final_package) {
    state.finalPackage = session.final_package;
    renderPackage();
  } else {
    state.finalPackage = null;
    renderEmptyResult();
  }
}

function toggleDeleteMode() {
  if (state.deleteMode) {
    confirmSelectedDelete().catch(showError);
    return;
  }
  state.deleteMode = true;
  state.selectedSessionIds.clear();
  renderDeleteMode();
  loadSessions().catch(showError);
}

function cancelDeleteMode() {
  state.deleteMode = false;
  state.selectedSessionIds.clear();
  renderDeleteMode();
  loadSessions().catch(showError);
}

function renderDeleteMode() {
  document.body.classList.toggle("delete-mode", state.deleteMode);
  els.selectDeleteBtn.textContent = state.deleteMode ? "确认删除" : "指定删除";
  els.selectDeleteBtn.classList.toggle("danger", state.deleteMode);
  els.cancelDeleteBtn.hidden = !state.deleteMode;
  els.deleteHint.hidden = !state.deleteMode;
}

function toggleSessionSelection(sessionId) {
  if (state.selectedSessionIds.has(sessionId)) {
    state.selectedSessionIds.delete(sessionId);
  } else {
    state.selectedSessionIds.add(sessionId);
  }
  loadSessions().catch(showError);
}

async function confirmSelectedDelete() {
  if (!state.selectedSessionIds.size) {
    addProgress("请先选择要删除的会话。");
    return;
  }
  const ids = [...state.selectedSessionIds];
  await Promise.all(ids.map((sessionId) => api(`/api/session/${sessionId}`, { method: "DELETE" })));
  if (state.sessionId && state.selectedSessionIds.has(state.sessionId)) {
    clearCurrentSession();
  }
  addProgress(`已删除 ${ids.length} 个会话。`);
  cancelDeleteMode();
}

async function deleteAllSessions() {
  const ok = window.confirm("确定删除全部历史会话吗？这个操作不能撤销。");
  if (!ok) return;
  const result = await api("/api/session/all", { method: "DELETE" });
  clearCurrentSession();
  state.deleteMode = false;
  state.selectedSessionIds.clear();
  renderDeleteMode();
  await loadSessions();
  addProgress(`已删除 ${result.deleted || 0} 个会话。`);
}

function clearCurrentSession() {
  state.sessionId = null;
  state.stage = null;
  state.finalPackage = null;
  state.markdown = "";
  setStage("");
  updateQuestionMeta({
    stage: "",
    questionSource: "unknown",
    stageRound: 0,
    maxStageRounds: 4,
    readyToFinalize: false,
  });
  els.chatLog.innerHTML = "";
  addMessage("assistant", "项目追问Agent", "等待项目材料。");
  els.answerInput.value = "";
  els.answerInput.disabled = true;
  els.submitAnswer.disabled = true;
  els.finalizeBtn.disabled = true;
  renderEmptyResult();
}

function countStageRounds(session, stage) {
  return (session.rounds || []).filter((record) => record.stage === stage).length;
}

function renderPackage() {
  if (!state.finalPackage) return;
  els.resultTabs.hidden = false;
  els.copyMarkdown.disabled = false;
  renderActiveTab();
}

function renderActiveTab() {
  const p = state.finalPackage;
  if (!p) return;
  [...els.resultTabs.querySelectorAll("button")].forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === state.activeTab);
  });
  els.resultView.classList.remove("empty");

  if (state.activeTab === "summary") {
    els.resultView.innerHTML = `
      <h3>项目定位</h3><p>${escapeHtml(p.positioning)}</p>
      <h3>简历项目简介</h3><p>${escapeHtml(p.resume_summary)}</p>
      <h3>简历 Bullet</h3>
      <ul>${p.resume_bullets.map((b) => `<li>${escapeHtml(b.text)}<br><small>${escapeHtml(b.focus)}：${escapeHtml(b.why_it_works)}</small></li>`).join("")}</ul>
      <h3>仍需补充</h3>
      <ul>${listItems(p.missing_info.length ? p.missing_info : ["暂无明显缺失"])}</ul>
    `;
  }
  if (state.activeTab === "tech") {
    els.resultView.innerHTML = `
      <h3>技术亮点</h3><ul>${listItems(p.technical_highlights)}</ul>
      <h3>架构与流程</h3><ul>${listItems(p.architecture_points)}</ul>
      <h3>结果与价值</h3><ul>${listItems(p.quantified_results)}</ul>
    `;
  }
  if (state.activeTab === "interview") {
    els.resultView.innerHTML = `
      <h3>面试追问</h3>
      <ul>${p.interview_questions.map((q) => `<li><strong>${escapeHtml(q.question)}</strong><br>${escapeHtml(q.answer_strategy)}</li>`).join("")}</ul>
      <h3>下一步</h3><ul>${listItems(p.next_actions)}</ul>
    `;
  }
  if (state.activeTab === "score") {
    const s = p.score_card;
    els.resultView.innerHTML = `
      <div class="score-grid">
        ${scoreTile("清晰度", s.clarity)}
        ${scoreTile("技术深度", s.technical_depth)}
        ${scoreTile("业务价值", s.business_impact)}
        ${scoreTile("面试准备", s.interview_readiness)}
      </div>
      <h3>审稿意见</h3><ul>${listItems(s.notes)}</ul>
      <h3>反思记录</h3><ul>${listItems(p.reflection_notes.length ? p.reflection_notes : ["离线演示或未返回反思记录"])}</ul>
    `;
  }
}

function scoreTile(label, value) {
  return `<div class="score-tile"><span>${escapeHtml(label)}</span><br><strong>${value}</strong><span>/10</span></div>`;
}

function listItems(items) {
  return items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("");
}

function renderEmptyResult(text = "生成后会显示结构化结果。") {
  els.resultTabs.hidden = true;
  els.copyMarkdown.disabled = true;
  els.resultView.className = "result-view empty";
  els.resultView.textContent = text;
}

function buildMarkdown(packageData) {
  const bullets = packageData.resume_bullets.map((b) => `- ${b.text}`).join("\n");
  const highlights = packageData.technical_highlights.map((x) => `- ${x}`).join("\n");
  const architecture = packageData.architecture_points.map((x) => `- ${x}`).join("\n");
  const results = packageData.quantified_results.map((x) => `- ${x}`).join("\n");
  const questions = packageData.interview_questions.map((q) => `- ${q.question}\n  回答思路：${q.answer_strategy}`).join("\n");
  return `# ${packageData.project_name}

## 项目定位
${packageData.positioning}

## 简历项目简介
${packageData.resume_summary}

## 简历 Bullet
${bullets}

## 技术亮点
${highlights}

## 架构与流程
${architecture}

## 结果与价值
${results}

## 面试追问
${questions}
`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function sourceLabel(source) {
  if (source === "llm") return "模型生成";
  if (source === "fallback") return "本地兜底";
  return "来源未知";
}

els.startForm.addEventListener("submit", (event) => startSession(event).catch(showError));
els.answerForm.addEventListener("submit", (event) => submitAnswer(event).catch(showError));
els.finalizeBtn.addEventListener("click", () => finalize().catch(showError));
els.refreshSessions.addEventListener("click", () => loadSessions().catch(showError));
els.selectDeleteBtn.addEventListener("click", toggleDeleteMode);
els.cancelDeleteBtn.addEventListener("click", cancelDeleteMode);
els.deleteAllBtn.addEventListener("click", () => deleteAllSessions().catch(showError));
els.resultTabs.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-tab]");
  if (!button) return;
  state.activeTab = button.dataset.tab;
  renderActiveTab();
});
els.copyMarkdown.addEventListener("click", async () => {
  if (!state.finalPackage) return;
  await navigator.clipboard.writeText(buildMarkdown(state.finalPackage));
  addProgress("Markdown 已复制。");
});

function showError(error) {
  addProgress(error.message || String(error));
}

async function init() {
  try {
    const health = await api("/api/health");
    els.runtimeStatus.textContent = health.llm_enabled ? `模型：${health.provider}` : "离线演示模式";
  } catch {
    els.runtimeStatus.textContent = "服务未连接";
  }
  renderDeleteMode();
  await loadSessions().catch(() => undefined);
}

init();
