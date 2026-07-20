"use strict";

const token = new URLSearchParams(window.location.search).get("token") || "";
const elements = {
  canvas: document.getElementById("writingCanvas"),
  clearButton: document.getElementById("clearButton"),
  closeWriterDialog: document.getElementById("closeWriterDialog"),
  connectionState: document.getElementById("connectionState"),
  inputSource: document.getElementById("inputSource"),
  nextButton: document.getElementById("nextButton"),
  pointCount: document.getElementById("pointCount"),
  positionInput: document.getElementById("positionInput"),
  positionTotal: document.getElementById("positionTotal"),
  previousButton: document.getElementById("previousButton"),
  progressBar: document.getElementById("progressBar"),
  progressText: document.getElementById("progressText"),
  sampleState: document.getElementById("sampleState"),
  saveButton: document.getElementById("saveButton"),
  saveNextButton: document.getElementById("saveNextButton"),
  searchInput: document.getElementById("searchInput"),
  strokeCount: document.getElementById("strokeCount"),
  targetCharacter: document.getElementById("targetCharacter"),
  targetMetadata: document.getElementById("targetMetadata"),
  toast: document.getElementById("toast"),
  undoButton: document.getElementById("undoButton"),
  variantSelect: document.getElementById("variantSelect"),
  writerButton: document.getElementById("writerButton"),
  writerDialog: document.getElementById("writerDialog"),
  writerForm: document.getElementById("writerForm"),
  writerIdInput: document.getElementById("writerIdInput"),
  writerLabel: document.getElementById("writerLabel"),
  writerNameInput: document.getElementById("writerNameInput"),
};

const state = {
  activePointerId: null,
  completedCharacters: new Set(),
  currentIndex: 0,
  entries: [],
  loadSequence: 0,
  pointerTypes: new Set(),
  recordingOrigin: performance.now(),
  recordingOffset: 0,
  sampleState: "missing",
  saveQueue: Promise.resolve(),
  strokes: [],
  variant: 1,
  writerId: "",
  writerName: "",
};

const context = elements.canvas.getContext("2d", { alpha: false });
let toastTimer = 0;

function apiUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  if (token) url.searchParams.set("token", token);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  return url;
}

async function apiRequest(path, options = {}, params = {}) {
  const response = await fetch(apiUrl(path, params), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(value.error?.message || `请求失败 (${response.status})`);
  }
  return value;
}

function setConnection(kind, label) {
  elements.connectionState.className = `connection ${kind}`;
  elements.connectionState.querySelector("span:last-child").textContent = label;
}

function showToast(message, isError = false) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.className = `toast visible${isError ? " error" : ""}`;
  toastTimer = window.setTimeout(() => {
    elements.toast.className = "toast";
  }, 2200);
}

function currentEntry() {
  return state.entries[state.currentIndex];
}

function updateTarget() {
  const entry = currentEntry();
  if (!entry) return;
  elements.targetCharacter.textContent = entry.character;
  const rank = entry.frequency_rank ? `字频 ${entry.frequency_rank}` : entry.category;
  const strokes = entry.stroke_count ? `${entry.stroke_count} 画` : "笔画数未知";
  elements.targetMetadata.textContent = `${entry.unicode} · ${rank} · ${strokes}`;
  elements.positionInput.value = String(state.currentIndex + 1);
  elements.positionInput.max = String(state.entries.length);
  elements.positionTotal.textContent = `/ ${state.entries.length}`;
}

function updateProgress(progress) {
  if (!progress) return;
  state.completedCharacters = new Set(progress.completed_characters || []);
  elements.progressBar.max = progress.total;
  elements.progressBar.value = progress.completed;
  elements.progressText.textContent = `${progress.completed} / ${progress.total}`;
}

function updateStats() {
  const pointTotal = state.strokes.reduce(
    (sum, stroke) => sum + stroke.points.length,
    0,
  );
  elements.strokeCount.textContent = `笔画 ${state.strokes.length}`;
  elements.pointCount.textContent = `轨迹点 ${pointTotal}`;
  const sources = [...state.pointerTypes];
  elements.inputSource.textContent = `输入 ${sources.length ? sources.join("+") : "--"}`;
  elements.undoButton.disabled = state.strokes.length === 0;
  elements.clearButton.disabled = state.strokes.length === 0;
  elements.saveButton.disabled = pointTotal < 2;
  elements.saveNextButton.disabled = pointTotal < 2;
}

