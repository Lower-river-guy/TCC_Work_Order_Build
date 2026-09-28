const tokenInput = document.querySelector("#access-token");
const accessPanel = document.querySelector("#access-panel");
const accessNote = document.querySelector("#access-note");
const ftpStatus = document.querySelector("#ftp-status");
const gradeChecker = document.querySelector("#grade-checker");
const prefixDisplay = document.querySelector("#prefix-display");
const deviceSelect = document.querySelector("#device");
const projectSelect = document.querySelector("#project");
const dryRunBox = document.querySelector("#dry-run");
const previewButton = document.querySelector("#preview-button");
const actionButton = document.querySelector("#action-button");
const banner = document.querySelector("#banner");
const previewBody = document.querySelector("#preview-body");
const log = document.querySelector("#log");
const confirmDialog = document.querySelector("#confirm-dialog");

const TOKEN_KEY = "tcc-work-order-token";
let lastPreview = null;

function token() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

function headers(extra = {}) {
  const value = token();
  return value ? { ...extra, "X-Access-Token": value, "Content-Type": "application/json" } : { ...extra, "Content-Type": "application/json" };
}

async function readJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

function selectionPayload() {
  return {
    grade_checker_id: gradeChecker.value,
    device: deviceSelect.value,
    project: projectSelect.value,
    access_token: token() || undefined,
  };
}

function validateSelection() {
  if (!gradeChecker.value) {
    throw new Error("Select a grade checker.");
  }
  if (!deviceSelect.value || !projectSelect.value) {
    throw new Error("Select a device and a project.");
  }
}

function updateActionButton() {
  actionButton.textContent = dryRunBox.checked ? "Run Dry Run" : "Upload New Work Orders";
}

function renderPreview(data) {
  lastPreview = data;
  banner.hidden = !data.banner;
  banner.textContent = data.banner || "";
  document.querySelector("#total-count").textContent = data.totals?.total ?? "—";
  document.querySelector("#new-count").textContent = data.totals?.new ?? "—";
  document.querySelector("#existing-count").textContent = data.totals?.existing ?? "—";
  previewBody.innerHTML = "";
  if (!data.rows?.length) {
    previewBody.innerHTML = '<tr><td colspan="3" class="empty">No work orders found in the master template.</td></tr>';
  } else {
    data.rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${row.work_order}</td><td>${row.status}</td><td>${row.action}</td>`;
      previewBody.appendChild(tr);
    });
  }
  log.textContent = (data.log || []).join("\n");
}

async function callPreview() {
  validateSelection();
  previewButton.disabled = true;
  actionButton.disabled = true;
  log.textContent = "Building preview from master template…";
  try {
    const data = await readJson(
      await fetch("/api/work-orders/preview", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(selectionPayload()),
      })
    );
    renderPreview(data);
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
    const payload = {
      ...selectionPayload(),
      dry_run: dryRun,
      confirm_upload: confirmUpload,
    };
    const data = await readJson(
      await fetch("/api/work-orders/run", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(payload),
      })
    );
    renderPreview(data);
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
    option.value = value.id || value;
    option.textContent = value.label || value;
    if (value.prefix) {
      option.dataset.prefix = value.prefix;
    }
    select.appendChild(option);
  });
}

gradeChecker.addEventListener("change", () => {
  const option = gradeChecker.selectedOptions[0];
  prefixDisplay.value = option?.dataset.prefix || "—";
});

dryRunBox.addEventListener("change", updateActionButton);
dryRunBox.checked = true;
updateActionButton();

document.querySelector("#load-devices").addEventListener("click", async () => {
  ftpStatus.textContent = "Loading devices…";
  try {
    const data = await readJson(await fetch("/api/ftp/devices", { headers: headers() }));
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
      await fetch(`/api/ftp/projects?device=${encodeURIComponent(deviceSelect.value)}`, { headers: headers() })
    );
    fillSelect(projectSelect, data.projects, "Select a project");
    ftpStatus.textContent = `${data.projects.length} projects found for ${data.device}.`;
  } catch (error) {
    ftpStatus.textContent = error.message;
  }
});

previewButton.addEventListener("click", () => {
  callPreview();
});

actionButton.addEventListener("click", () => {
  if (dryRunBox.checked) {
    callRun(true, false);
    return;
  }
  if (!lastPreview) {
    log.textContent = "Run Preview first.";
    return;
  }
  document.querySelector("#confirm-grade").textContent = lastPreview.grade_checker;
  document.querySelector("#confirm-prefix").textContent = lastPreview.prefix;
  document.querySelector("#confirm-device").textContent = deviceSelect.value;
  document.querySelector("#confirm-project").textContent = projectSelect.value;
  document.querySelector("#confirm-new").textContent = String(lastPreview.totals?.new ?? 0);
  document.querySelector("#confirm-existing").textContent = String(lastPreview.totals?.existing ?? 0);
  confirmDialog.showModal();
});

document.querySelector("#cancel-upload").addEventListener("click", () => {
  confirmDialog.close();
});

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
    fillSelect(gradeChecker, data.grade_checkers, "Select a grade checker");
    if (data.grade_checkers.length === 1) {
      gradeChecker.value = data.grade_checkers[0].id;
      prefixDisplay.value = data.grade_checkers[0].prefix;
    }
    dryRunBox.checked = true;
    updateActionButton();
    ftpStatus.textContent = data.ftp_configured
      ? "FTP credentials are configured. Load devices to begin."
      : "FTP credentials are not configured. Set TCC_T48_DEVICE_USER and TCC_T48_DEVICE_PASS on the server.";
  } catch (error) {
    ftpStatus.textContent = error.message;
  }
}

loadConfig();
