const tokenInput = document.querySelector("#access-token");
const accessPanel = document.querySelector("#access-panel");
const accessNote = document.querySelector("#access-note");
const ftpStatus = document.querySelector("#ftp-status");
const templateSourceInputs = document.querySelectorAll('input[name="template_source"]');
const customTemplateField = document.querySelector("#custom-template-field");
const customTemplateInput = document.querySelector("#custom-template");
const prefixInput = document.querySelector("#prefix");
const customWorkOrderNamesInput = document.querySelector("#custom-work-order-names");
const customWorkOrderPreview = document.querySelector("#custom-work-order-preview");
const deviceSelect = document.querySelector("#device");
const projectSelect = document.querySelector("#project");
const dryRunBox = document.querySelector("#dry-run");
const previewButton = document.querySelector("#preview-button");
const actionButton = document.querySelector("#action-button");
const templateLine = document.querySelector("#template-line");
const banner = document.querySelector("#banner");
const previewBody = document.querySelector("#preview-body");
const log = document.querySelector("#log");
const confirmDialog = document.querySelector("#confirm-dialog");

const TOKEN_KEY = "tcc-work-order-token";
let lastPreview = null;

function token() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

function authHeaders() {
  const value = token();
  return value ? { "X-Access-Token": value } : {};
}

function selectedTemplateSource() {
  const checked = document.querySelector('input[name="template_source"]:checked');
  return checked ? checked.value : "default";
}

async function readJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

function buildFormData(extra = {}) {
  const data = new FormData();
  data.set("prefix", prefixInput.value.trim());
  data.set("device", deviceSelect.value);
  data.set("project", projectSelect.value);
  data.set("template_source", selectedTemplateSource());
  data.set("custom_work_order_names", customWorkOrderNamesInput.value.trim());
  if (token()) {
    data.set("access_token", token());
  }
  Object.entries(extra).forEach(([key, value]) => data.set(key, value));
  if (selectedTemplateSource() === "upload" && customTemplateInput.files[0]) {
    data.set("custom_template", customTemplateInput.files[0]);
  }
  return data;
}

