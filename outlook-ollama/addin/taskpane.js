// ---------------------------------------------------------------------------
// EDIT THESE BEFORE HOSTING:
//   BACKEND_URL: HTTPS URL of the Flask proxy (e.g. https://llm.corp.example.com)
//   API_KEY:     Bearer secret if the backend has API_KEY set, otherwise "".
// ---------------------------------------------------------------------------
const BACKEND_URL = "https://llm.corp.example.com";
const API_KEY = "";

let lastResult = "";
let mode = null; // "compose" | "read"

function authHeaders() {
  const h = { "Content-Type": "application/json" };
  if (API_KEY) h["Authorization"] = "Bearer " + API_KEY;
  return h;
}

async function callBackend(path, payload) {
  const resp = await fetch(BACKEND_URL.replace(/\/+$/, "") + path, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error("HTTP " + resp.status + ": " + body);
  }
  return resp.json();
}

async function loadModels() {
  try {
    const resp = await fetch(BACKEND_URL.replace(/\/+$/, "") + "/models", {
      headers: authHeaders(),
    });
    if (!resp.ok) return;
    const data = await resp.json();
    const sel = document.getElementById("model");
    (data.models || []).forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name + (name === data.default ? " (default)" : "");
      sel.appendChild(opt);
    });
  } catch (e) {
    // non-fatal: user can still use the server default
    console.warn("loadModels failed:", e);
  }
}

function setStatus(msg, isError) {
  const el = document.getElementById("status");
  el.textContent = msg || "";
  el.classList.toggle("error", !!isError);
}

function setOutput(text) {
  document.getElementById("output").textContent = text || "";
  lastResult = text || "";
}

function getComposeBody() {
  return new Promise((resolve, reject) => {
    Office.context.mailbox.item.body.getAsync(
      Office.CoercionType.Text,
      (result) => {
        if (result.status === Office.AsyncResultStatus.Succeeded) resolve(result.value || "");
        else reject(new Error(result.error && result.error.message || "body.getAsync failed"));
      }
    );
  });
}

function setComposeBody(text) {
  return new Promise((resolve, reject) => {
    Office.context.mailbox.item.body.setAsync(
      text,
      { coercionType: Office.CoercionType.Text },
      (result) => {
        if (result.status === Office.AsyncResultStatus.Succeeded) resolve();
        else reject(new Error(result.error && result.error.message || "body.setAsync failed"));
      }
    );
  });
}

function getReadBody() {
  return new Promise((resolve, reject) => {
    Office.context.mailbox.item.body.getAsync(
      Office.CoercionType.Text,
      (result) => {
        if (result.status === Office.AsyncResultStatus.Succeeded) resolve(result.value || "");
        else reject(new Error(result.error && result.error.message || "body.getAsync failed"));
      }
    );
  });
}

async function doRewrite() {
  try {
    setStatus("Reading draft...");
    const text = (await getComposeBody()).trim();
    if (!text) {
      setStatus("Your draft is empty - type something first.", true);
      return;
    }
    const tone = document.getElementById("tone").value;
    const model = document.getElementById("model").value || undefined;
    const instructions = document.getElementById("instructions").value.trim() || undefined;

    setStatus("Rewriting with " + (model || "default model") + "...");
    document.getElementById("btnRewrite").disabled = true;
    const data = await callBackend("/rewrite", { text, tone, model, instructions });
    setOutput(data.text || "");
    setStatus("Done. Review the result, then click 'Insert into email'.");
    document.getElementById("btnInsert").disabled = !data.text;
  } catch (e) {
    setStatus("Error: " + e.message, true);
  } finally {
    document.getElementById("btnRewrite").disabled = false;
  }
}

async function doInsert() {
  try {
    if (!lastResult) return;
    setStatus("Inserting into email...");
    await setComposeBody(lastResult);
    setStatus("Inserted. Feel free to edit before sending.");
  } catch (e) {
    setStatus("Error: " + e.message, true);
  }
}

async function doSummarize() {
  try {
    setStatus("Reading email...");
    const text = (await getReadBody()).trim();
    if (!text) {
      setStatus("No email body to summarize.", true);
      return;
    }
    const model = document.getElementById("model").value || undefined;
    setStatus("Summarizing with " + (model || "default model") + "...");
    document.getElementById("btnSummarize").disabled = true;
    const data = await callBackend("/summarize", { text, model });
    setOutput(data.text || "");
    setStatus("Done.");
    document.getElementById("btnCopy").disabled = !data.text;
  } catch (e) {
    setStatus("Error: " + e.message, true);
  } finally {
    document.getElementById("btnSummarize").disabled = false;
  }
}

async function doCopy() {
  try {
    if (!lastResult) return;
    await navigator.clipboard.writeText(lastResult);
    setStatus("Copied to clipboard.");
  } catch (e) {
    setStatus("Copy failed: " + e.message, true);
  }
}

Office.onReady((info) => {
  if (info.host !== Office.HostType.Outlook) {
    setStatus("This add-in runs inside Outlook only.", true);
    return;
  }

  document.getElementById("endpointLabel").textContent = "Backend: " + BACKEND_URL;

  const item = Office.context.mailbox.item;
  // Compose mode exposes subject.setAsync; read mode does not.
  const isCompose = !!(item && item.subject && typeof item.subject.setAsync === "function");
  mode = isCompose ? "compose" : "read";

  document.getElementById("composeActions").hidden = !isCompose;
  document.getElementById("readActions").hidden = isCompose;

  if (isCompose) {
    document.getElementById("btnRewrite").addEventListener("click", doRewrite);
    document.getElementById("btnInsert").addEventListener("click", doInsert);
  } else {
    document.getElementById("btnSummarize").addEventListener("click", doSummarize);
    document.getElementById("btnCopy").addEventListener("click", doCopy);
  }

  loadModels();
  setStatus("Ready.");
});