function setSampleState(value) {
  state.sampleState = value;
  const labels = {
    missing: "尚未采集",
    draft: "草稿已保存",
    complete: "已完成",
    saving: "正在保存",
  };
  elements.sampleState.textContent = labels[value] || value;
}

function resizeCanvas() {
  const rect = elements.canvas.getBoundingClientRect();
  const ratio = Math.min(window.devicePixelRatio || 1, 2.5);
  const width = Math.max(1, Math.round(rect.width * ratio));
  const height = Math.max(1, Math.round(rect.height * ratio));
  if (elements.canvas.width !== width || elements.canvas.height !== height) {
    elements.canvas.width = width;
    elements.canvas.height = height;
  }
  drawCanvas();
}

function drawGrid(width, height) {
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, height);
  context.save();
  context.strokeStyle = "#d7dede";
  context.lineWidth = Math.max(1, width / 700);
  context.setLineDash([width / 55, width / 75]);
  context.beginPath();
  context.moveTo(width / 2, 0);
  context.lineTo(width / 2, height);
  context.moveTo(0, height / 2);
  context.lineTo(width, height / 2);
  context.moveTo(0, 0);
  context.lineTo(width, height);
  context.moveTo(width, 0);
  context.lineTo(0, height);
  context.stroke();
  context.restore();
}

function drawStroke(stroke, width, height) {
  if (!stroke.points.length) return;
  if (stroke.points.length === 1) {
    const point = stroke.points[0];
    context.beginPath();
    context.fillStyle = "#172326";
    context.arc(point.x * width, point.y * height, 2.4, 0, Math.PI * 2);
    context.fill();
    return;
  }
  for (let index = 1; index < stroke.points.length; index += 1) {
    const previous = stroke.points[index - 1];
    const current = stroke.points[index];
    context.beginPath();
    context.moveTo(previous.x * width, previous.y * height);
    context.lineTo(current.x * width, current.y * height);
    context.strokeStyle = "#172326";
    context.lineWidth = 2.2 + ((previous.pressure + current.pressure) / 2) * 3.2;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.stroke();
  }
}

function drawCanvas() {
  const width = elements.canvas.width;
  const height = elements.canvas.height;
  drawGrid(width, height);
  state.strokes.forEach((stroke) => drawStroke(stroke, width, height));
}

function normalizedPoint(event) {
  const rect = elements.canvas.getBoundingClientRect();
  const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
  const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
  const pointerType = event.pointerType || "touch";
  const source = pointerType === "pen" ? "pen" : pointerType === "mouse" ? "mouse" : "touch";
  const pressure = event.pressure > 0 ? event.pressure : 0.5;
  return {
    x,
    y,
    t_ms: state.recordingOffset + Math.max(0, Math.round(performance.now() - state.recordingOrigin)),
    pressure,
    x_tilt: Number(event.tiltX || 0),
    y_tilt: Number(event.tiltY || 0),
    rotation: Number(event.twist || 0),
    tangential_pressure: Number(event.tangentialPressure || 0),
    source,
  };
}

function appendPointerEvents(event) {
  const stroke = state.strokes[state.strokes.length - 1];
  if (!stroke) return;
  const events = typeof event.getCoalescedEvents === "function"
    ? event.getCoalescedEvents()
    : [event];
  const samples = events.length ? events : [event];
  samples.forEach((sample) => {
    const point = normalizedPoint(sample);
    const previous = stroke.points[stroke.points.length - 1];
    if (!previous || Math.hypot(point.x - previous.x, point.y - previous.y) >= 0.0008 || point.t_ms - previous.t_ms >= 5) {
      stroke.points.push(point);
      state.pointerTypes.add(point.source);
    }
  });
}

function resetTiming() {
  const timestamps = state.strokes.flatMap((stroke) => stroke.points.map((point) => point.t_ms || 0));
  state.recordingOffset = timestamps.length ? Math.max(...timestamps) + 1 : 0;
  state.recordingOrigin = performance.now();
}

