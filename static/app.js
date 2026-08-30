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
const askTeacherButton = document.querySelector("#ask-teacher");
const endInterviewButton = document.querySelector("#end-interview");
const turnStatus = document.querySelector("#turn-status");
const reviewsRoot = document.querySelector("#reviews-root");
const interviewPanel = document.querySelector("#panel-interview");
const reviewsPanel = document.querySelector("#panel-reviews");
const liveWorkspace = document.querySelector("#live-workspace");
const codeIde = document.querySelector("#code-ide");
const codeIdeTitle = document.querySelector("#code-ide-title");
const codeIdePrompt = document.querySelector("#code-ide-prompt");
const codeIdeKicker = document.querySelector("#code-ide-kicker");
const codeIdeMeta = document.querySelector("#code-ide-meta");
const codeIdeStatus = document.querySelector("#code-ide-status");
const codeIdeCollapsedText = document.querySelector("#code-ide-collapsed-text");
const monacoHost = document.querySelector("#monaco-editor");
const submitCodeButton = document.querySelector("#submit-code");
const codeIdeExpand = document.querySelector("#code-ide-expand");
const codeIdeCollapse = document.querySelector("#code-ide-collapse");
const ROLE_LABELS = {
  "llm-algo": "LLM 算法实习",
  agent: "Agent 应用实习",
  rag: "RAG / AI 搜索实习",
};
const DEMO_CATALOG_URL = "/demo-projects.json?v=21";
let demoCatalog = [];
let demoCatalogPromise = null;
const LIBRARY_PAGE_SIZE = 9;
let libraryLoading = false;
let libraryRequestSeq = 0;
let libraryKind = "jd";
let libraryPage = 1;
let turnInFlight = false;
let endingInFlight = false;
let monacoLoadPromise = null;
let monacoEditor = null;
let monacoWorkerUrl = "";
let monacoCommandBound = false;
let ideOpenSeq = 0;
let codeExerciseState = null;
let codeSubmitting = false;
const MONACO_CDNS = [
  "https://registry.npmmirror.com/monaco-editor/0.52.2/files/min",
  "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min",
];
const MOCK_SESSION_ID = "mock-session";
const CHAT_PLACEHOLDER_DEFAULT = "回答当前问题";
const CHAT_PLACEHOLDER_WITH_IDE = "写代码时也可以问面试官语法或 API";
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
const TOOL_UI = {
  thinking: { label: "思考", start: "正在组织这一轮评价" },
  search_library: { label: "检索面经", start: "正在调用检索面经工具" },
  code_inspect: { label: "查仓库", start: "正在调用查仓库工具" },
  code_exercise: { label: "打开手撕", start: "正在打开手撕题" },
};

function loadDemoCatalog() {
  if (demoCatalog.length) {
    return Promise.resolve(demoCatalog);
  }
  if (!demoCatalogPromise) {
    demoCatalogPromise = fetch(DEMO_CATALOG_URL, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) {
          throw new Error("测试样本加载失败");
        }
        return response.json();
      })
      .then((data) => {
        demoCatalog = Array.isArray(data?.projects) ? data.projects : [];
        return demoCatalog;
      })
      .catch((error) => {
        demoCatalogPromise = null;
        throw error;
      });
  }
  return demoCatalogPromise;
}

function getDemoById(demoId) {
  return demoCatalog.find((item) => item.id === demoId) || null;
}

function selectedDemoId() {
  return document.querySelector("#demo-select")?.value || "";
}

function applyDemoPreset(demoId, currentRole) {
  const demo = getDemoById(demoId);
  if (!demo) {
    return null;
  }
  const githubInput = document.querySelector("#github-url");
  const statementInput = document.querySelector("#statement");
  const roleSelect = document.querySelector("#role");
  const sampleRole = demo.role || "llm-algo";
  const nextRole = sampleRole || String(currentRole || "").trim();
  if (githubInput) {
    githubInput.value = demo.github_url;
  }
  if (statementInput) {
    statementInput.value = demo.statement;
  }
  if (roleSelect && (!roleSelect.value || sampleRole)) {
    roleSelect.value = nextRole;
  }
  return {
    github_url: demo.github_url,
    statement: demo.statement,
    role: roleSelect?.value || nextRole,
  };
}

async function handleDemoFill() {
  const demoId = selectedDemoId();
  if (!demoId) {
    return;
  }
  try {
    await loadDemoCatalog();
    const filled = applyDemoPreset(demoId, document.querySelector("#role")?.value);
    if (!filled) {
      throw new Error("未找到该测试样本");
    }
  } catch (error) {
    console.error("Failed to apply demo preset", error);
    if (sessionStatus) {
      sessionStatus.replaceChildren(
        createTextElement(
          "p",
          "flash error",
          error instanceof Error ? error.message : "测试样本加载失败",
        ),
      );
    }
  }
}

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

const LIBRARY_KEYWORDS = [
  "Multi-Head Attention",
  "PagedAttention",
  "KV cache",
  "KV Cache",
  "Transformer",
  "Attention",
  "RMSNorm",
  "SwiGLU",
  "RoPE",
  "LoRA",
  "GRPO",
  "RLHF",
  "PPO",
  "DPO",
  "SFT",
  "RAG",
  "Agent",
  "Tokenizer",
  "手撕",
  "实习",
  "一面",
  "二面",
];

function isXiaohongshuSample(sample) {
  const blob = `${sample.source_name || ""} ${sample.source_url || ""}`.toLowerCase();
  return blob.includes("小红书") || blob.includes("xiaohongshu") || blob.includes("xhslink");
}

function sourcePlatform(sample) {
  const blob = `${sample.source_name || ""} ${sample.source_url || ""}`.toLowerCase();
  if (isXiaohongshuSample(sample)) {
    return "xhs";
  }
  if (blob.includes("牛客") || blob.includes("nowcoder")) {
    return "nowcoder";
  }
  return "official";
}

function sourceLabel(sample) {
  const platform = sourcePlatform(sample);
  if (platform === "xhs") {
    return "小红书";
  }
  if (platform === "nowcoder") {
    return "牛客";
  }
  return sample.source_name || "官方招聘";
}

function sampleDisplayDate(sample) {
  return String(
    sample.published_at ||
      sample.sort_date ||
      sample.created_at ||
      sample.date ||
      sample.captured_at ||
      "",
  ).trim();
}

