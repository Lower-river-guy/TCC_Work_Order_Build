const tokenInput = document.querySelector("#access-token");
const accessPanel = document.querySelector("#access-panel");
const accessNote = document.querySelector("#access-note");
const ftpStatus = document.querySelector("#ftp-status");
const templateSourceInputs = document.querySelectorAll('input[name="template_source"]');
const workOrderPresetInputs = document.querySelectorAll('input[name="work_order_preset"]');
const workOrderPresetNotice = document.querySelector("#work-order-preset-notice");
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
const loadDevicesButton = document.querySelector("#load-devices");
const loadProjectsButton = document.querySelector("#load-projects");
const templateLine = document.querySelector("#template-line");
const banner = document.querySelector("#banner");
const previewBody = document.querySelector("#preview-body");
const log = document.querySelector("#log");
const confirmDialog = document.querySelector("#confirm-dialog");
const workflowSteps = document.querySelectorAll(".workflow-step");

const TOKEN_KEY = "tcc-work-order-token";

/** Placeholder presets — map to real configuration behavior in a later revision. */
const WORK_ORDER_PRESETS = {
  default: { label: "Default", ready: true },
  landfill: { label: "Landfill", ready: false },
  residential: { label: "Residential", ready: false },
  solar: { label: "Solar", ready: false },
};

let lastPreview = null;
let devicesLoaded = false;
let projectsLoaded = false;
let pushCompleted = false;

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

function selectedWorkOrderPreset() {
  const checked = document.querySelector('input[name="work_order_preset"]:checked');
  return checked ? checked.value : "default";
}

function workOrderPresetProfile() {
  return WORK_ORDER_PRESETS[selectedWorkOrderPreset()] || WORK_ORDER_PRESETS.default;
}

