const tabs = Array.from(document.querySelectorAll('.sidebar [role="tab"]'));
const panels = Array.from(document.querySelectorAll(".main-content > [role='tabpanel']"));
const sampleLibrary = document.querySelector("#sample-library");
const sessionForm = document.querySelector("#session-form");
const sessionStatus = document.querySelector("#session-status");
const interviewStart = document.querySelector("#interview-start");
const interviewLive = document.querySelector("#interview-live");
const directionList = document.querySelector("#direction-list");
const cloneNotice = document.querySelector("#clone-notice");
const chatLog = document.querySelector("#chat-log");
const chatForm = document.querySelector("#chat-form");
const answerInput = document.querySelector("#answer-input");
const sendAnswerButton = document.querySelector("#send-answer");
const endInterviewButton = document.querySelector("#end-interview");
const turnStatus = document.querySelector("#turn-status");
const reviewsRoot = document.querySelector("#reviews-root");
const interviewPanel = document.querySelector("#panel-interview");
const reviewsPanel = document.querySelector("#panel-reviews");
const ROLE_LABELS = {
  "llm-algo": "LLM 算法实习",
  training: "大模型训练与对齐",
  rag: "RAG 与 Agent 应用",
};
let libraryLoaded = false;
let libraryLoading = false;
let libraryCache = null;
let libraryKind = "jd";
let turnInFlight = false;
let endingInFlight = false;
const REPORT_SECTIONS = [
  { key: "overview", label: "总评", aliases: ["总评", "综合评价", "整体评价"] },
  {
    key: "essence",
    label: "岗位本质",
    aliases: ["岗位本质对照", "岗位本质", "本质对照"],
  },
  { key: "knowledge", label: "知识建议", aliases: ["知识建议", "知识补习"] },
  {
    key: "improve",
    label: "项目改良",
    aliases: ["项目改良", "最小改造", "项目改造", "改造建议"],
  },
];

function createTextElement(tagName, className, text) {
  const element = document.createElement(tagName);
  element.className = className;
  element.textContent = text;
  return element;
}

function createLoadingState(text) {
  const loading = document.createElement("div");
  loading.className = "loading-state";
  loading.setAttribute("role", "status");
  const spinner = document.createElement("span");
  spinner.className = "spinner";
  spinner.setAttribute("aria-hidden", "true");
  loading.append(spinner, document.createTextNode(text));
  return loading;
}

function safeSourceUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function fieldText(value) {
  if (value == null || value === "") {
    return "";
  }
  if (Array.isArray(value)) {
    return value.map(fieldText).filter(Boolean).join("、");
  }
  return String(value);
}

function displayOrNone(value) {
  return fieldText(value).trim() || "暂无";
}

function isGraduateTargeted(sample) {
  const education = fieldText(sample.education).trim();
  const masterPhd = /硕士|博士|master'?s?\b|ph\.?\s*d\.?/i;
  const bachelor = /本科|学士|bachelor/i;
  if (education && masterPhd.test(education)) {
    if (
      bachelor.test(education) &&
      !/硕士及以上|仅限硕士|仅限博士|博士/.test(education)
    ) {
      return false;
    }
    return true;
  }
  const blob = [
    education,
    fieldText(sample.requirements),
    fieldText(sample.text),
    fieldText(sample.experience),
  ].join("\n");
  return /硕士及以上|博士及以上|(?:学历|要求)[^\n。]{0,20}(?:硕士|博士)|(?:仅限|必须|须为)[^\n。]{0,8}(?:硕士|博士)|(?:硕士|博士)[^\n。]{0,8}(?:学历|及以上|起步)|master'?s(?:\s+degree)?\s+(?:or\s+above|and\s+above|required)|ph\.?\s*d\.?\s+(?:or\s+above|required)/i.test(
    blob,
  );
}