function captureClientContext() {
  return {
    application: "mobile_web",
    user_agent: navigator.userAgent,
    viewport: {
      width_px: Math.max(1, Math.round(window.innerWidth)),
      height_px: Math.max(1, Math.round(window.innerHeight)),
      device_pixel_ratio: window.devicePixelRatio || 1,
    },
    pointer_types: [...state.pointerTypes],
  };
}

function capturePayload(status) {
  return {
    schema_version: "1.0",
    writer_id: state.writerId,
    writer_name: state.writerName,
    character: currentEntry().character,
    variant: state.variant,
    status,
    client: captureClientContext(),
    strokes: JSON.parse(JSON.stringify(state.strokes)),
  };
}

function queueSave(status) {
  const payload = capturePayload(status);
  const fallbackState = state.sampleState === "saving" ? "draft" : state.sampleState;
  setSampleState("saving");
  state.saveQueue = state.saveQueue.catch(() => undefined).then(async () => {
    const result = await apiRequest("/api/sample", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    updateProgress(result.progress);
    setSampleState(result.state);
    return result;
  });
  return state.saveQueue.catch((error) => {
    setConnection("error", "保存失败");
    setSampleState(fallbackState);
    showToast(error.message, true);
    throw error;
  });
}

function loadStrokes(sample) {
  state.strokes = (sample?.strokes || []).map((stroke) => ({
    points: (stroke.points || []).map((point) => ({ ...point })),
  }));
  state.pointerTypes = new Set(
    state.strokes.flatMap((stroke) => stroke.points.map((point) => point.source || "touch")),
  );
  resetTiming();
  drawCanvas();
  updateStats();
}

async function loadEntry(index) {
  if (!state.entries.length || !state.writerId) return;
  await state.saveQueue.catch(() => undefined);
  state.currentIndex = (index + state.entries.length) % state.entries.length;
  updateTarget();
  const entry = currentEntry();
  const sequence = ++state.loadSequence;
  try {
    const result = await apiRequest("/api/sample", {}, {
      writer_id: state.writerId,
      writer_name: state.writerName,
      character: entry.character,
      variant: state.variant,
    });
    if (sequence !== state.loadSequence) return;
    loadStrokes(result.sample);
    updateProgress(result.progress);
    setSampleState(result.state);
    setConnection("connected", "已连接");
  } catch (error) {
    setConnection("error", "连接失败");
    showToast(error.message, true);
  }
}

function nextIncompleteIndex() {
  for (let offset = 1; offset <= state.entries.length; offset += 1) {
    const index = (state.currentIndex + offset) % state.entries.length;
    if (!state.completedCharacters.has(state.entries[index].character)) return index;
  }
  return state.currentIndex;
}

async function initializeWriter() {
  elements.writerLabel.textContent = state.writerName || state.writerId;
  const progress = await apiRequest("/api/progress", {}, {
    writer_id: state.writerId,
    writer_name: state.writerName,
  });
  updateProgress(progress.progress);
  const firstIncomplete = state.entries.findIndex(
    (entry) => !state.completedCharacters.has(entry.character),
  );
  await loadEntry(firstIncomplete >= 0 ? firstIncomplete : 0);
}

async function startApplication() {
  try {
    const config = await apiRequest("/api/config");
    state.entries = config.entries;
    elements.positionTotal.textContent = `/ ${state.entries.length}`;
    elements.progressBar.max = state.entries.length;
    const savedWriterId = window.localStorage.getItem("handwriting.writer_id") || "";
    const savedWriterName = window.localStorage.getItem("handwriting.writer_name") || "";
    elements.writerIdInput.value = savedWriterId || config.default_writer.id || "";
    elements.writerNameInput.value = savedWriterName || config.default_writer.name || "";
    setConnection("connected", "已连接");
    if (elements.writerIdInput.value) {
      state.writerId = elements.writerIdInput.value.trim();
      state.writerName = elements.writerNameInput.value.trim();
      await initializeWriter();
    } else {
      elements.writerDialog.showModal();
    }
  } catch (error) {
    setConnection("error", "连接失败");
    showToast(error.message, true);
  }
}

elements.canvas.addEventListener("pointerdown", (event) => {
  if (!state.writerId || state.activePointerId !== null) return;
  event.preventDefault();
  state.activePointerId = event.pointerId;
  elements.canvas.setPointerCapture(event.pointerId);
  state.strokes.push({ points: [] });
  appendPointerEvents(event);
  drawCanvas();
  updateStats();
});

elements.canvas.addEventListener("pointermove", (event) => {
  if (event.pointerId !== state.activePointerId) return;
  event.preventDefault();
  appendPointerEvents(event);
  drawCanvas();
  updateStats();
});

async function finishPointer(event) {
  if (event.pointerId !== state.activePointerId) return;
  event.preventDefault();
  appendPointerEvents(event);
  state.activePointerId = null;
  drawCanvas();
  updateStats();
  try {
    await queueSave("draft");
  } catch (_) {
    // The toast and connection state already expose the failure.
  }
}

elements.canvas.addEventListener("pointerup", finishPointer);
elements.canvas.addEventListener("pointercancel", finishPointer);

elements.undoButton.addEventListener("click", async () => {
  state.strokes.pop();
  resetTiming();
  drawCanvas();
  updateStats();
  try {
    await queueSave("draft");
  } catch (_) {}
});

elements.clearButton.addEventListener("click", async () => {
  state.strokes = [];
  state.pointerTypes.clear();
  resetTiming();
  drawCanvas();
  updateStats();
  try {
    await queueSave("draft");
    showToast("当前画布已清空");
  } catch (_) {}
});

elements.saveButton.addEventListener("click", async () => {
  try {
    await queueSave("complete");
    showToast("样本已保存");
  } catch (_) {}
});

elements.saveNextButton.addEventListener("click", async () => {
  try {
    await queueSave("complete");
    showToast("样本已保存");
    await loadEntry(nextIncompleteIndex());
  } catch (_) {}
});

elements.previousButton.addEventListener("click", () => loadEntry(state.currentIndex - 1));
elements.nextButton.addEventListener("click", () => loadEntry(state.currentIndex + 1));

elements.positionInput.addEventListener("change", () => {
  const value = Number(elements.positionInput.value);
  if (Number.isInteger(value) && value >= 1 && value <= state.entries.length) {
    loadEntry(value - 1);
  } else {
    elements.positionInput.value = String(state.currentIndex + 1);
  }
});

elements.searchInput.addEventListener("change", () => {
  const character = [...elements.searchInput.value.trim()][0] || "";
  const index = state.entries.findIndex((entry) => entry.character === character);
  if (index >= 0) {
    elements.searchInput.value = "";
    loadEntry(index);
  } else if (character) {
    showToast(`“${character}”不在目标字符集中`, true);
  }
});

elements.searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    elements.searchInput.dispatchEvent(new Event("change"));
  }
});