function parseCommaNames(raw) {
  return (raw || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function resolveCustomWorkOrderFolder(prefix, rawName) {
  const cleaned = (rawName || "").trim();
  if (!cleaned) {
    return "";
  }
  let body = cleaned;
  if (body.toLowerCase().startsWith(prefix.toLowerCase())) {
    body = body.slice(prefix.length).trim();
  }
  if (!body) {
    return "";
  }
  return `${prefix}${body}`;
}

function updateCustomWorkOrderPreview() {
  const prefix = prefixInput.value.trim() || "RK-";
  const names = parseCommaNames(customWorkOrderNamesInput.value);
  if (!names.length) {
    customWorkOrderPreview.textContent = "Custom work orders: —";
    return;
  }
  const resolved = names.map((name) => resolveCustomWorkOrderFolder(prefix, name));
  customWorkOrderPreview.textContent = `Custom work orders: ${resolved.join(", ")}`;
}

function validateSelection() {
  if (!deviceSelect.value || !projectSelect.value) {
    throw new Error("Select a device and a project.");
  }
  const source = selectedTemplateSource();
  if (source === "upload" && !customTemplateInput.files[0]) {
    throw new Error("Upload Custom Work Order Template (.zip).");
  }
  if (source === "none" && !customWorkOrderNamesInput.value.trim()) {
    throw new Error("Enter at least one Custom Work Order Name when No Template is selected.");
  }
}

function updateActionButton() {
  actionButton.textContent = dryRunBox.checked ? "Run Dry Run" : "Upload New Work Orders";
}

function toggleCustomTemplateField() {
  customTemplateField.hidden = selectedTemplateSource() !== "upload";
}

function resetFormDefaults(defaultPrefix = "RK-") {
  const defaultRadio = document.querySelector('input[name="template_source"][value="default"]');
  if (defaultRadio) {
    defaultRadio.checked = true;
  }
  dryRunBox.checked = true;
  prefixInput.value = defaultPrefix;
  customTemplateInput.value = "";
  customWorkOrderNamesInput.value = "";
  toggleCustomTemplateField();
  updateCustomWorkOrderPreview();
  updateActionButton();
}

function renderPreview(data) {
  lastPreview = data;
  templateLine.textContent = `Template: ${data.template || "—"}`;
  banner.hidden = !data.banner;
  banner.textContent = data.banner || "";
  document.querySelector("#total-count").textContent = data.totals?.total ?? "—";
  document.querySelector("#new-count").textContent = data.totals?.new ?? "—";
  document.querySelector("#existing-count").textContent = data.totals?.existing ?? "—";
  previewBody.innerHTML = "";
  if (!data.rows?.length) {
    previewBody.innerHTML =
      '<tr><td colspan="4" class="empty">No work orders found for this selection.</td></tr>';
  } else {
    data.rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${row.work_order}</td><td>${row.source || "—"}</td><td>${row.status}</td><td>${row.action}</td>`;
      previewBody.appendChild(tr);
    });
  }
  log.textContent = (data.log || []).join("\n");
}

async function callPreview() {
  validateSelection();
  previewButton.disabled = true;
  actionButton.disabled = true;
  log.textContent = "Building preview…";
  try {
    const response = await fetch("/api/work-orders/preview", {
      method: "POST",
      headers: authHeaders(),
      body: buildFormData(),
    });
    renderPreview(await readJson(response));
  } catch (error) {
    log.textContent = error.message;
  } finally {
    previewButton.disabled = false;
    actionButton.disabled = false;
  }
}

async function callRun(dryRun, confirmUpload) {
  validateSelection();
  previewButton.disabled = true;
  actionButton.disabled = true;
  log.textContent = dryRun ? "Running dry run…" : "Uploading new work orders…";
  try {
    const response = await fetch("/api/work-orders/run", {
      method: "POST",
      headers: authHeaders(),
      body: buildFormData({
        dry_run: dryRun ? "true" : "false",
        confirm_upload: confirmUpload ? "true" : "false",
      }),
    });
    renderPreview(await readJson(response));
  } catch (error) {
    log.textContent = error.message;
  } finally {
    previewButton.disabled = false;
    actionButton.disabled = false;
  }
}

function fillSelect(select, values, placeholder) {
  select.innerHTML = "";
  const first = document.createElement("option");
  first.value = "";
  first.textContent = placeholder;
  select.appendChild(first);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
}

templateSourceInputs.forEach((input) => {
  input.addEventListener("change", toggleCustomTemplateField);
});
customWorkOrderNamesInput.addEventListener("input", updateCustomWorkOrderPreview);
prefixInput.addEventListener("input", updateCustomWorkOrderPreview);
dryRunBox.addEventListener("change", updateActionButton);
resetFormDefaults();
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    resetFormDefaults(prefixInput.value.trim() || "RK-");
  }
});

document.querySelector("#load-devices").addEventListener("click", async () => {
  ftpStatus.textContent = "Loading devices…";
  try {
    const data = await readJson(await fetch("/api/ftp/devices", { headers: authHeaders() }));
    fillSelect(deviceSelect, data.devices, "Select a device");
    ftpStatus.textContent = `${data.devices.length} devices found.`;
  } catch (error) {
    ftpStatus.textContent = error.message;
  }
});

document.querySelector("#load-projects").addEventListener("click", async () => {
  if (!deviceSelect.value) {
    ftpStatus.textContent = "Select a device first.";
    return;
  }
  ftpStatus.textContent = "Loading projects…";
  try {
    const data = await readJson(
      await fetch(`/api/ftp/projects?device=${encodeURIComponent(deviceSelect.value)}`, {
        headers: authHeaders(),
      })
    );
    fillSelect(projectSelect, data.projects, "Select a project");
    ftpStatus.textContent = `${data.projects.length} projects found for ${data.device}.`;
  } catch (error) {
    ftpStatus.textContent = error.message;
  }
});

previewButton.addEventListener("click", () => callPreview());

actionButton.addEventListener("click", () => {
  if (dryRunBox.checked) {
    callRun(true, false);
    return;
  }
  if (!lastPreview) {
    log.textContent = "Run Preview first.";
    return;
  }
  document.querySelector("#confirm-template").textContent = lastPreview.template;
  document.querySelector("#confirm-prefix").textContent = lastPreview.prefix;
  document.querySelector("#confirm-device").textContent = deviceSelect.value;
  document.querySelector("#confirm-project").textContent = projectSelect.value;
  document.querySelector("#confirm-new").textContent = String(lastPreview.totals?.new ?? 0);
  document.querySelector("#confirm-existing").textContent = String(lastPreview.totals?.existing ?? 0);
  confirmDialog.showModal();
});

document.querySelector("#cancel-upload").addEventListener("click", () => confirmDialog.close());

document.querySelector("#confirm-form").addEventListener("submit", (event) => {
  event.preventDefault();
  confirmDialog.close();
  callRun(false, true);
});

document.querySelector("#save-token").addEventListener("click", () => {
  sessionStorage.setItem(TOKEN_KEY, tokenInput.value.trim());
  accessNote.textContent = "Token saved in this browser tab.";
  loadConfig();
});

async function loadConfig() {
  if (token()) {
    tokenInput.value = token();
  }
  try {
    const data = await readJson(await fetch("/api/config"));
    accessPanel.hidden = !data.access_required;
    resetFormDefaults(data.default_prefix || "RK-");
    ftpStatus.textContent = data.ftp_configured
      ? "FTP credentials are configured. Load devices to begin."
      : "FTP credentials are not configured. Set TCC_T48_DEVICE_USER and TCC_T48_DEVICE_PASS on the server.";
  } catch (error) {
    ftpStatus.textContent = error.message;
  }
}

loadConfig();