function appendHighlightedText(parent, text) {
  const source = String(text || "");
  if (!source) {
    parent.append(document.createTextNode("暂无"));
    return;
  }
  const pattern = new RegExp(
    `(${LIBRARY_KEYWORDS.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "gi",
  );
  let cursor = 0;
  for (const match of source.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > cursor) {
      parent.append(document.createTextNode(source.slice(cursor, index)));
    }
    const strong = document.createElement("strong");
    strong.textContent = match[0];
    parent.append(strong);
    cursor = index + match[0].length;
  }
  if (cursor < source.length) {
    parent.append(document.createTextNode(source.slice(cursor)));
  }
}

function createSourceMark(sample) {
  const platform = sourcePlatform(sample);
  const mark = document.createElement("span");
  mark.className = `source-mark source-mark-${platform}`;

  const logo = document.createElement("span");
  logo.className = "source-logo";
  logo.setAttribute("aria-hidden", "true");
  if (platform === "xhs") {
    logo.innerHTML =
      '<svg viewBox="0 0 32 32" width="18" height="18"><rect width="32" height="32" rx="6" fill="#FF2442"/><text x="16" y="21" text-anchor="middle" fill="#fff" font-size="11" font-family="sans-serif" font-weight="700">红</text></svg>';
  } else if (platform === "nowcoder") {
    logo.innerHTML =
      '<svg viewBox="0 0 32 32" width="18" height="18"><rect width="32" height="32" rx="6" fill="#19B24B"/><text x="16" y="21" text-anchor="middle" fill="#fff" font-size="11" font-family="sans-serif" font-weight="700">牛</text></svg>';
  } else {
    logo.innerHTML =
      '<svg viewBox="0 0 32 32" width="18" height="18"><rect width="32" height="32" rx="6" fill="#1D1D1F"/><text x="16" y="21" text-anchor="middle" fill="#fff" font-size="11" font-family="sans-serif" font-weight="700">招</text></svg>';
  }

  const name = document.createElement("span");
  name.className = "source-mark-name";
  name.textContent = sourceLabel(sample);
  mark.append(logo, name);
  return mark;
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

  header.prepend(createSourceMark(sample));

  const addField = (label, value) => {
    body.append(createTextElement("p", "modal-meta-label", label));
    const paragraph = document.createElement("p");
    paragraph.className = "modal-meta-value";
    if (!value || value === "暂无") {
      paragraph.textContent = "暂无";
    } else {
      appendHighlightedText(paragraph, value);
    }
    body.append(paragraph);
  };

  addField("发布日期", displayOrNone(sampleDisplayDate(sample)));
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
  const excerpt = document.createElement("p");
  excerpt.className = "library-card-excerpt";
  const raw =
    kind === "interview"
      ? sample.text || sample.experience || ""
      : sample.text || sample.requirements || "";
  appendHighlightedText(excerpt, raw.slice(0, 72) + (raw.length > 72 ? "…" : ""));
  button.append(
    createSourceMark(sample),
    createTextElement("span", "library-card-company", sample.company || "未知公司"),
    createTextElement("span", "library-card-role", sample.role || "未命名岗位"),
  );
  const dateText = sampleDisplayDate(sample);
  if (dateText) {
    button.append(createTextElement("span", "library-card-date", dateText));
  }
  button.append(excerpt);
  button.addEventListener("click", () => {
    openSampleDetail(sample, kind);
  });
  return button;
}

function renderLibraryPager(page, pages) {
  const pager = document.createElement("nav");
  pager.className = "library-pager";
  pager.setAttribute(
    "aria-label",
    libraryKind === "interview" ? "面经分页" : "JD 分页",
  );

  const prev = document.createElement("button");
  prev.type = "button";
  prev.className = "btn btn-sm";
  prev.textContent = "上一页";
  prev.disabled = page <= 1;
  prev.addEventListener("click", () => {
    void loadSampleLibrary(page - 1);
  });

  const indicator = document.createElement("span");
  indicator.className = "library-page-indicator";
  indicator.setAttribute("aria-current", "page");
  indicator.textContent = `${page}/${Math.max(pages, 1)}`;

  const next = document.createElement("button");
  next.type = "button";
  next.className = "btn btn-sm";
  next.textContent = "下一页";
  next.disabled = pages === 0 || page >= pages;
  next.addEventListener("click", () => {
    void loadSampleLibrary(page + 1);
  });

  pager.append(prev, indicator, next);
  return pager;
}

function renderLibraryGrid(data) {
  if (!sampleLibrary) {
    return;
  }
  const samples = (data.items || []).filter(
    (sample) => safeSourceUrl(sample.source_url) && sample.source_name,
  );
  const page = Number(data.page) || libraryPage;
  const pages = Number(data.pages) || 0;
  if (!samples.length) {
    const empty = createTextElement(
      "p",
      "empty-state",
      libraryKind === "interview" ? "暂无可核验面经" : "暂无可核验 JD",
    );
    if (pages > 0) {
      sampleLibrary.replaceChildren(empty, renderLibraryPager(page, pages));
    } else {
      sampleLibrary.replaceChildren(empty);
    }
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
  sampleLibrary.replaceChildren(grid, renderLibraryPager(page, pages));
}

function setLibraryKind(nextKind) {
  const next = nextKind === "interview" ? "interview" : "jd";
  if (libraryKind !== next) {
    libraryKind = next;
    libraryPage = 1;
  }
  document.querySelectorAll(".kind-btn").forEach((button) => {
    const isActive = button.dataset.kind === libraryKind;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });
  void loadSampleLibrary(libraryPage);
}

async function loadSampleLibrary(page = libraryPage) {
  if (!sampleLibrary) {
    return;
  }

  const requestedPage = Math.max(1, Number(page) || 1);
  const seq = ++libraryRequestSeq;
  libraryLoading = true;
  libraryPage = requestedPage;
  sampleLibrary.replaceChildren(createLoadingState("正在加载真实样本"));
  try {
    const params = new URLSearchParams({
      type: libraryKind,
      page: String(requestedPage),
      page_size: String(LIBRARY_PAGE_SIZE),
    });
    const response = await fetch(`/api/jds?${params}`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    if (!Array.isArray(data.items)) {
      throw new Error("样本数据格式错误");
    }
    if (seq !== libraryRequestSeq) {
      return;
    }

    libraryPage = Number(data.page) || requestedPage;
    renderLibraryGrid(data);
  } catch (error) {
    console.error("Failed to load sourced samples", error);
    if (seq !== libraryRequestSeq) {
      return;
    }
    sampleLibrary.replaceChildren(
      createTextElement("p", "flash error", "真实样本加载失败，请稍后重试。"),
    );
  } finally {
    if (seq === libraryRequestSeq) {
      libraryLoading = false;
    }
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
    interviewLive.dataset.currentQuestion = text;
  }
  return row;
}

function appendTeacherHint(hint, container = chatLog) {
  const row = document.createElement("div");
  row.className = "teacher-hint";
  row.append(
    createTextElement("p", "teacher-hint-kicker", "老师提示 · 请用自己的话回答"),
    createTextElement("p", "teacher-hint-body", hint),
  );
  container.append(row);
  container.scrollTop = container.scrollHeight;
  return row;
}

function appendUserBlock(text, container = chatLog, options = {}) {
  const block = document.createElement("div");
  block.className = "user-block";

  const row = document.createElement("div");
  row.className = "bubble-row user";
  const kind = options.kind || "";
  if (kind === "code_submission" || kind === "code_dump") {
    const bubble = document.createElement("div");
    bubble.className = "bubble code-submit-bubble";
    bubble.append(
      createTextElement(
        "p",
        "code-submit-badge",
        kind === "code_dump"
          ? "对话框贴了代码（应走手撕编辑器）"
          : options.fallback
            ? "代码提交（经对话通道）"
            : "代码提交",
      ),
    );
    const preview = document.createElement("pre");
    preview.className = "code-submit-preview";
    preview.textContent = text;
    bubble.append(preview);
    row.append(bubble);
  } else {
    row.append(createTextElement("div", "bubble", text));
  }

  const thought = createThoughtPanel();
  block.append(row, thought);
  container.append(block);
  container.scrollTop = container.scrollHeight;
  return thought;
}

function createThoughtPanel() {
  const thought = document.createElement("div");
  thought.className = "thought thought-panel";
  thought.hidden = true;
  const timeline = document.createElement("div");
  timeline.className = "thought-timeline";
  const text = document.createElement("div");
  thought.append(timeline, text);
  text.className = "thought-text";
  return thought;
}

function thoughtTextEl(panel) {
  return panel?.querySelector?.(".thought-text") || panel;
}

function thoughtTimelineEl(panel) {
  if (!panel?.querySelector) {
    return null;
  }
  let timeline = panel.querySelector(".thought-timeline");
  if (!timeline) {
    timeline = document.createElement("div");
    timeline.className = "thought-timeline";
    panel.prepend(timeline);
  }
  return timeline;
}

function upsertToolStep(panel, name, payload) {
  if (!panel) {
    return;
  }
  panel.hidden = false;
  const timeline = thoughtTimelineEl(panel);
  if (!timeline) {
    return;
  }
  const ui = TOOL_UI[name] || { label: name, start: `正在调用 ${name} 工具` };
  if (name !== "thinking") {
    timeline.querySelector('[data-tool-name="thinking"]')?.remove();
  }
  let row = timeline.querySelector(`[data-tool-name="${name}"]`);
  if (!row) {
    row = document.createElement("div");
    row.className = `tool-step tool-${name}`;
    row.dataset.toolName = name;
    const icon = document.createElement("span");
    icon.className = "tool-step-icon";
    icon.textContent = ui.label;
    const body = document.createElement("span");
    body.className = "tool-step-body";
    row.append(icon, body);
    timeline.append(row);
  }
  const body = row.querySelector(".tool-step-body");
  const result = payload?.result || "";
  const status = payload?.status || payload?.label || ui.start;
  body.textContent = result || status;
}

function sanitizeThought(text) {
  return text
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      if (/(建议你|总评|复习|岗位本质对照|知识建议|项目改良)/.test(line)) {
        return false;
      }
      if (/^检索面经[：:]/.test(trimmed)) {
        return false;
      }
      if (/^查代码：是（search_library）/.test(trimmed)) {
        return false;
      }
      return true;
    })
    .join("\n");
}

function looksLikeCodeDump(text) {
  const raw = String(text || "");
  if (/\[code_submission:/.test(raw) || /\[手撕提交/.test(raw)) {
    return true;
  }
  const lines = raw.split("\n").filter((line) => line.trim());
  if (lines.length < 6) {
    return false;
  }
  const hits = lines.filter((line) =>
    /^\s*(def |class |import |from \w+ import |@\w+)/.test(line),
  ).length;
  return hits >= 4;
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
    answerInput.placeholder =
      enabled && isCodeExerciseActive()
        ? CHAT_PLACEHOLDER_WITH_IDE
        : CHAT_PLACEHOLDER_DEFAULT;
  }
  if (sendAnswerButton) {
    sendAnswerButton.disabled = !enabled;
    sendAnswerButton.setAttribute("aria-disabled", String(!enabled));
  }
  if (askTeacherButton) {
    askTeacherButton.disabled = !enabled;
  }
  if (endInterviewButton) {
    endInterviewButton.disabled = !enabled;
  }
}

function isMockSession() {
  return interviewLive?.dataset.sessionId === MOCK_SESSION_ID;
}

function isCodeExerciseOpen() {
  return Boolean(codeExerciseState && codeIde && !codeIde.hidden);
}

function isCodeExerciseActive() {
  return isCodeExerciseOpen() && !codeExerciseState?.submitted;
}

function setIdeLayoutOpen(open) {
  liveWorkspace?.classList.toggle("has-code-ide", open);
  interviewPanel?.classList.toggle("has-code-ide", open);
  document.querySelector(".main-content")?.classList.toggle("has-code-ide", open);
}

function syncIdeChrome() {
  const submitted = Boolean(codeExerciseState?.submitted);
  const collapsed = Boolean(codeIde?.classList.contains("is-collapsed"));
  if (codeIdeCollapse) {
    codeIdeCollapse.classList.toggle("is-visible", submitted && !collapsed);
    codeIdeCollapse.hidden = !(submitted && !collapsed);
  }
  if (answerInput && !answerInput.disabled) {
    answerInput.placeholder = isCodeExerciseActive()
      ? CHAT_PLACEHOLDER_WITH_IDE
      : CHAT_PLACEHOLDER_DEFAULT;
  }
}

function closeCodeExercise(options = {}) {
  codeExerciseState = null;
  if (codeIde) {
    codeIde.hidden = true;
    codeIde.classList.remove("is-collapsed", "is-readonly");
    delete codeIde.dataset.ready;
    delete codeIde.dataset.exerciseId;
  }
  setIdeLayoutOpen(false);
  if (codeIdeStatus) {
    codeIdeStatus.replaceChildren();
  }
  if (answerInput && !answerInput.disabled) {
    answerInput.placeholder = CHAT_PLACEHOLDER_DEFAULT;
  }
  if (options.dispose && monacoEditor) {
    monacoEditor.dispose();
    monacoEditor = null;
    monacoCommandBound = false;
  }
}

function collapseCodeExercise() {
  if (!codeIde || !codeExerciseState) {
    return;
  }
  codeIde.classList.add("is-collapsed");
  if (codeIdeCollapsedText) {
    codeIdeCollapsedText.textContent = `已提交 · ${codeExerciseState.title || "手撕代码"}`;
  }
  syncIdeChrome();
}

function expandCodeExercise() {
  if (!codeIde) {
    return;
  }
  codeIde.classList.remove("is-collapsed");
  syncIdeChrome();
  window.requestAnimationFrame(() => {
    monacoEditor?.layout();
  });
}

function asExercisePayload(value) {
  if (!value || typeof value !== "object") {
    return null;
  }
  const title = fieldText(value.title).trim();
  const prompt = fieldText(
    value.prompt || value.description || value.question,
  ).trim();
  const starter = fieldText(
    value.starter || value.starter_code || value.code || "",
  );
  const exerciseId = fieldText(value.exercise_id || value.id || "").trim();
  if (!title && !prompt && !starter && !exerciseId) {
    return null;
  }
  return {
    exercise_id: exerciseId,
    title: title || "手撕代码",
    prompt: prompt || "请在编辑器中完成这道题。",
    language: fieldText(value.language || "python").trim() || "python",
    starter,
  };
}

function extractCodeExercise(eventName, data) {
  if (eventName === "code_exercise") {
    return asExercisePayload(data);
  }
  const name = fieldText(data?.name).trim();
  if (eventName !== "tool" || name !== "code_exercise") {
    return null;
  }
  const fromResultString = () => {
    if (typeof data.result !== "string" || !data.result.trim()) {
      return null;
    }
    try {
      return asExercisePayload(JSON.parse(data.result));
    } catch {
      return null;
    }
  };
  return (
    asExercisePayload(data) ||
    asExercisePayload(data.args) ||
    asExercisePayload(data.input) ||
    asExercisePayload(typeof data.result === "object" ? data.result : null) ||
    fromResultString()
  );
}

function configureMonacoEnvironment(cdn) {
  if (monacoWorkerUrl) {
    URL.revokeObjectURL(monacoWorkerUrl);
    monacoWorkerUrl = "";
  }
  const source = `
      self.MonacoEnvironment = { baseUrl: "${cdn}/" };
      importScripts("${cdn}/vs/base/worker/workerMain.js");
    `;
  monacoWorkerUrl = URL.createObjectURL(
    new Blob([source], { type: "text/javascript" }),
  );
  window.MonacoEnvironment = {
    getWorkerUrl() {
      return monacoWorkerUrl;
    },
  };
}

function injectMonacoLoader(cdn) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `${cdn}/vs/loader.js`;
    script.dataset.monacoLoader = "";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Monaco 加载器下载失败"));
    document.head.append(script);
  });
}

function waitForEditorMain(amdRequire, cdn) {
  return new Promise((resolve, reject) => {
    if (typeof amdRequire.config === "function") {
      amdRequire.config({
        paths: { vs: `${cdn}/vs` },
      });
    }
    const timer = window.setTimeout(() => {
      reject(new Error("Monaco 加载超时"));
    }, 45000);
    amdRequire(["vs/editor/editor.main"], () => {
      window.clearTimeout(timer);
      if (!window.monaco?.editor) {
        reject(new Error("Monaco 初始化失败"));
        return;
      }
      resolve();
    });
  });
}

function loadMonaco() {
  if (window.monaco?.editor) {
    return Promise.resolve(window.monaco);
  }
  if (monacoLoadPromise) {
    return monacoLoadPromise;
  }
  monacoLoadPromise = (async () => {
    let lastError = new Error("Monaco 加载失败");
    for (const cdn of MONACO_CDNS) {
      try {
        if (typeof window.require !== "function") {
          window.require = { paths: { vs: `${cdn}/vs` } };
          await injectMonacoLoader(cdn);
        }
        configureMonacoEnvironment(cdn);
        const amdRequire = window.require;
        if (typeof amdRequire !== "function") {
          throw new Error("Monaco 加载器未就绪");
        }
        await waitForEditorMain(amdRequire, cdn);
        return window.monaco;
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError;
  })();
  monacoLoadPromise.catch(() => {
    monacoLoadPromise = null;
  });
  return monacoLoadPromise;
}

function ensureMonacoTheme(monaco) {
  monaco.editor.defineTheme("interview-ide", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "4FC1FF", fontStyle: "bold" },
      { token: "keyword.python", foreground: "4FC1FF", fontStyle: "bold" },
      { token: "string", foreground: "CE9178" },
      { token: "comment", foreground: "6A9955" },
      { token: "number", foreground: "B5CEA8" },
    ],
    colors: {
      "editor.background": "#1E1E1E",
      "editor.foreground": "#E8E8E8",
      "editorLineNumber.foreground": "#8B8B8B",
      "editorLineNumber.activeForeground": "#F2F2F2",
      "editor.lineHighlightBackground": "#2A2A2A",
      "editorCursor.foreground": "#FFFFFF",
      "editor.selectionBackground": "#264F78",
      "editorIndentGuide.background": "#3B3B3B",
      "editorIndentGuide.activeBackground": "#707070",
    },
  });
}

function updateCodeMeta() {
  if (!codeIdeMeta || !monacoEditor) {
    return;
  }
  const model = monacoEditor.getModel();
  const position = monacoEditor.getPosition();
  const value = model ? model.getValue() : "";
  const lines = model ? model.getLineCount() : 0;
  const suffix = codeExerciseState?.submitted ? " · 已提交只读" : "";
  codeIdeMeta.textContent = `Ln ${position?.lineNumber || 1}, Col ${position?.column || 1}  ·  ${lines} 行  ·  ${value.length} 字符  ·  4 空格  ·  UTF-8  ·  Python${suffix}`;
}

function getEditorCode() {
  return monacoEditor?.getValue() ?? codeExerciseState?.starter ?? "";
}

async function openCodeExercise(raw) {
  const exercise = asExercisePayload(raw);
  if (!exercise || !codeIde || !monacoHost) {
    return;
  }
  if (
    monacoEditor &&
    codeExerciseState &&
    !codeExerciseState.submitted &&
    exercise.exercise_id &&
    codeExerciseState.exercise_id === exercise.exercise_id
  ) {
    codeIde.hidden = false;
    codeIde.dataset.exerciseId = exercise.exercise_id;
    setIdeLayoutOpen(true);
    codeIde.dataset.ready = "1";
    syncIdeChrome();
    return;
  }
  const seq = ++ideOpenSeq;
  codeExerciseState = {
    ...exercise,
    submitted: false,
    fallbackSubmit: false,
  };
  codeIde.hidden = false;
  codeIde.classList.remove("is-collapsed", "is-readonly");
  delete codeIde.dataset.ready;
  if (codeExerciseState.exercise_id) {
    codeIde.dataset.exerciseId = codeExerciseState.exercise_id;
  } else {
    delete codeIde.dataset.exerciseId;
  }
  setIdeLayoutOpen(true);
  if (codeIdeTitle) {
    codeIdeTitle.textContent = codeExerciseState.title;
  }
  if (codeIdePrompt) {
    codeIdePrompt.textContent = codeExerciseState.prompt;
  }
  if (codeIdeKicker) {
    const languageLabel =
      codeExerciseState.language.toLowerCase() === "python"
        ? "Python"
        : codeExerciseState.language;
    codeIdeKicker.textContent = `手撕代码 · ${languageLabel}`;
  }
  if (submitCodeButton) {
    submitCodeButton.disabled = false;
    submitCodeButton.textContent = "提交代码";
  }
  if (codeIdeStatus) {
    codeIdeStatus.replaceChildren();
  }
  syncIdeChrome();
  if (!monacoEditor) {
    monacoHost.classList.add("is-loading");
    monacoHost.textContent = "正在加载代码编辑器";
  }

  try {
    const monaco = await loadMonaco();
    if (seq !== ideOpenSeq) {
      return;
    }
    ensureMonacoTheme(monaco);
    const language =
      codeExerciseState.language.toLowerCase() === "python"
        ? "python"
        : "plaintext";
    if (!monacoEditor) {
      monacoHost.classList.remove("is-loading");
      monacoHost.replaceChildren();
      monacoEditor = monaco.editor.create(monacoHost, {
        value: codeExerciseState.starter,
        language,
        theme: "interview-ide",
        automaticLayout: true,
        fontSize: 15,
        lineHeight: 24,
        letterSpacing: 0.2,
        fontLigatures: true,
        fontFamily:
          'ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
        lineNumbers: "on",
        renderLineHighlight: "all",
        roundedSelection: false,
        scrollBeyondLastLine: false,
        minimap: { enabled: false },
        tabSize: 4,
        insertSpaces: true,
        detectIndentation: false,
        autoClosingBrackets: "always",
        autoClosingQuotes: "always",
        autoClosingDelete: "always",
        autoSurround: "languageDefined",
        matchBrackets: "always",
        autoIndent: "full",
        formatOnType: true,
        wrappingIndent: "indent",
        wordWrap: "on",
        padding: { top: 12, bottom: 12 },
        glyphMargin: false,
        folding: true,
        renderWhitespace: "selection",
        mouseWheelZoom: true,
        smoothScrolling: true,
        cursorBlinking: "smooth",
        bracketPairColorization: { enabled: true },
        guides: { bracketPairs: true, indentation: true },
        suggestOnTriggerCharacters: true,
        quickSuggestions: { other: true, comments: false, strings: false },
        acceptSuggestionOnEnter: "on",
        tabCompletion: "on",
        ariaLabel: "Python 代码编辑器",
      });
      monacoEditor.onDidChangeCursorPosition(updateCodeMeta);
      monacoEditor.onDidChangeModelContent(updateCodeMeta);
    } else {
      const model = monacoEditor.getModel();
      if (model) {
        monaco.editor.setModelLanguage(model, language);
        model.setValue(codeExerciseState.starter);
      }
    }
    monacoEditor.updateOptions({ readOnly: false });
    if (!monacoCommandBound) {
      monacoEditor.addCommand(
        monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter,
        () => {
          void submitCodeExercise();
        },
      );
      monacoCommandBound = true;
    }
    window.requestAnimationFrame(() => {
      monacoEditor?.layout();
    });
    updateCodeMeta();
    codeIde.dataset.ready = "1";
    if (document.activeElement !== answerInput) {
      monacoEditor.focus();
    }
  } catch (error) {
    console.error("Failed to open Monaco editor", error);
    monacoHost.classList.remove("is-loading");
    if (codeIdeStatus) {
      codeIdeStatus.replaceChildren(
        createTextElement(
          "p",
          "flash error",
          "编辑器加载失败，请检查网络后刷新重试。",
        ),
      );
    }
  }
}

function appendCodeSubmissionBubble(code, options) {
  return appendUserBlock(code, options?.container || chatLog, {
    kind: "code_submission",
    fallback: Boolean(options?.fallback),
  });
}

function markCodeSubmitted(fallback) {
  if (!codeExerciseState) {
    return;
  }
  codeExerciseState.submitted = true;
  codeExerciseState.fallbackSubmit = fallback;
  monacoEditor?.updateOptions({ readOnly: true });
  codeIde?.classList.add("is-readonly");
  if (submitCodeButton) {
    submitCodeButton.disabled = true;
    submitCodeButton.textContent = "已提交";
  }
  updateCodeMeta();
  collapseCodeExercise();
}

async function consumeCodeSubmissionResponse(response, thoughtNode) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const data = await response.json().catch(() => ({}));
    const nextQuestion = data.question || data.text || data.next_question;
    if (nextQuestion) {
      appendInterviewerBubble(
        nextQuestion,
        data.direction_id || interviewLive.dataset.currentDirectionId,
      );
    }
    return;
  }
  const turn = await consumeTurnStream(response, thoughtNode);
  if (turn.question) {
    appendInterviewerBubble(turn.question, turn.directionId);
  }
}

async function submitCodeExercise() {
  if (
    !codeExerciseState ||
    codeExerciseState.submitted ||
    codeSubmitting ||
    turnInFlight ||
    endingInFlight ||
    sessionHasEnded()
  ) {
    return;
  }
  const sessionId = interviewLive?.dataset.sessionId;
  const code = getEditorCode();
  if (!sessionId) {
    return;
  }
  if (!code.trim()) {
    codeIdeStatus?.replaceChildren(
      createTextElement("p", "flash error", "请先在编辑器中写下代码再提交。"),
    );
    return;
  }

  codeSubmitting = true;
  if (submitCodeButton) {
    submitCodeButton.disabled = true;
  }
  setTurnLoading(true);
  codeIdeStatus?.replaceChildren();

  if (isMockSession()) {
    const thoughtNode = appendCodeSubmissionBubble(code, { fallback: true });
    thoughtNode.hidden = false;
    thoughtNode.textContent = "本地 mock：提交接口未调用，面试可继续。";
    markCodeSubmitted(true);
    appendInterviewerBubble(
      "代码已收到。可以说一下你为什么先减最大值再做归一化吗？",
      interviewLive.dataset.currentDirectionId || "d1",
    );
    codeSubmitting = false;
    setTurnLoading(false);
    answerInput?.focus();
    return;
  }

  try {
    let fallback = false;
    let response = await fetch(`/api/sessions/${sessionId}/code-submissions`, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        exercise_id: codeExerciseState.exercise_id,
        code,
      }),
    });

    if (response.status === 404 || response.status === 405) {
      fallback = true;
      response = await fetch(`/api/sessions/${sessionId}/turns`, {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          answer: `【代码提交】${
            codeExerciseState.exercise_id
              ? ` exercise_id=${codeExerciseState.exercise_id}`
              : ""
          }\n\n${code}`,
        }),
      });
    }

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(apiErrorMessage(data, "代码提交失败，请稍后重试。"));
    }

    const thoughtNode = appendCodeSubmissionBubble(code, { fallback });
    markCodeSubmitted(fallback);
    await consumeCodeSubmissionResponse(response, thoughtNode);
    codeSubmitting = false;
    setTurnLoading(false);
    answerInput?.focus();
  } catch (error) {
    console.error("Failed to submit code exercise", error);
    codeSubmitting = false;
    if (submitCodeButton && !codeExerciseState?.submitted) {
      submitCodeButton.disabled = false;
    }
    setTurnLoading(false);
    codeIdeStatus?.replaceChildren(
      createTextElement(
        "p",
        "flash error",
        error instanceof Error ? error.message : "代码提交失败，请稍后重试。",
      ),
    );
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
  if (askTeacherButton) {
    askTeacherButton.disabled = isLoading || sessionHasEnded();
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

function fillDirectionList(listEl, directions, currentId) {
  if (!listEl) {
    return;
  }
  listEl.replaceChildren(
    ...(directions || []).map((direction) => {
      const item = document.createElement("li");
      item.className = "direction-item";
      item.dataset.directionId = direction.id;
      if (currentId && direction.id === currentId) {
        item.classList.add("current");
      }
      item.append(
        createTextElement("p", "direction-title", direction.title),
        createTextElement("p", "direction-goal", direction.goal),
      );
      return item;
    }),
  );
}

function renderSessionDirections(snapshot) {
  const session = snapshot?.session || snapshot || {};
  const directions = session.directions || snapshot?.directions || [];
  if (!Array.isArray(directions) || directions.length === 0) {
    return null;
  }
  const section = document.createElement("section");
  section.className = "directions-block review-directions";
  section.setAttribute("aria-labelledby", "review-directions-title");
  section.append(
    createTextElement("p", "section-label", "本场固定方向"),
    createTextElement("h2", "", "接下来会沿这些链路逐步深挖"),
  );
  section.querySelector("h2").id = "review-directions-title";
  const list = document.createElement("ol");
  list.className = "direction-list";
  fillDirectionList(list, directions, session.current_direction_id);
  section.append(list);
  return section;
}

function renderStartedSession(session) {
  fillDirectionList(directionList, session.directions, "d1");
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
  closeCodeExercise({ dispose: true });
  setComposerEnabled(true);
  setTurnLoading(false);
  interviewStart.hidden = true;
  interviewLive.hidden = false;
  interviewLive.focus({ preventScroll: true });
  interviewLive.scrollIntoView({ behavior: "smooth", block: "start" });
  if (session.code_exercise) {
    void openCodeExercise(session.code_exercise);
  }
}

function applySseEvent(eventName, data, thoughtNode, state) {
  const exercise = extractCodeExercise(eventName, data);
  if (eventName === "code_exercise" || fieldText(data?.name).trim() === "code_exercise") {
    if (exercise) {
      state.receivedExercise = true;
      void openCodeExercise(exercise);
    } else if (isCodeExerciseOpen()) {
      state.receivedExercise = true;
    }
    if (eventName === "tool") {
      upsertToolStep(thoughtNode, "code_exercise", {
        result: sanitizeThought(data.result || "已打开手撕题"),
      });
    }
    return;
  }
  if (eventName === "tool_start") {
    const name = data.name || "search_library";
    upsertToolStep(thoughtNode, name, {
      status: data.label || TOOL_UI[name]?.start || `正在调用 ${name} 工具`,
    });
    chatLog.scrollTop = chatLog.scrollHeight;
    return;
  }
  if (eventName === "thought_delta") {
    thoughtNode.hidden = false;
    thoughtNode.querySelector('[data-tool-name="thinking"]')?.remove();
    thoughtTextEl(thoughtNode).textContent += sanitizeThought(data.text || "");
    chatLog.scrollTop = chatLog.scrollHeight;
    return;
  }
  if (eventName === "tool") {
    const toolName = data.name || "code_inspect";
    upsertToolStep(thoughtNode, toolName, {
      result: sanitizeThought(data.result || ""),
    });
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
    receivedExercise: false,
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
  thoughtNode.hidden = false;
  upsertToolStep(thoughtNode, "thinking", {
    status: "正在组织这一轮评价",
  });
  const thinkingRow = thoughtNode.querySelector('[data-tool-name="thinking"]');
  if (thinkingRow) {
    thinkingRow.classList.add("tool-thinking");
  }
  answerInput.value = "";

  if (isMockSession()) {
    thoughtNode.hidden = false;
    thoughtNode.textContent = "本地 mock：对话未请求后端。";
    appendInterviewerBubble(
      "可以边写边问。Python 列表推导、math.exp 都可以用；注意溢出时先减去最大值。",
      interviewLive.dataset.currentDirectionId || "d1",
    );
    answerInput.focus();
    return;
  }

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
    if (!turn.question && !turn.receivedExercise && !isCodeExerciseOpen()) {
      throw new Error("未收到下一问，请稍后重试。");
    }
    if (turn.question) {
      appendInterviewerBubble(turn.question, turn.directionId);
    }
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
    // 手撕编辑器打开时对话失败不应关掉 IDE，占位符继续提示可边写边问
    syncIdeChrome();
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

function fillThoughtFromTurn(thoughtNode, body, meta) {
  thoughtNode.hidden = false;
  const items = Array.isArray(meta) ? meta : [];
  const seen = new Set();
  for (const item of items) {
    const name = item?.name || "";
    if (!name || seen.has(name) || name === "thinking") {
      continue;
    }
    seen.add(name);
    let result = "";
    if (name === "search_library") {
      result = "已检索面经";
    } else if (name === "code_exercise") {
      result = String(item.result || "已打开手撕题");
    } else if (name === "code_inspect") {
      result = "已核对仓库";
    }
    upsertToolStep(thoughtNode, name, { result });
  }
  thoughtTextEl(thoughtNode).textContent = sanitizeThought(body || "");
}

function renderTurnsInto(container, turns, helps) {
  container.replaceChildren();
  let thoughtNode = null;
  const leftover = [...(helps || [])];
  for (const turn of turns || []) {
    if (turn.role === "interviewer") {
      appendInterviewerBubble(turn.body, turn.direction_id, container);
      thoughtNode = null;
      const remaining = [];
      leftover.forEach((item) => {
        if (item.question === turn.body) {
          appendTeacherHint(item.hint, container);
        } else {
          remaining.push(item);
        }
      });
      leftover.splice(0, leftover.length, ...remaining);
    } else if (turn.role === "user") {
      const meta = turn.meta || {};
      const kind =
        meta.kind === "code_submission"
          ? "code_submission"
          : looksLikeCodeDump(turn.body)
            ? "code_dump"
            : "";
      thoughtNode = appendUserBlock(turn.body, container, { kind });
    } else if (turn.role === "thought" && thoughtNode) {
      fillThoughtFromTurn(thoughtNode, turn.body || "", turn.meta);
      thoughtNode = null;
    }
  }
  leftover.forEach((item) => appendTeacherHint(item.hint, container));
}

function renderEndedView(snapshot, container) {
  const chatPane = document.createElement("div");
  chatPane.className = "ended-pane ended-pane-chat";
  chatPane.setAttribute("data-ended-chat", "1");
  renderTurnsInto(chatPane, snapshot.turns || [], snapshot.helps || []);

  const divider = document.createElement("div");
  divider.className = "ended-view-divider";
  divider.setAttribute("aria-hidden", "true");

  const reportPane = document.createElement("div");
  reportPane.className = "ended-pane ended-pane-report";
  reportPane.setAttribute("data-ended-report", "1");
  renderReportTabs(snapshot.report?.text || "", reportPane);

  const main = document.createElement("div");
  main.className = "ended-view-main";
  main.append(chatPane, divider, reportPane);

  container.classList.add("ended-view");
  const directions = renderSessionDirections(snapshot);
  if (directions) {
    container.replaceChildren(directions, main);
    document.querySelector("#interview-live .directions-block")?.setAttribute("hidden", "");
  } else {
    container.replaceChildren(main);
  }
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
  const main = document.createElement("div");
  main.className = "ended-view-main";
  main.append(chatPane, divider, reportPane);
  endedView.append(main);
  chatLog.replaceWith(endedView);
  closeCodeExercise({ dispose: true });
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
  const loading = createLoadingState("生成评价报告中");
  loading.classList.add("report-generating");
  reportPane.replaceChildren(loading);

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

const interviewerRoot = document.querySelector("#interviewer-agent-root");
let interviewerAgentSeq = 0;
let interviewerSelectedRole = "";

function makePromptBlock(text) {
  const pre = document.createElement("pre");
  pre.className = "prompt-block";
  pre.textContent = text || "";
  return pre;
}

function renderInterviewerAgent(data) {
  if (!interviewerRoot) {
    return;
  }
  const root = document.createElement("div");
  root.className = "interviewer-agent";

  const switcher = document.createElement("div");
  switcher.className = "library-kind-switch";
  switcher.setAttribute("role", "tablist");
  switcher.setAttribute("aria-label", "选择岗位人设");
  (data.roles || []).forEach((role) => {
    const button = document.createElement("button");
    button.className = "kind-btn";
    button.type = "button";
    button.dataset.role = role.id;
    button.textContent = role.label;
    if (role.id === data.selected_role) {
      button.classList.add("active");
    }
    button.addEventListener("click", () => {
      loadInterviewerAgent(role.id);
    });
    switcher.append(button);
  });
  root.append(switcher);

  const selected = (data.roles || []).find((item) => item.id === data.selected_role) || {};
  const stats = document.createElement("div");
  stats.className = "agent-stats";
  [
    ["岗位", selected.label || data.role_label || ""],
    ["JD", String(selected.jd_count ?? "—")],
    ["面经", String(selected.interview_count ?? "—")],
  ].forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "agent-stat";
    card.append(
      createTextElement("p", "agent-stat-label", label),
      createTextElement("p", "agent-stat-value", value),
    );
    stats.append(card);
  });
  root.append(stats);
  if (selected.one_liner) {
    root.append(createTextElement("p", "section-copy", selected.one_liner));
  }

  const personaSection = document.createElement("section");
  personaSection.className = "divider-section";
  personaSection.append(
    createTextElement("p", "section-label", "岗位人设"),
    createTextElement("h2", "", `${selected.label || ""} · 全文`),
    makePromptBlock(selected.persona_prompt || data.prompts?.role || ""),
  );
  root.append(personaSection);

  const promptSection = document.createElement("section");
  promptSection.className = "divider-section";
  promptSection.append(
    createTextElement("p", "section-label", "System prompt"),
    createTextElement("h2", "", "面中实际注入的完整系统提示"),
    createTextElement(
      "p",
      "section-copy",
      "下面是 app.agent.build_turn_system_prompt 的原文，含 interviewer.md、该岗人设文件、本场占位项目和工具契约。",
    ),
    makePromptBlock(data.system_prompt || ""),
  );
  root.append(promptSection);

  const skillSection = document.createElement("section");
  skillSection.className = "divider-section";
  skillSection.append(
    createTextElement("p", "section-label", "Skill"),
    createTextElement("h2", "", "方向规划、话题锁、工具策略"),
  );
  (data.skills || []).forEach((skill) => {
    skillSection.append(createTextElement("h3", "agent-subhead", skill.name || skill.id));
    skillSection.append(createTextElement("p", "section-copy", skill.text || ""));
    skillSection.append(createTextElement("p", "field-hint", `来源：${skill.source || ""}`));
  });
  root.append(skillSection);

  const toolSection = document.createElement("section");
  toolSection.className = "divider-section";
  toolSection.append(
    createTextElement("p", "section-label", "工具"),
    createTextElement("h2", "", "与代码 INTERVIEW_TURN_TOOLS 一致"),
  );
  (data.tools || []).forEach((tool) => {
    const when = (data.when_to_call && data.when_to_call[tool.name]) || "";
    toolSection.append(createTextElement("h3", "agent-subhead", tool.name || ""));
    toolSection.append(createTextElement("p", "section-copy", tool.description || ""));
    if (when) {
      toolSection.append(createTextElement("p", "section-copy", `何时调用：${when}`));
    }
    toolSection.append(makePromptBlock(JSON.stringify(tool.parameters || {}, null, 2)));
  });
  root.append(toolSection);

  const ruleSection = document.createElement("section");
  ruleSection.className = "divider-section";
  ruleSection.append(
    createTextElement("p", "section-label", "运行规则"),
    createTextElement("h2", "", "从 app/agent.py 读出的硬约束"),
  );
  const list = document.createElement("ul");
  list.className = "agent-rule-list";
  (data.runtime_rules || []).forEach((rule) => {
    const item = document.createElement("li");
    item.append(createTextElement("p", "section-copy", rule.text || ""));
    item.append(createTextElement("p", "field-hint", `${rule.source || ""} · ${JSON.stringify(rule.value)}`));
    list.append(item);
  });
  ruleSection.append(list);
  root.append(ruleSection);

  const filesSection = document.createElement("section");
  filesSection.className = "divider-section";
  filesSection.append(
    createTextElement("p", "section-label", "Prompt 原件"),
    createTextElement("h2", "", "interviewer.md"),
    makePromptBlock(data.prompts?.interviewer || ""),
  );
  root.append(filesSection);

  interviewerRoot.replaceChildren(root);
}

function loadInterviewerAgent(role) {
  if (!interviewerRoot) {
    return;
  }
  const source = window.INTERVIEWER_AGENT;
  if (!source || !Array.isArray(source.roles) || !source.roles.length) {
    interviewerRoot.replaceChildren(
      createTextElement("p", "flash error", "面试官定义未加载"),
    );
    return;
  }
  const nextRole = role || interviewerSelectedRole || source.selected_role;
  const selected = source.roles.find((item) => item.id === nextRole) || source.roles[0];
  interviewerSelectedRole = selected.id;
  renderInterviewerAgent({
    ...source,
    selected_role: selected.id,
    role_label: selected.label,
    system_prompt: selected.system_prompt || source.system_prompt,
    prompts: {
      ...(source.prompts || {}),
      role: selected.persona_prompt || source.prompts?.role,
    },
  });
}

async function loadRoleOptions() {
  const select = document.querySelector("#role");
  if (!select) {
    return;
  }
  try {
    const response = await fetch("/api/roles", { headers: { Accept: "application/json" } });
    const data = await response.json().catch(() => ({}));
    const roles = Array.isArray(data.roles) ? data.roles : [];
    if (!roles.length) {
      return;
    }
    const current = select.value;
    select.replaceChildren();
    roles.forEach((role) => {
      const option = document.createElement("option");
      option.value = role.id;
      option.textContent = role.label;
      select.append(option);
      ROLE_LABELS[role.id] = role.label;
    });
    if ([...select.options].some((item) => item.value === current)) {
      select.value = current;
    }
  } catch (error) {
    console.error("Failed to load roles", error);
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
  if (panelName === "interviewer") {
    loadInterviewerAgent();
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
async function requestTeacherHint() {
  const sessionId = interviewLive?.dataset.sessionId;
  const question = interviewLive?.dataset.currentQuestion || "";
  if (!sessionId || turnInFlight || sessionHasEnded()) {
    return;
  }
  setTurnLoading(true);
  if (turnStatus) {
    turnStatus.replaceChildren(createLoadingState("老师正在看这道题"));
  }
  try {
    const response = await fetch(`/api/sessions/${sessionId}/hints`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(apiErrorMessage(data, "老师暂时无法给出提示"));
    }
    appendTeacherHint(data.hint || "");
    setTurnLoading(false);
    answerInput?.focus();
  } catch (error) {
    console.error("Teacher hint failed", error);
    setTurnLoading(false);
    turnStatus?.replaceChildren(
      createTextElement(
        "p",
        "flash error",
        error instanceof Error ? error.message : "老师暂时无法给出提示",
      ),
    );
  }
}

chatForm?.addEventListener("submit", submitTurn);
askTeacherButton?.addEventListener("click", () => {
  void requestTeacherHint();
});
endInterviewButton?.addEventListener("click", () => {
  void submitEndInterview();
});
submitCodeButton?.addEventListener("click", () => {
  void submitCodeExercise();
});
codeIdeExpand?.addEventListener("click", () => {
  expandCodeExercise();
});
codeIdeCollapse?.addEventListener("click", () => {
  collapseCodeExercise();
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

function bootMockCodeExercise() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("mock_code") !== "1") {
    return;
  }
  renderStartedSession({
    id: MOCK_SESSION_ID,
    directions: [
      {
        id: "d1",
        title: "手撕代码",
        goal: "在编辑器完成题目，同时可向面试官提问。",
      },
      { id: "d2", title: "实现核对", goal: "提交后继续追问实现细节。" },
      { id: "d3", title: "岗位对照", goal: "对照岗位能力评估实现。" },
    ],
    first_question: "先在编辑器里完成这道题。写的时候可以直接问我语法或 API。",
    clone_ok: true,
    code_exercise: {
      exercise_id: "mock-softmax",
      title: "实现 Softmax",
      prompt:
        "实现 Softmax.__call__(xs)，输入 list[float]，返回归一化后的概率。请使用数值稳定写法：先减最大值再 exp。写的时候可以问我语法。",
      language: "python",
      starter:
        "class Softmax:\n    def __init__(self):\n        pass\n\n    def __call__(self, xs):\n        # TODO: 数值稳定的 softmax\n        return xs\n",
    },
  });
}

window.__interviewHelper = {
  openCodeExercise,
  extractCodeExercise,
  applyDemoPreset,
  handleDemoFill,
  loadDemoCatalog,
  getDemoCatalog() {
    return demoCatalog;
  },
  getEditor() {
    return monacoEditor;
  },
  getCode() {
    return getEditorCode();
  },
  getExerciseState() {
    return codeExerciseState
      ? {
          exercise_id: codeExerciseState.exercise_id,
          title: codeExerciseState.title,
          language: codeExerciseState.language,
          submitted: codeExerciseState.submitted,
          fallbackSubmit: codeExerciseState.fallbackSubmit,
        }
      : null;
  },
  tokenizePython(code) {
    return window.monaco?.editor.tokenize(code, "python") || [];
  },
};

document.querySelector("#demo-fill")?.addEventListener("click", () => {
  void handleDemoFill();
});
void loadDemoCatalog();
void loadRoleOptions();
bootMockCodeExercise();