elements.variantSelect.addEventListener("change", () => {
  state.variant = Number(elements.variantSelect.value);
  loadEntry(state.currentIndex);
});

elements.writerButton.addEventListener("click", () => {
  elements.writerIdInput.value = state.writerId;
  elements.writerNameInput.value = state.writerName;
  elements.writerDialog.showModal();
});

elements.closeWriterDialog.addEventListener("click", () => {
  if (state.writerId) elements.writerDialog.close();
});

elements.writerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const writerId = elements.writerIdInput.value.trim();
  if (!writerId) {
    elements.writerIdInput.focus();
    return;
  }
  state.writerId = writerId;
  state.writerName = elements.writerNameInput.value.trim();
  window.localStorage.setItem("handwriting.writer_id", state.writerId);
  window.localStorage.setItem("handwriting.writer_name", state.writerName);
  elements.writerDialog.close();
  try {
    await initializeWriter();
  } catch (error) {
    setConnection("error", "连接失败");
    showToast(error.message, true);
  }
});

const resizeObserver = new ResizeObserver(resizeCanvas);
resizeObserver.observe(elements.canvas);
window.addEventListener("orientationchange", () => window.setTimeout(resizeCanvas, 80));
window.addEventListener("online", () => setConnection("connected", "已连接"));
window.addEventListener("offline", () => setConnection("error", "网络断开"));

updateStats();
resizeCanvas();
startApplication();
