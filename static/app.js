const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));
const sampleLibrary = document.querySelector("#sample-library");
const sessionForm = document.querySelector("#session-form");
const sessionStatus = document.querySelector("#session-status");
const interviewStart = document.querySelector("#interview-start");
const interviewLive = document.querySelector("#interview-live");
const directionList = document.querySelector("#direction-list");
const firstQuestion = document.querySelector("#first-question");
const cloneNotice = document.querySelector("#clone-notice");
let libraryLoaded = false;
let libraryLoading = false;

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

function renderStartedSession(session) {
  directionList.replaceChildren(
    ...session.directions.map((direction) => {
      const item = document.createElement("li");
      item.className = "direction-item";
      item.append(
        createTextElement("p", "direction-title", direction.title),
        createTextElement("p", "direction-goal", direction.goal),
      );
      return item;
    }),
  );
  firstQuestion.textContent = session.first_question;
  cloneNotice.hidden = session.clone_ok;
  cloneNotice.textContent = session.clone_ok
    ? ""
    : session.clone_error || "代码仓库暂不可用，面试仍可继续。";
  interviewLive.dataset.sessionId = session.id;
  interviewStart.hidden = true;
  interviewLive.hidden = false;
  interviewLive.focus({ preventScroll: true });
  interviewLive.scrollIntoView({ behavior: "smooth", block: "start" });
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