function isWorkOrderPresetReady() {
  return workOrderPresetProfile().ready;
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

function updateWorkOrderPresetNotice() {
  const profile = workOrderPresetProfile();
  if (profile.ready) {
    workOrderPresetNotice.hidden = true;
    workOrderPresetNotice.textContent = "";
  } else {
    workOrderPresetNotice.hidden = false;
    workOrderPresetNotice.textContent = `${profile.label} Work Order Preset — Under Construction`;
  }
}

function isPrefixComplete() {
  return prefixInput.value.trim().length > 0;
}

function isDeviceStepComplete() {
  return devicesLoaded && Boolean(deviceSelect.value);
}

function isProjectsStepComplete() {
  return projectsLoaded && Boolean(projectSelect.value);
}

function isConfigureComplete() {
  if (!isWorkOrderPresetReady()) {
    return false;
  }
  if (!deviceSelect.value || !projectSelect.value) {
    return false;
  }
  const source = selectedTemplateSource();
  if (source === "upload" && !customTemplateInput.files[0]) {
    return false;
  }
  if (source === "none" && !customWorkOrderNamesInput.value.trim()) {
    return false;
  }
  return true;
}

function isPreviewComplete() {
  return lastPreview !== null;
}

function updateWorkflowSteps() {
  const stepComplete = [
    isPrefixComplete(),
    isDeviceStepComplete(),
    isProjectsStepComplete(),
    isConfigureComplete(),
    isPreviewComplete(),
    pushCompleted,
  ];

  let currentIndex = stepComplete.findIndex((done) => !done);
  if (currentIndex === -1) {
    currentIndex = stepComplete.length - 1;
  }

  workflowSteps.forEach((element, index) => {
    element.classList.remove("is-current", "is-complete");
    if (stepComplete[index]) {
      element.classList.add("is-complete");
      const marker = element.querySelector(".step-marker");
      if (marker) {
        marker.textContent = "✓";
      }
    } else if (index === currentIndex) {
      element.classList.add("is-current");
      const marker = element.querySelector(".step-marker");
      if (marker) {
        marker.textContent = String(index + 1);
      }
    } else {
      const marker = element.querySelector(".step-marker");
      if (marker) {
        marker.textContent = String(index + 1);
      }
    }
  });
}

function updateButtonStates() {
  const templateReady = isWorkOrderPresetReady();
  const configured = isConfigureComplete();

  previewButton.disabled = !templateReady || !configured;
  actionButton.disabled = !templateReady || !configured;

  loadProjectsButton.disabled = !deviceSelect.value;
}

function validateSelection() {
  if (!isWorkOrderPresetReady()) {
    throw new Error(`${workOrderPresetProfile().label} Work Order Preset — Under Construction`);
  }
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
  actionButton.textContent = dryRunBox.checked ? "Run Dry Run" : "Confirm Upload";
  updateWorkflowSteps();
  updateButtonStates();
}

function toggleCustomTemplateField() {
  customTemplateField.hidden = selectedTemplateSource() !== "upload";
  lastPreview = null;
  pushCompleted = false;
  refreshUiState();
}

function refreshUiState() {
  updateWorkOrderPresetNotice();
  updateCustomWorkOrderPreview();
  updateActionButton();
  updateWorkflowSteps();
  updateButtonStates();
}

function resetFormDefaults(defaultPrefix = "RK-") {
  const defaultSource = document.querySelector('input[name="template_source"][value="default"]');
  const defaultPreset = document.querySelector('input[name="work_order_preset"][value="default"]');
  if (defaultSource) {
    defaultSource.checked = true;
  }
  if (defaultPreset) {
    defaultPreset.checked = true;
  }
  dryRunBox.checked = true;
  prefixInput.value = defaultPrefix;
  customTemplateInput.value = "";
  customWorkOrderNamesInput.value = "";
  devicesLoaded = false;
  projectsLoaded = false;
  pushCompleted = false;
  lastPreview = null;
  fillSelect(deviceSelect, [], "Select a device");
  fillSelect(projectSelect, [], "Select a project");
  toggleCustomTemplateField();
  refreshUiState();
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
  refreshUiState();
}

async function callPreview() {
  validateSelection();
  previewButton.disabled = true;
  actionButton.disabled = true;
  log.textContent = "Building preview…";
  pushCompleted = false;
  try {
    const response = await fetch("/api/work-orders/preview", {
      method: "POST",
      headers: authHeaders(),
      body: buildFormData(),
    });
    renderPreview(await readJson(response));
  } catch (error) {
    log.textContent = error.message;
    lastPreview = null;
    refreshUiState();
  } finally {
    updateButtonStates();
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
    if (!dryRun) {
      pushCompleted = true;
      refreshUiState();
    }
  } catch (error) {
    log.textContent = error.message;
  } finally {
    updateButtonStates();
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
workOrderPresetInputs.forEach((input) => {
  input.addEventListener("change", () => {
    lastPreview = null;
    pushCompleted = false;
    refreshUiState();
  });
});
customWorkOrderNamesInput.addEventListener("input", () => {
  lastPreview = null;
  pushCompleted = false;
  refreshUiState();
});
customTemplateInput.addEventListener("change", () => {
  lastPreview = null;
  pushCompleted = false;
  refreshUiState();
});
prefixInput.addEventListener("input", () => {
  lastPreview = null;
  pushCompleted = false;
  refreshUiState();
});
deviceSelect.addEventListener("change", () => {
  projectsLoaded = false;
  pushCompleted = false;
  lastPreview = null;
  fillSelect(projectSelect, [], "Select a project");
  refreshUiState();
});
projectSelect.addEventListener("change", () => {
  lastPreview = null;
  pushCompleted = false;
  refreshUiState();
});
dryRunBox.addEventListener("change", updateActionButton);

resetFormDefaults();
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    resetFormDefaults(prefixInput.value.trim() || "RK-");
  }
});

loadDevicesButton.addEventListener("click", async () => {
  ftpStatus.textContent = "Loading devices…";
  try {
    const data = await readJson(await fetch("/api/ftp/devices", { headers: authHeaders() }));
    fillSelect(deviceSelect, data.devices, "Select a device");
    devicesLoaded = true;
    projectsLoaded = false;
    fillSelect(projectSelect, [], "Select a project");
    ftpStatus.textContent = `${data.devices.length} devices found.`;
    refreshUiState();
  } catch (error) {
    ftpStatus.textContent = error.message;
  }
});

loadProjectsButton.addEventListener("click", async () => {
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
    projectsLoaded = true;
    ftpStatus.textContent = `${data.projects.length} projects found for ${data.device}.`;
    refreshUiState();
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
