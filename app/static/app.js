const tokenInput = document.querySelector("#access-token");
const accessPanel = document.querySelector("#access-panel");
const accessNote = document.querySelector("#access-note");
const form = document.querySelector("#build-form");
const log = document.querySelector("#log");
const ftpLog = document.querySelector("#ftp-log");
const ftpStatus = document.querySelector("#ftp-status");

const TOKEN_KEY = "tcc-work-order-token";

function token() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

function headers(extra = {}) {
  const value = token();
  return value ? { ...extra, "X-Access-Token": value } : extra;
}

async function readJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }
  return data;
}

function formData() {
  const data = new FormData(form);
  if (token()) {
    data.set("access_token", token());
  }
  return data;
}

function showSummary(data) {
  document.querySelector("#count-orders").textContent = data.work_orders.length;
  document.querySelector("#count-files").textContent = data.existing_files;
  document.querySelector("#count-placeholders").textContent = data.placeholder_files;
  document.querySelector("#count-output").textContent = data.output_folders;
  const names = data.work_orders.map((name) => `[ZIP FOLDER] ${name}`).join("\n");
  log.textContent = `${names}\n\n${(data.log || []).join("\n")}`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  log.textContent = "Building preview…";
  try {
    const response = await fetch("/api/preview", { method: "POST", body: formData(), headers: headers() });
    showSummary(await readJson(response));
  } catch (error) {
    log.textContent = error.message;
  }
});

document.querySelector("#download-button").addEventListener("click", async () => {
  log.textContent = "Building ZIP…";
  try {
    const response = await fetch("/api/build", { method: "POST", body: formData(), headers: headers() });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `Request failed (${response.status})`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "Work Orders.zip";
    link.click();
    URL.revokeObjectURL(url);
    log.textContent = "Downloaded Work Orders.zip";
  } catch (error) {
    log.textContent = error.message;
  }
});

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

document.querySelector("#load-devices").addEventListener("click", async () => {
  ftpStatus.textContent = "Loading devices…";
  try {
    const data = await readJson(await fetch("/api/ftp/devices", { headers: headers() }));
    fillSelect(document.querySelector("#device"), data.devices, "Select a device");
    ftpStatus.textContent = `${data.devices.length} devices found.`;
  } catch (error) {
    ftpStatus.textContent = error.message;
  }
});

document.querySelector("#load-projects").addEventListener("click", async () => {
  const device = document.querySelector("#device").value;
  if (!device) {
    ftpStatus.textContent = "Select a device first.";
    return;
  }
  ftpStatus.textContent = "Loading projects…";
  try {
    const data = await readJson(await fetch(`/api/ftp/projects?device=${encodeURIComponent(device)}`, { headers: headers() }));
    fillSelect(document.querySelector("#project"), data.projects, "Select a project");
    ftpStatus.textContent = `${data.projects.length} projects found for ${device}.`;
  } catch (error) {
    ftpStatus.textContent = error.message;
  }
});

document.querySelector("#upload-button").addEventListener("click", async () => {
  const device = document.querySelector("#device").value;
  const project = document.querySelector("#project").value;
  const dryRun = document.querySelector("#dry-run").checked;
  if (!device || !project) {
    ftpLog.textContent = "Select a device and a project.";
    return;
  }
  if (!dryRun) {
    const confirmed = window.confirm(`Upload new work orders to ${device} / ${project}? Existing work orders stay in place.`);
    if (!confirmed) {
      return;
    }
  }
  const data = formData();
  data.set("device", device);
  data.set("project", project);
  data.set("dry_run", dryRun ? "true" : "false");
  ftpLog.textContent = dryRun ? "Running dry run…" : "Uploading new work orders…";
  try {
    const result = await readJson(await fetch("/api/ftp/upload", { method: "POST", body: data, headers: headers() }));
    ftpLog.textContent = [
      result.dry_run ? "Dry run. No FTP changes were made." : "Upload finished.",
      `Target: ${result.target}`,
      `Files: ${result.files}`,
      `Directories: ${result.directories}`,
      `Skipped existing work orders: ${result.skipped_existing_work_orders}`,
      "",
      ...(result.log || []),
    ].join("\n");
  } catch (error) {
    ftpLog.textContent = error.message;
  }
});

document.querySelector("#save-token").addEventListener("click", () => {
  sessionStorage.setItem(TOKEN_KEY, tokenInput.value.trim());
  accessNote.textContent = "Token saved in this browser tab.";
  loadConfig();
});

async function loadConfig() {
  const saved = token();
  if (saved) {
    tokenInput.value = saved;
  }
  try {
    const data = await readJson(await fetch("/api/config"));
    accessPanel.hidden = !data.access_required;
    ftpStatus.textContent = data.ftp_configured
      ? "FTP credentials are configured on this server. Load devices to begin."
      : "FTP credentials are not configured. ZIP build and download still work. Set TCC_T48_DEVICE_USER and TCC_T48_DEVICE_PASS before upload.";
  } catch (error) {
    ftpStatus.textContent = error.message;
  }
}

loadConfig();
