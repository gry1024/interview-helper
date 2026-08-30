const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));
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
let libraryLoaded = false;
let libraryLoading = false;
let turnInFlight = false;

function createTextElement(tagName, className, text) {
  const element = document.createElement(tagName);
  element.className = className;
  element.textContent = text;
  return element;
}

function safeSourceUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function renderSample(sample) {
  const sourceUrl = safeSourceUrl(sample.source_url);
  if (!sourceUrl || !sample.source_name) {
    return null;
  }

  const article = document.createElement("article");
  article.className = "sample-item";
  article.append(createTextElement("p", "sample-company", sample.company));

  const heading = document.createElement("div");
  heading.className = "sample-heading";
  heading.append(createTextElement("h3", "", sample.role));

  const sourceLink = createTextElement(
    "a",
    "source-link",
    `查看来源 · ${sample.source_name}`,
  );
  sourceLink.href = sourceUrl;
  sourceLink.target = "_blank";
  sourceLink.rel = "noopener noreferrer";
  heading.append(sourceLink);

  article.append(heading);
  article.append(createTextElement("p", "sample-text", sample.text));
  return article;
}

function renderSampleGroup(title, samples) {
  const section = document.createElement("section");
  section.className = "library-section";
  section.append(createTextElement("h2", "library-title", title));

  const sourcedSamples = samples.map(renderSample).filter(Boolean);
  if (sourcedSamples.length === 0) {
    section.append(createTextElement("p", "empty-state", "暂无可核验样本"));
  } else {
    section.append(...sourcedSamples);
  }
  return section;
}

async function loadSampleLibrary() {
  if (!sampleLibrary || libraryLoaded || libraryLoading) {
    return;
  }

  libraryLoading = true;
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

    sampleLibrary.replaceChildren(
      renderSampleGroup("真实 JD", data.jds),
      renderSampleGroup("真实面经", data.interviews),
    );
    libraryLoaded = true;
  } catch (error) {
    console.error("Failed to load sourced samples", error);
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
    const loading = document.createElement("div");
    loading.className = "loading-state";
    loading.setAttribute("role", "status");
    const spinner = document.createElement("span");
    spinner.className = "spinner";
    spinner.setAttribute("aria-hidden", "true");
    loading.append(spinner, document.createTextNode("正在确定方向并准备代码仓库"));
    sessionStatus.replaceChildren(loading);
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

function appendInterviewerBubble(text, directionId) {
  const row = document.createElement("div");
  row.className = "bubble-row interviewer";
  if (directionId) {
    row.dataset.directionId = directionId;
  }
  row.append(createTextElement("div", "bubble", text));
  chatLog.append(row);
  chatLog.scrollTop = chatLog.scrollHeight;
  setCurrentDirection(directionId);
  return row;
}

function appendUserBlock(text) {
  const block = document.createElement("div");
  block.className = "user-block";

  const row = document.createElement("div");
  row.className = "bubble-row user";
  row.append(createTextElement("div", "bubble", text));

  const thought = document.createElement("div");
  thought.className = "thought";
  thought.hidden = true;

  block.append(row, thought);
  chatLog.append(block);
  chatLog.scrollTop = chatLog.scrollHeight;
  return thought;
}

function sanitizeThought(text) {
  return text
    .split("\n")
    .filter((line) => !/(建议你|总评|复习|岗位本质对照)/.test(line))
    .join("\n");
}

function setTurnLoading(isLoading) {
  turnInFlight = isLoading;
  if (chatForm) {
    chatForm.setAttribute("aria-busy", String(isLoading));
  }
  if (sendAnswerButton) {
    sendAnswerButton.disabled = isLoading;
    sendAnswerButton.setAttribute("aria-disabled", String(isLoading));
  }
  if (endInterviewButton) {
    endInterviewButton.disabled = true;
  }
  if (!turnStatus) {
    return;
  }
  if (isLoading) {
    const loading = document.createElement("div");
    loading.className = "loading-state";
    loading.setAttribute("role", "status");
    const spinner = document.createElement("span");
    spinner.className = "spinner";
    spinner.setAttribute("aria-hidden", "true");
    loading.append(spinner, document.createTextNode("面试官正在思考"));
    turnStatus.replaceChildren(loading);
  } else {
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

function parseSseBlock(block, thoughtNode, state) {
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
  applySseEvent(eventName, data, thoughtNode, state);
}

async function consumeTurnStream(response, thoughtNode) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const state = {
    question: "",
    directionId: interviewLive.dataset.currentDirectionId || "d1",
    directionDone: false,
  };

  const consumeBuffer = (raw, flushRemainder) => {
    const chunks = raw.split("\n\n");
    const remainder = flushRemainder ? "" : chunks.pop() || "";
    for (const chunk of chunks) {
      if (chunk.trim()) {
        parseSseBlock(chunk, thoughtNode, state);
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

  return state;
}

async function submitTurn(event) {
  event.preventDefault();
  if (turnInFlight) {
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
