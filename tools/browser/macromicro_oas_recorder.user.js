// ==UserScript==
// @name         MacroMicro OAS Tooltip Recorder
// @namespace    local-macro-portfolio-ai
// @version      0.1.0
// @description  Manually record MacroMicro Highcharts OAS tooltip values while hovering the chart.
// @match        https://sc.macromicro.me/series/78167/*
// @match        https://*.macromicro.me/series/78167/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_deleteValue
// @grant        GM_download
// ==/UserScript==

(function () {
  "use strict";

  const CONFIG = {
    storageKey: "macromicro_oas_tooltip_recorder_v1",
    panelId: "mm-oas-recorder-panel",
    debounceMs: 90,
    tooltipSelectors: [
      ".highcharts-tooltip",
      ".highcharts-label.highcharts-tooltip",
      "[role='tooltip']",
      ".chart-tooltip",
    ],
    chartSelectors: [
      ".highcharts-container",
      ".highcharts-root",
      "[id*='chart']",
    ],
    targetTextPattern: /OAS\s*[\u5229\u5dee]/i,
    valuePattern: /OAS[\s\S]{0,24}?[:\uFF1A]\s*([0-9]+(?:\.[0-9]+)?)/i,
    maxReasonableOasPercent: 100,
  };

  const MONTHS = {
    jan: "01",
    feb: "02",
    mar: "03",
    apr: "04",
    may: "05",
    jun: "06",
    jul: "07",
    aug: "08",
    sep: "09",
    oct: "10",
    nov: "11",
    dec: "12",
  };

  const DEFAULT_STATE = {
    recording: false,
    chartOnly: true,
    records: {},
    conflicts: [],
    stats: {
      duplicateOverwrite: 0,
      conflictCount: 0,
      parseFailures: 0,
      ignoredOutsideChart: 0,
      tooltipReads: 0,
    },
    last: {
      rawTooltip: "",
      date: "",
      value: "",
      error: "",
      capturedAt: "",
    },
  };

  let state = loadState();
  let panel = null;
  let debounceTimer = null;
  let lastPointer = { x: 0, y: 0, insideChart: false };

  function cloneDefaultState() {
    return JSON.parse(JSON.stringify(DEFAULT_STATE));
  }

  function loadState() {
    const fallback = cloneDefaultState();
    try {
      const raw = typeof GM_getValue === "function"
        ? GM_getValue(CONFIG.storageKey, null)
        : window.localStorage.getItem(CONFIG.storageKey);
      if (!raw) return fallback;
      return mergeState(fallback, JSON.parse(raw));
    } catch (_error) {
      return fallback;
    }
  }

  function mergeState(base, saved) {
    const merged = { ...base, ...saved };
    merged.records = saved.records || {};
    merged.conflicts = saved.conflicts || [];
    merged.stats = { ...base.stats, ...(saved.stats || {}) };
    merged.last = { ...base.last, ...(saved.last || {}) };
    return merged;
  }

  function saveState() {
    const raw = JSON.stringify(state);
    if (typeof GM_setValue === "function") {
      GM_setValue(CONFIG.storageKey, raw);
      return;
    }
    window.localStorage.setItem(CONFIG.storageKey, raw);
  }

  function clearState() {
    const recording = state.recording;
    const chartOnly = state.chartOnly;
    state = cloneDefaultState();
    state.recording = recording;
    state.chartOnly = chartOnly;
    if (typeof GM_deleteValue === "function") {
      GM_deleteValue(CONFIG.storageKey);
    } else {
      window.localStorage.removeItem(CONFIG.storageKey);
    }
    saveState();
    renderPanel();
  }

  function normalizeText(text) {
    return String(text || "")
      .replace(/[\u200B-\u200D\uFEFF]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function findTooltipElement() {
    for (const selector of CONFIG.tooltipSelectors) {
      const element = document.querySelector(selector);
      if (element && normalizeText(element.textContent)) return element;
    }
    return null;
  }

  function readTooltipText() {
    const element = findTooltipElement();
    if (!element) return "";
    const style = window.getComputedStyle(element);
    if (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0) {
      return "";
    }
    return normalizeText(element.textContent);
  }

  function chartRect() {
    for (const selector of CONFIG.chartSelectors) {
      const element = document.querySelector(selector);
      if (!element) continue;
      const rect = element.getBoundingClientRect();
      if (rect.width > 100 && rect.height > 100) return rect;
    }
    return null;
  }

  function isInsideChart(x, y) {
    const rect = chartRect();
    if (!rect) return true;
    return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
  }

  function parseTooltip(text) {
    const raw = normalizeText(text);
    if (!raw) return { ok: false, error: "empty_tooltip", raw };
    if (!CONFIG.targetTextPattern.test(raw)) {
      return { ok: false, error: "target_series_missing", raw };
    }

    const dateMatch = raw.match(
      /(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s*(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})/i
    );
    if (!dateMatch) return { ok: false, error: "date_not_found", raw };

    const day = dateMatch[1].padStart(2, "0");
    const month = MONTHS[dateMatch[2].toLowerCase()];
    const year = dateMatch[3];
    if (!month) return { ok: false, error: "month_not_found", raw };
    const date = `${year}-${month}-${day}`;

    const valueMatch = raw.match(CONFIG.valuePattern);
    if (!valueMatch) return { ok: false, error: "value_not_found", raw };
    const value = Number(valueMatch[1]);
    if (!Number.isFinite(value)) return { ok: false, error: "value_not_finite", raw };
    if (value < 0 || value > CONFIG.maxReasonableOasPercent) {
      return { ok: false, error: "value_out_of_range", raw };
    }

    return { ok: true, date, value, raw };
  }

  function scheduleRead() {
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(captureCurrentTooltip, CONFIG.debounceMs);
  }

  function captureCurrentTooltip() {
    if (!state.recording) return;
    if (state.chartOnly && !lastPointer.insideChart) {
      state.stats.ignoredOutsideChart += 1;
      saveState();
      renderPanel();
      return;
    }

    const rawTooltip = readTooltipText();
    if (!rawTooltip || rawTooltip === state.last.rawTooltip) return;
    state.stats.tooltipReads += 1;

    const parsed = parseTooltip(rawTooltip);
    state.last = {
      rawTooltip,
      date: parsed.date || "",
      value: parsed.value ?? "",
      error: parsed.ok ? "" : parsed.error,
      capturedAt: new Date().toISOString(),
    };

    if (!parsed.ok) {
      state.stats.parseFailures += 1;
      saveState();
      renderPanel();
      return;
    }

    const capturedAt = new Date().toISOString();
    const existing = state.records[parsed.date];
    if (existing) {
      state.stats.duplicateOverwrite += 1;
      if (Number(existing.oas_percent) !== parsed.value) {
        state.stats.conflictCount += 1;
        state.conflicts.push({
          date: parsed.date,
          previous: Number(existing.oas_percent),
          current: parsed.value,
          captured_at: capturedAt,
          previous_captured_at: existing.captured_at,
        });
      }
    }

    state.records[parsed.date] = {
      date: parsed.date,
      oas_percent: parsed.value,
      source_url: location.href,
      captured_at: capturedAt,
      raw_tooltip: parsed.raw,
    };
    saveState();
    renderPanel();
  }

  function sortedRecords() {
    return Object.values(state.records).sort((a, b) => a.date.localeCompare(b.date));
  }

  function findGaps(records) {
    const gaps = [];
    for (let index = 1; index < records.length; index += 1) {
      const prev = new Date(`${records[index - 1].date}T00:00:00Z`);
      const next = new Date(`${records[index].date}T00:00:00Z`);
      const days = Math.round((next - prev) / 86400000);
      if (days > 7) {
        gaps.push({
          from: records[index - 1].date,
          to: records[index].date,
          calendar_days: days,
        });
      }
    }
    return gaps;
  }

  function csvEscape(value) {
    const text = String(value ?? "");
    if (/[",\r\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
    return text;
  }

  function buildCsv() {
    const header = ["date", "oas_percent", "source_url", "captured_at", "raw_tooltip"];
    const rows = sortedRecords().map((record) => [
      record.date,
      record.oas_percent,
      record.source_url,
      record.captured_at,
      record.raw_tooltip,
    ]);
    return [header, ...rows].map((row) => row.map(csvEscape).join(",")).join("\n") + "\n";
  }

  function buildManifest() {
    const records = sortedRecords();
    const gaps = findGaps(records);
    return {
      source_url: location.href,
      captured_at: new Date().toISOString(),
      recorder_version: "0.1.0",
      chart_library_hint: "Highcharts tooltip DOM",
      selector: ".highcharts-tooltip",
      record_count: records.length,
      first_date: records[0]?.date || null,
      last_date: records[records.length - 1]?.date || null,
      stats: state.stats,
      gaps_over_7_calendar_days: gaps,
      conflicts: state.conflicts,
      note: "Manual hover capture. Do not treat as official imported market_history without separate QA.",
    };
  }

  function downloadText(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    if (typeof GM_download === "function") {
      GM_download({ url, name: filename, saveAs: true });
      window.setTimeout(() => URL.revokeObjectURL(url), 30000);
      return;
    }
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 30000);
  }

  function exportCsv() {
    downloadText("oas_capture_raw.csv", buildCsv(), "text/csv;charset=utf-8");
  }

  function exportJson() {
    downloadText(
      "oas_capture_manifest.json",
      JSON.stringify({ manifest: buildManifest(), records: sortedRecords() }, null, 2),
      "application/json;charset=utf-8"
    );
  }

  async function copyDiagnostics() {
    const diagnostics = JSON.stringify({
      selector: ".highcharts-tooltip",
      raw_tooltip: state.last.rawTooltip || readTooltipText(),
      parsed: parseTooltip(state.last.rawTooltip || readTooltipText()),
      record_count: sortedRecords().length,
      stats: state.stats,
      chart_rect: chartRect(),
    }, null, 2);
    try {
      await navigator.clipboard.writeText(diagnostics);
      state.last.error = "diagnostics_copied";
    } catch (_error) {
      state.last.error = "copy_failed";
      window.prompt("Copy diagnostics:", diagnostics);
    }
    renderPanel();
  }

  function createButton(label, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", onClick);
    return button;
  }

  function ensurePanel() {
    if (panel) return panel;
    const style = document.createElement("style");
    style.textContent = `
      #${CONFIG.panelId} {
        position: fixed;
        right: 14px;
        bottom: 14px;
        z-index: 2147483647;
        width: 330px;
        max-width: calc(100vw - 28px);
        padding: 10px;
        border: 1px solid #92a3ad;
        border-radius: 6px;
        background: rgba(255, 255, 255, 0.96);
        color: #1f2d36;
        box-shadow: 0 8px 28px rgba(0, 0, 0, 0.18);
        font: 12px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      #${CONFIG.panelId} .mm-oas-title {
        font-weight: 700;
        margin-bottom: 8px;
      }
      #${CONFIG.panelId} .mm-oas-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 8px;
      }
      #${CONFIG.panelId} button {
        border: 1px solid #8da1aa;
        border-radius: 4px;
        background: #f7fafb;
        color: #17252e;
        cursor: pointer;
        font: inherit;
        padding: 4px 7px;
      }
      #${CONFIG.panelId} button[data-active="true"] {
        background: #0f9f8f;
        border-color: #0f9f8f;
        color: white;
      }
      #${CONFIG.panelId} .mm-oas-grid {
        display: grid;
        grid-template-columns: 92px 1fr;
        gap: 2px 8px;
      }
      #${CONFIG.panelId} .mm-oas-muted {
        color: #60727d;
      }
      #${CONFIG.panelId} .mm-oas-raw {
        margin-top: 7px;
        max-height: 48px;
        overflow: auto;
        word-break: break-word;
        color: #344b57;
      }
    `;
    document.documentElement.appendChild(style);

    panel = document.createElement("div");
    panel.id = CONFIG.panelId;
    document.documentElement.appendChild(panel);
    return panel;
  }

  function renderPanel() {
    const root = ensurePanel();
    const records = sortedRecords();
    const gaps = findGaps(records);
    root.replaceChildren();

    const title = document.createElement("div");
    title.className = "mm-oas-title";
    title.textContent = "MacroMicro OAS Recorder";
    root.appendChild(title);

    const actions = document.createElement("div");
    actions.className = "mm-oas-actions";
    const start = createButton(state.recording ? "Recording" : "Start", () => {
      state.recording = true;
      saveState();
      renderPanel();
      scheduleRead();
    });
    start.dataset.active = String(state.recording);
    actions.appendChild(start);
    actions.appendChild(createButton("Pause", () => {
      state.recording = false;
      saveState();
      renderPanel();
    }));
    const chartOnly = createButton(state.chartOnly ? "Chart only: on" : "Chart only: off", () => {
      state.chartOnly = !state.chartOnly;
      saveState();
      renderPanel();
    });
    chartOnly.dataset.active = String(state.chartOnly);
    actions.appendChild(chartOnly);
    actions.appendChild(createButton("Export CSV", exportCsv));
    actions.appendChild(createButton("Export JSON", exportJson));
    actions.appendChild(createButton("Copy diag", copyDiagnostics));
    actions.appendChild(createButton("Clear", () => {
      if (window.confirm("Clear captured OAS records in this browser session?")) clearState();
    }));
    root.appendChild(actions);

    const grid = document.createElement("div");
    grid.className = "mm-oas-grid";
    const items = [
      ["Status", state.recording ? "recording" : "paused"],
      ["Records", String(records.length)],
      ["Current date", state.last.date || "-"],
      ["Current value", state.last.value === "" ? "-" : String(state.last.value)],
      ["Overwrites", String(state.stats.duplicateOverwrite)],
      ["Parse fails", String(state.stats.parseFailures)],
      ["Conflicts", String(state.stats.conflictCount)],
      ["Gaps > 7d", String(gaps.length)],
      ["Range", records.length ? `${records[0].date} to ${records[records.length - 1].date}` : "-"],
    ];
    for (const [key, value] of items) {
      const label = document.createElement("div");
      label.className = "mm-oas-muted";
      label.textContent = key;
      const text = document.createElement("div");
      text.textContent = value;
      grid.append(label, text);
    }
    root.appendChild(grid);

    const raw = document.createElement("div");
    raw.className = "mm-oas-raw";
    raw.textContent = state.last.rawTooltip || "Hover the chart while recording.";
    root.appendChild(raw);
  }

  function attachListeners() {
    document.addEventListener("pointermove", (event) => {
      lastPointer = {
        x: event.clientX,
        y: event.clientY,
        insideChart: isInsideChart(event.clientX, event.clientY),
      };
      scheduleRead();
    }, { passive: true });

    const observer = new MutationObserver(scheduleRead);
    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["visibility", "style", "transform", "opacity"],
    });
  }

  renderPanel();
  attachListeners();
  window.__macromicroOasRecorder = {
    parseTooltip,
    readTooltipText,
    exportCsv,
    exportJson,
    getState: () => JSON.parse(JSON.stringify(state)),
    clearState,
  };
})();