function kindOfSample(sample, fallback) {
  const kind = String(sample.kind || "").trim().toLowerCase();
  if (kind === "interview" || kind === "面经") {
    return "interview";
  }
  if (kind === "jd" || kind === "job") {
    return "jd";
  }
  return fallback;
}

function partitionLibrary(data) {
  const buckets = { jds: [], interviews: [] };
  const rows = [
    ...(data.jds || []).map((sample) => ({ sample, fallback: "jd" })),
    ...(data.interviews || []).map((sample) => ({
      sample,
      fallback: "interview",
    })),
  ];
  for (const { sample, fallback } of rows) {
    if (!safeSourceUrl(sample.source_url) || !sample.source_name) {
      continue;
    }
    if (isGraduateTargeted(sample)) {
      continue;
    }
    if (kindOfSample(sample, fallback) === "interview") {
      buckets.interviews.push(sample);
    } else {
      buckets.jds.push(sample);
    }
  }
  return buckets;
}

function closeLibraryModal() {
  document.querySelector("#library-modal")?.remove();
  document.body.classList.remove("modal-open");
}

function openSampleDetail(sample, kind) {
  closeLibraryModal();
  const sourceUrl = safeSourceUrl(sample.source_url);
  const overlay = document.createElement("div");
  overlay.id = "library-modal";
  overlay.className = "modal-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", "library-modal-title");

  const card = document.createElement("div");
  card.className = "modal-card";

  const header = document.createElement("div");
  header.className = "modal-header";
  header.append(
    createTextElement("p", "modal-kicker", sample.company || "未知公司"),
    createTextElement(
      "h2",
      "modal-title",
      sample.role || (kind === "interview" ? "面经" : "岗位"),
    ),
  );
  header.querySelector("h2").id = "library-modal-title";

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "btn modal-close";
  closeBtn.textContent = "关闭";
  closeBtn.addEventListener("click", closeLibraryModal);

  const body = document.createElement("div");
  body.className = "modal-body";

  const addField = (label, value) => {
    body.append(
      createTextElement("p", "modal-meta-label", label),
      createTextElement("p", "modal-meta-value", value),
    );
  };

  addField("发布日期", displayOrNone(sample.published_at || sample.captured_at));
  if (kind === "jd") {
    addField("岗位要求", displayOrNone(sample.requirements));
  } else {
    addField("常考题型", displayOrNone(sample.question_types));
    addField("面试经验", displayOrNone(sample.experience));
  }
  addField("原文", displayOrNone(sample.text));

  if (sourceUrl) {
    const source = document.createElement("a");
    source.className = "source-link";
    source.href = sourceUrl;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    source.textContent = `查看来源 · ${sample.source_name}`;
    body.append(createTextElement("p", "modal-meta-label", "来源链接"), source);
  } else {
    addField("来源链接", "暂无");
  }

  card.append(closeBtn, header, body);
  overlay.append(card);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      closeLibraryModal();
    }
  });
  document.body.append(overlay);
  document.body.classList.add("modal-open");
  closeBtn.focus();
}

function renderLibraryCard(sample, kind) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "library-card";
  button.append(
    createTextElement("span", "library-card-company", sample.company || "未知公司"),
    createTextElement("span", "library-card-role", sample.role || "未命名岗位"),
  );
  button.addEventListener("click", () => {
    openSampleDetail(sample, kind);
  });
  return button;
}

function renderLibraryGrid(data) {
  if (!sampleLibrary) {
    return;
  }
  const samples = libraryKind === "interview" ? data.interviews : data.jds;
  if (!samples.length) {
    sampleLibrary.replaceChildren(
      createTextElement(
        "p",
        "empty-state",
        libraryKind === "interview" ? "暂无可核验面经" : "暂无可核验 JD",
      ),
    );
    return;
  }
  const grid = document.createElement("div");
  grid.className = "library-grid";
  grid.setAttribute(
    "aria-label",
    libraryKind === "interview" ? "面经列表" : "JD 列表",
  );
  grid.append(
    ...samples.map((sample) => renderLibraryCard(sample, libraryKind)),
  );
  sampleLibrary.replaceChildren(grid);
}

