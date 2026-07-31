import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const QUERY_KEY = "sineforge_workflow";
const TOKEN_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const POST_RESTORE_DELAY_MS = 750;
const EMPTY_WORKSPACE_FALLBACK_MS = 5000;

let pendingToken = null;
let transferTimer = null;
let transferInProgress = false;

function clearTransferQuery() {
  const url = new URL(window.location.href);
  url.searchParams.delete(QUERY_KEY);
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

function showToast(severity, summary, detail) {
  const toast = app.extensionManager?.toast;
  if (toast?.add) {
    toast.add({ severity, summary, detail, life: 6000 });
  }
}

function scheduleTransfer(delayMs) {
  if (!pendingToken || transferInProgress) return;
  if (transferTimer !== null) {
    window.clearTimeout(transferTimer);
  }
  transferTimer = window.setTimeout(() => {
    transferTimer = null;
    void loadTransferredWorkflow();
  }, delayMs);
}

async function loadTransferredWorkflow() {
  if (!pendingToken || transferInProgress) return;

  const token = pendingToken;
  pendingToken = null;
  transferInProgress = true;

  try {
    const response = await api.fetchApi(
      `/sineforge/workflow-transfer/${encodeURIComponent(token)}`,
      { cache: "no-store" },
    );
    const payload = await response.json();
    if (!response.ok || !payload?.ok || !payload.workflow) {
      throw new Error(payload?.error || `Workflow transfer failed (${response.status}).`);
    }
    await app.loadGraphData(payload.workflow, true, true, payload.name || "SineForge workflow");
    showToast(
      "success",
      "SineForge workflow loaded",
      `${payload.name || "Workflow"} is open and has not been queued.`,
    );
  } catch (error) {
    console.error("SineForge workflow bridge:", error);
    showToast(
      "error",
      "SineForge workflow failed to load",
      error instanceof Error ? error.message : String(error),
    );
  } finally {
    transferInProgress = false;
    clearTransferQuery();
  }
}

app.registerExtension({
  name: "SineForge.WorkflowBridge",
  setup() {
    const token = new URL(window.location.href).searchParams.get(QUERY_KEY);
    if (!token) return;
    window.opener = null;
    if (!TOKEN_PATTERN.test(token)) {
      clearTransferQuery();
      showToast("error", "SineForge workflow rejected", "The transfer token is invalid.");
      return;
    }

    pendingToken = token;

    // ComfyUI restores its saved workflow tabs after custom-extension setup.
    // This fallback covers a brand-new workspace where no graph is configured.
    scheduleTransfer(EMPTY_WORKSPACE_FALLBACK_MS);
  },
  afterConfigureGraph() {
    if (!pendingToken || transferInProgress) return;

    // Each startup graph load resets the timer. The SineForge workflow is
    // applied only after ComfyUI's own workflow/tab restoration has settled.
    scheduleTransfer(POST_RESTORE_DELAY_MS);
  },
});