function setLibraryKind(nextKind) {
  libraryKind = nextKind === "interview" ? "interview" : "jd";
  document.querySelectorAll(".kind-btn").forEach((button) => {
    const isActive = button.dataset.kind === libraryKind;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });
  if (libraryCache) {
    renderLibraryGrid(libraryCache);
    return;
  }
  libraryLoading = false;
  void loadSampleLibrary();
}

async function loadSampleLibrary() {
  if (!sampleLibrary || libraryLoaded || libraryLoading) {
    return;
  }

  libraryLoading = true;
  sampleLibrary.replaceChildren(createLoadingState("正在加载真实样本"));
  try {
    const response = await fetch("/api/jds", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    if (!Array.isArray(data.jds) || !Array.isArray(data.interviews)) {
      throw new Error("样本数据格式错误");
    }

    libraryCache = partitionLibrary(data);
    libraryLoaded = true;
    renderLibraryGrid(libraryCache);
  } catch (error) {
    console.error("Failed to load sourced samples", error);
    libraryLoaded = false;
    libraryCache = null;
    sampleLibrary.replaceChildren(
      createTextElement("p", "flash error", "真实样本加载失败，请稍后重试。"),
    );
  } finally {
    libraryLoading = false;
  }
}

function setSessionLoading(isLoading) {
  if (!sessionForm) {
    return;
  }

  sessionForm
    .querySelectorAll("input, textarea, select, button")
    .forEach((control) => {
      control.disabled = isLoading;
    });

  if (isLoading) {
    sessionStatus.replaceChildren(createLoadingState("正在确定方向并准备代码仓库"));
  }
}

function apiErrorMessage(data, fallback) {
  if (typeof data?.detail === "string") {
    return data.detail;
  }
  if (Array.isArray(data?.detail) && typeof data.detail[0]?.msg === "string") {
    return data.detail[0].msg.replace(/^Value error,\s*/, "");
  }
  return fallback;
}

function setCurrentDirection(directionId) {
  if (!interviewLive || !directionId) {
    return;
  }
  interviewLive.dataset.currentDirectionId = directionId;
  directionList?.querySelectorAll(".direction-item").forEach((item) => {
    item.classList.toggle("current", item.dataset.directionId === directionId);
  });
}

function appendInterviewerBubble(text, directionId, container = chatLog) {
  const row = document.createElement("div");
  row.className = "bubble-row interviewer";
  if (directionId) {
    row.dataset.directionId = directionId;
  }
  row.append(createTextElement("div", "bubble", text));
  container.append(row);
  container.scrollTop = container.scrollHeight;
  if (container === chatLog) {
    setCurrentDirection(directionId);
  }
  return row;
}

function appendUserBlock(text, container = chatLog) {
  const block = document.createElement("div");
  block.className = "user-block";

  const row = document.createElement("div");
  row.className = "bubble-row user";
  row.append(createTextElement("div", "bubble", text));

  const thought = document.createElement("div");
  thought.className = "thought";
  thought.hidden = true;

  block.append(row, thought);
  container.append(block);
  container.scrollTop = container.scrollHeight;
  return thought;
}

function sanitizeThought(text) {
  return text
    .split("\n")
    .filter((line) => !/(建议你|总评|复习|岗位本质对照|知识建议|项目改良)/.test(line))
    .join("\n");
}

function sessionHasEnded() {
  return interviewLive?.dataset.ended === "1";
}

function setComposerEnabled(enabled) {
  if (chatForm) {
    chatForm.hidden = !enabled;
  }
  if (answerInput) {
    answerInput.disabled = !enabled;
  }
  if (sendAnswerButton) {
    sendAnswerButton.disabled = !enabled;
    sendAnswerButton.setAttribute("aria-disabled", String(!enabled));
  }
  if (endInterviewButton) {
    endInterviewButton.disabled = !enabled;
  }
}

function setTurnLoading(isLoading) {
  turnInFlight = isLoading;
  if (chatForm) {
    chatForm.setAttribute("aria-busy", String(isLoading));
  }
  if (sendAnswerButton) {
    sendAnswerButton.disabled = isLoading || sessionHasEnded();
    sendAnswerButton.setAttribute(
      "aria-disabled",
      String(isLoading || sessionHasEnded()),
    );
  }
  if (endInterviewButton) {
    endInterviewButton.disabled =
      isLoading ||
      endingInFlight ||
      sessionHasEnded() ||
      !interviewLive?.dataset.sessionId;
  }
  if (!turnStatus) {
    return;
  }
  if (isLoading) {
    turnStatus.replaceChildren(createLoadingState("面试官正在思考"));
  } else if (!endingInFlight) {
    turnStatus.replaceChildren();
  }
}

function renderStartedSession(session) {
  directionList.replaceChildren(
    ...session.directions.map((direction) => {
      const item = document.createElement("li");
      item.className = "direction-item";
      item.dataset.directionId = direction.id;
      item.append(
        createTextElement("p", "direction-title", direction.title),
        createTextElement("p", "direction-goal", direction.goal),
      );
      return item;
    }),
  );
  cloneNotice.hidden = session.clone_ok;
  cloneNotice.textContent = session.clone_ok
    ? ""
    : session.clone_error || "代码仓库暂不可用，面试仍可继续。";
  interviewLive.dataset.sessionId = session.id;
  chatLog.replaceChildren();
  appendInterviewerBubble(session.first_question, "d1");
  if (answerInput) {
    answerInput.value = "";
  }
  interviewLive.dataset.ended = "";
  setComposerEnabled(true);
  setTurnLoading(false);
  interviewStart.hidden = true;
  interviewLive.hidden = false;
  interviewLive.focus({ preventScroll: true });
  interviewLive.scrollIntoView({ behavior: "smooth", block: "start" });
}

function applySseEvent(eventName, data, thoughtNode, state) {
  if (eventName === "thought_delta") {
    thoughtNode.hidden = false;
    thoughtNode.textContent += sanitizeThought(data.text || "");
    chatLog.scrollTop = chatLog.scrollHeight;
    return;
  }
  if (eventName === "tool") {
    thoughtNode.hidden = false;
    const toolName = data.name || "code_inspect";
    const toolResult = sanitizeThought(data.result || "");
    thoughtNode.textContent += `\n查代码：是（${toolName}）\n${toolResult}\n`;
    chatLog.scrollTop = chatLog.scrollHeight;
    return;
  }
  if (eventName === "question") {
    state.question = data.text || "";
    state.directionId = data.direction_id || interviewLive.dataset.currentDirectionId;
    state.directionDone = Boolean(data.direction_done);
    return;
  }
  if (eventName === "error") {
    throw new Error(data.message || "本轮追问失败");
  }
}

function parseSseBlock(block, onEvent) {
  const lines = block.split("\n");
  let eventName = "message";
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) {
    return;
  }
  const data = JSON.parse(dataLines.join("\n"));
  onEvent(eventName, data);
}

async function consumeSse(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const consumeBuffer = (raw, flushRemainder) => {
    const chunks = raw.split("\n\n");
    const remainder = flushRemainder ? "" : chunks.pop() || "";
    for (const chunk of chunks) {
      if (chunk.trim()) {
        parseSseBlock(chunk, onEvent);
      }
    }
    return remainder;
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      consumeBuffer(buffer, true);
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    buffer = consumeBuffer(buffer, false);
  }
}

async function consumeTurnStream(response, thoughtNode) {
  const state = {
    question: "",
    directionId: interviewLive.dataset.currentDirectionId || "d1",
    directionDone: false,
  };
  await consumeSse(response, (eventName, data) => {
    applySseEvent(eventName, data, thoughtNode, state);
  });
  return state;
}

async function submitTurn(event) {
  event.preventDefault();
  if (turnInFlight || endingInFlight || sessionHasEnded()) {
    return;
  }
  if (!chatForm.reportValidity()) {
    return;
  }

  const sessionId = interviewLive.dataset.sessionId;
  const answer = answerInput.value.trim();
  if (!sessionId || !answer) {
    return;
  }

  const thoughtNode = appendUserBlock(answer);
  answerInput.value = "";
  setTurnLoading(true);

  try {
    const response = await fetch(`/api/sessions/${sessionId}/turns`, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ answer }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(apiErrorMessage(data, "本轮追问失败，请稍后重试。"));
    }

    const turn = await consumeTurnStream(response, thoughtNode);
    if (!turn.question) {
      throw new Error("未收到下一问，请稍后重试。");
    }
    appendInterviewerBubble(turn.question, turn.directionId);
    setTurnLoading(false);
    answerInput.focus();
  } catch (error) {
    console.error("Failed to submit interview turn", error);
    turnStatus.replaceChildren(
      createTextElement(
        "p",
        "flash error",
        error instanceof Error ? error.message : "本轮追问失败，请稍后重试。",
      ),
    );
    setTurnLoading(false);
  }
}

async function submitSession(event) {
  event.preventDefault();
  if (!sessionForm.reportValidity()) {
    return;
  }

  const formData = new FormData(sessionForm);
  const payload = {
    github_url: formData.get("github_url"),
    statement: formData.get("statement"),
    role: formData.get("role"),
  };
  setSessionLoading(true);

  try {
    const response = await fetch("/api/sessions", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(apiErrorMessage(data, "面试启动失败，请稍后重试。"));
    }
    if (
      !Array.isArray(data.directions) ||
      data.directions.length < 3 ||
      !data.first_question
    ) {
      throw new Error("面试方向返回格式无效，请稍后重试。");
    }

    renderStartedSession(data);
  } catch (error) {
    console.error("Failed to start interview session", error);
    sessionStatus.replaceChildren(
      createTextElement(
        "p",
        "flash error",
        error instanceof Error ? error.message : "面试启动失败，请稍后重试。",
      ),
    );
    setSessionLoading(false);
  }
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderMarkdown(text) {
  const escaped = escapeHtml(text);
  const html = escaped
    .split(/\n{2,}/)
    .map((block) => {
      const trimmed = block.trim();
      if (!trimmed) {
        return "";
      }
      if (/^##\s+/.test(trimmed)) {
        return `<h2>${trimmed.replace(/^##\s+/, "").replace(/\n/g, "<br>")}</h2>`;
      }
      if (/^###\s+/.test(trimmed)) {
        return `<h3>${trimmed.replace(/^###\s+/, "").replace(/\n/g, "<br>")}</h3>`;
      }
      if (/^[-*]\s/m.test(trimmed)) {
        const items = trimmed
          .split("\n")
          .filter((line) => /^[-*]\s/.test(line))
          .map((line) => `<li>${line.replace(/^[-*]\s+/, "")}</li>`)
          .join("");
        return `<ul>${items}</ul>`;
      }
      return `<p>${trimmed.replace(/\n/g, "<br>")}</p>`;
    })
    .join("");
  const withBold = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  if (window.DOMPurify) {
    return window.DOMPurify.sanitize(withBold);
  }
  return withBold;
}

function normalizeReportHeading(line) {
  return line
    .replace(/^#{1,6}\s*/, "")
    .replace(/^\*{1,2}\s*|\s*\*{1,2}$/g, "")
    .replace(/^[（(]?[一二三四1-4][）)、.\s]+/, "")
    .replace(/[：:]\s*$/, "")
    .replace(/[【】\[\]]/g, "")
    .trim();
}

function matchReportSection(line) {
  const heading = normalizeReportHeading(line);
  if (!heading || heading.length > 24) {
    return null;
  }
  for (const section of REPORT_SECTIONS) {
    for (const alias of section.aliases) {
      if (heading === alias || heading.endsWith(alias) || heading.startsWith(alias)) {
        return section.key;
      }
    }
  }
  return null;
}

function splitReportSections(text) {
  const result = {
    overview: "",
    essence: "",
    knowledge: "",
    improve: "",
  };
  const raw = String(text || "").replace(/\r\n/g, "\n").trim();
  if (!raw) {
    return result;
  }

  const buckets = {
    overview: [],
    essence: [],
    knowledge: [],
    improve: [],
  };
  const preamble = [];
  let current = null;

  for (const line of raw.split("\n")) {
    const key = matchReportSection(line.trim());
    if (key) {
      current = key;
      continue;
    }
    if (current) {
      buckets[current].push(line);
    } else {
      preamble.push(line);
    }
  }

  for (const key of Object.keys(buckets)) {
    result[key] = buckets[key].join("\n").trim();
  }
  if (!result.overview && preamble.join("").trim()) {
    result.overview = preamble.join("\n").trim();
  }
  if (!result.overview && !result.essence && !result.knowledge && !result.improve) {
    result.overview = raw;
  }
  return result;
}

function renderSectionHtml(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) {
    return "<p>暂无此段内容</p>";
  }
  return renderMarkdown(trimmed);
}

function renderReportTabs(reportText, reportPane) {
  const sections = splitReportSections(reportText);
  const tabs = document.createElement("div");
  tabs.className = "report-tabs";
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", "报告段落");

  const body = document.createElement("article");
  body.className = "report-article report-article-body";
  body.setAttribute("role", "tabpanel");

  const show = (key) => {
    tabs.querySelectorAll(".report-tab").forEach((button) => {
      const isActive = button.dataset.section === key;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-selected", String(isActive));
    });
    const section = REPORT_SECTIONS.find((item) => item.key === key);
    body.setAttribute("aria-label", section ? section.label : "总评");
    body.innerHTML = renderSectionHtml(sections[key]);
  };

  for (const section of REPORT_SECTIONS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "report-tab";
    button.dataset.section = section.key;
    button.textContent = section.label;
    button.setAttribute("role", "tab");
    button.addEventListener("click", () => {
      show(section.key);
    });
    tabs.append(button);
  }

  reportPane.replaceChildren(tabs, body);
  show("overview");
}

function renderTurnsInto(container, turns) {
  container.replaceChildren();
  let thoughtNode = null;
  for (const turn of turns || []) {
    if (turn.role === "interviewer") {
      appendInterviewerBubble(turn.body, turn.direction_id, container);
      thoughtNode = null;
    } else if (turn.role === "user") {
      thoughtNode = appendUserBlock(turn.body, container);
    } else if (turn.role === "thought" && thoughtNode) {
      thoughtNode.hidden = false;
      thoughtNode.textContent = sanitizeThought(turn.body || "");
      thoughtNode = null;
    }
  }
}

function renderEndedView(snapshot, container) {
  const chatPane = document.createElement("div");
  chatPane.className = "ended-pane ended-pane-chat";
  chatPane.setAttribute("data-ended-chat", "1");
  renderTurnsInto(chatPane, snapshot.turns || []);

  const divider = document.createElement("div");
  divider.className = "ended-view-divider";
  divider.setAttribute("aria-hidden", "true");

  const reportPane = document.createElement("div");
  reportPane.className = "ended-pane ended-pane-report";
  reportPane.setAttribute("data-ended-report", "1");
  renderReportTabs(snapshot.report?.text || "", reportPane);

  container.classList.add("ended-view");
  container.replaceChildren(chatPane, divider, reportPane);
}

function markInterviewPanelEnded() {
  interviewPanel?.classList.add("has-ended-view");
  document.querySelector(".main-content")?.classList.add("ended-layout");
}

function ensureEndedShell() {
  let endedView = document.querySelector("#ended-view");
  if (endedView) {
    return endedView;
  }
  endedView = document.createElement("div");
  endedView.id = "ended-view";
  endedView.className = "ended-view";
  const chatPane = document.createElement("div");
  chatPane.className = "ended-pane ended-pane-chat";
  while (chatLog.firstChild) {
    chatPane.append(chatLog.firstChild);
  }
  const divider = document.createElement("div");
  divider.className = "ended-view-divider";
  const reportPane = document.createElement("div");
  reportPane.className = "ended-pane ended-pane-report";
  reportPane.id = "ended-report-stream";
  endedView.append(chatPane, divider, reportPane);
  chatLog.replaceWith(endedView);
  markInterviewPanelEnded();
  setComposerEnabled(false);
  return endedView;
}

function formatReviewTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function renderEmptyReviews() {
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.setAttribute("role", "status");
  const symbol = document.createElement("span");
  symbol.className = "empty-symbol";
  symbol.setAttribute("aria-hidden", "true");
  symbol.textContent = "○";
  empty.append(symbol, createTextElement("p", "", "还没有面试记录"));
  reviewsRoot.replaceChildren(empty);
}

async function fetchSnapshot(reviewId) {
  const response = await fetch(`/api/reviews/${reviewId}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error("复盘读取失败，请稍后重试。");
  }
  const raw = await response.text();
  return JSON.parse(raw);
}

async function loadReviews() {
  if (!reviewsRoot) {
    return;
  }
  reviewsPanel?.classList.remove("has-ended-view");
  reviewsRoot.replaceChildren(createLoadingState("正在加载复盘"));
  try {
    const response = await fetch("/api/reviews", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const items = await response.json();
    if (!Array.isArray(items) || items.length === 0) {
      renderEmptyReviews();
      return;
    }
    const list = document.createElement("div");
    list.className = "reviews-list";
    for (const item of items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "list-item";
      button.append(
        createTextElement(
          "p",
          "list-item-meta",
          `${formatReviewTime(item.created_at)} · ${ROLE_LABELS[item.role] || item.role}`,
        ),
        createTextElement("p", "list-item-preview", item.statement_preview || ""),
      );
      button.addEventListener("click", () => {
        void openReview(item.id);
      });
      list.append(button);
    }
    reviewsRoot.replaceChildren(list);
  } catch (error) {
    console.error("Failed to load reviews", error);
    reviewsRoot.replaceChildren(
      createTextElement("p", "flash error", "复盘列表加载失败，请稍后重试。"),
    );
  }
}

async function openReview(reviewId) {
  if (!reviewsRoot) {
    return;
  }
  reviewsRoot.replaceChildren(createLoadingState("正在打开复盘"));
  try {
    const snapshot = await fetchSnapshot(reviewId);
    const wrap = document.createElement("div");
    wrap.className = "review-detail";
    const back = document.createElement("button");
    back.type = "button";
    back.className = "btn";
    back.textContent = "返回列表";
    back.addEventListener("click", () => {
      reviewsPanel?.classList.remove("has-ended-view");
      void loadReviews();
    });
    const ended = document.createElement("div");
    ended.className = "ended-view";
    wrap.append(back, ended);
    reviewsRoot.replaceChildren(wrap);
    renderEndedView(snapshot, ended);
    reviewsPanel?.classList.add("has-ended-view");
    document.querySelector(".main-content")?.classList.add("ended-layout");
  } catch (error) {
    console.error("Failed to open review", error);
    reviewsRoot.replaceChildren(
      createTextElement(
        "p",
        "flash error",
        error instanceof Error ? error.message : "复盘读取失败，请稍后重试。",
      ),
    );
  }
}

async function finishWithSnapshot(sessionId) {
  const snapshot = await fetchSnapshot(sessionId);
  const endedView = ensureEndedShell();
  renderEndedView(snapshot, endedView);
  interviewLive.dataset.ended = "1";
  markInterviewPanelEnded();
  setComposerEnabled(false);
}

function setEndLoading(isLoading) {
  endingInFlight = isLoading;
  if (endInterviewButton) {
    endInterviewButton.disabled = true;
  }
  if (!turnStatus) {
    return;
  }
  if (isLoading) {
    turnStatus.replaceChildren(createLoadingState("正在生成结束报告"));
  } else {
    turnStatus.replaceChildren();
  }
}

async function submitEndInterview() {
  if (turnInFlight || endingInFlight || sessionHasEnded()) {
    return;
  }
  const sessionId = interviewLive?.dataset.sessionId;
  if (!sessionId) {
    return;
  }

  setEndLoading(true);
  setComposerEnabled(false);
  const endedView = ensureEndedShell();
  const reportPane = endedView.querySelector(".ended-pane-report");
  const stream = document.createElement("pre");
  stream.className = "report-stream";
  reportPane.replaceChildren(stream);

  try {
    const response = await fetch(`/api/sessions/${sessionId}/end`, {
      method: "POST",
      headers: { Accept: "text/event-stream" },
    });
    if (response.status === 409) {
      await finishWithSnapshot(sessionId);
      setEndLoading(false);
      return;
    }
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(apiErrorMessage(data, "结束报告生成失败，请稍后重试。"));
    }

    await consumeSse(response, (eventName, data) => {
      if (eventName === "report_delta") {
        stream.textContent += data.text || "";
        reportPane.scrollTop = reportPane.scrollHeight;
        return;
      }
      if (eventName === "tool") {
        const note = document.createElement("p");
        note.className = "report-tool-note";
        note.textContent = `查代码：${data.result || ""}`;
        reportPane.insertBefore(note, stream);
        return;
      }
      if (eventName === "error") {
        throw new Error(data.message || "结束报告生成失败");
      }
    });

    await finishWithSnapshot(sessionId);
    setEndLoading(false);
  } catch (error) {
    console.error("Failed to end interview", error);
    try {
      await finishWithSnapshot(sessionId);
      setEndLoading(false);
    } catch {
      setComposerEnabled(true);
      setEndLoading(false);
      turnStatus.replaceChildren(
        createTextElement(
          "p",
          "flash error",
          error instanceof Error ? error.message : "结束报告生成失败，请稍后重试。",
        ),
      );
    }
  }
}

function activateTab(nextTab) {
  const panelName = nextTab.dataset.panel;

  tabs.forEach((tab) => {
    const isActive = tab === nextTab;
    tab.classList.toggle("active", isActive);
    tab.setAttribute("aria-selected", String(isActive));
    tab.tabIndex = isActive ? 0 : -1;
  });

  panels.forEach((panel) => {
    panel.hidden = panel.id !== `panel-${panelName}`;
  });

  if (panelName === "jds") {
    void loadSampleLibrary();
  }
  if (panelName === "reviews") {
    void loadReviews();
  }
}

tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activateTab(tab));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft"].includes(event.key)) {
      return;
    }

    event.preventDefault();
    const movesForward = event.key === "ArrowDown" || event.key === "ArrowRight";
    const offset = movesForward ? 1 : -1;
    const nextIndex = (index + offset + tabs.length) % tabs.length;
    activateTab(tabs[nextIndex]);
    tabs[nextIndex].focus();
  });
});

sessionForm?.addEventListener("submit", submitSession);
chatForm?.addEventListener("submit", submitTurn);
endInterviewButton?.addEventListener("click", () => {
  void submitEndInterview();
});
document.querySelectorAll(".kind-btn").forEach((button) => {
  button.addEventListener("click", () => {
    setLibraryKind(button.dataset.kind);
  });
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && document.querySelector("#library-modal")) {
    closeLibraryModal();
  }
});
