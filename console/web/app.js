let latest = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    headers: {"Content-Type": "application/json"},
    ...options
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || data.message || "Request failed");
  return data;
}

function setMessage(value) {
  document.getElementById("message").textContent = value;
}

function stateClass(state) {
  if (state === "RUNNING") return "running";
  if (state === "STARTING") return "starting";
  if (state === "READY") return "ready";
  if (state === "FAILED") return "error";
  return "stopped";
}

async function updateRouterSources() {
  const box = document.getElementById("router-sources");
  if (!box) return;
  try {
    const data = await api("/api/router/sources");
    box.innerHTML = (data.sources || []).map(item => {
      const encoded = encodeURIComponent(item.name);
      return [
        '<div class="ref-row">',
        '<div class="ref-row-head"><span class="ref-name">' + item.name + '</span><span class="badge ' + (item.exists ? "ready" : "stopped") + '">' + (item.exists ? "READY" : "MISSING") + '</span></div>',
        '<div class="ref-path">' + item.folder + '</div>',
        '<div class="ref-actions">',
        '<button onclick="browseRouterSource(' + "'" + encoded + "'" + ')">CHANGE FOLDER</button>',
        '</div>',
        '</div>'
      ].join("");
    }).join("");
  } catch (error) {
    box.textContent = error.message;
  }
}

async function browseRouterSource(encodedName) {
  const name = decodeURIComponent(encodedName);
  setMessage("Opening folder picker...");
  try {
    const picked = await api("/api/reference/browse");
    if (!picked.success) {
      setMessage(picked.message);
      return;
    }
    await api("/api/router/source", {
      method: "POST",
      body: JSON.stringify({name: name, folder: picked.path})
    });
    setMessage(name + " folder updated; restarting Router...");
    await api("/api/service/router/restart", {method: "POST", body: "{}"});
    await updateRouterSources();
    setTimeout(refresh, 800);
  } catch (error) {
    setMessage(error.message);
  }
}

function updateService(name, item) {
  const badge = document.getElementById(name + "-badge");
  const state = document.getElementById(name + "-state");
  const pid = document.getElementById(name + "-pid");
  const uptime = document.getElementById(name + "-uptime");
  const detail = document.getElementById(name + "-detail");

  badge.textContent = item.state;
  badge.className = "badge " + stateClass(item.state);
  state.textContent = item.state;
  pid.textContent = item.pid || "—";
  uptime.textContent = item.uptime_seconds ? formatUptime(item.uptime_seconds) : "—";
  detail.textContent = JSON.stringify({
    state: item.state,
    pid: item.pid,
    health: item.health,
    last_error: item.last_error || ""
  }, null, 2);
}

function formatUptime(seconds) {
  seconds = Math.floor(seconds || 0);
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
}

function updateReference(data) {
  const rows = data.databases || [];
  rows.forEach(item => {
    const el = document.getElementById(item.name.toLowerCase() + "-state");
    if (el) el.textContent = item.status;
  });

  const ready = rows.filter(x => x.store_ready).length;
  const badge = document.getElementById("reference-badge");
  badge.textContent = ready + "/" + rows.length + " READY";
  badge.className = "badge " + (ready === rows.length ? "ready" : "starting");

  const list = document.getElementById("reference-list");
  list.innerHTML = rows.map(item => {
    const required = Object.keys(item.required || {}).map(k => k + ": " + (item.required[k] ? "OK" : "MISSING")).join(" · ");
    const safe = encodeURIComponent(item.name);
    return [
      '<div class="ref-row">',
      '<div class="ref-row-head"><span class="ref-name">' + item.name + '</span><span class="badge ' + (item.store_ready ? "ready" : "stopped") + '">' + item.status + '</span></div>',
      '<div class="ref-path">SOURCE: ' + (item.source_folder || "not configured") + '</div>',
      '<div class="ref-path">STORE: ' + item.store_path + '</div>',
      '<div class="ref-path">' + (required || "Source folder not checked") + '</div>',
      '<div class="ref-actions">',
      '<button onclick="browseReference(' + "'" + safe + "'" + ')">BROWSE</button>',
      '<button onclick="validateReference(' + "'" + safe + "'" + ')">VALIDATE</button>',
      '<button onclick="reloadReference(' + "'" + safe + "'" + ')">RELOAD PARSER</button>',
      '</div>',
      '</div>'
    ].join("");
  }).join("");
}

async function refresh() {
  try {
    const data = await api("/api/status");
    latest = data;
    document.getElementById("system-state").textContent = data.system;
    document.getElementById("system-dot").style.background =
      data.system === "RUNNING" ? "var(--good)" :
      data.system === "DEGRADED" ? "var(--warn)" : "var(--muted)";
    ["router", "parser", "forwarder"].forEach(name => updateService(name, data.services[name]));
    updateReference(data.reference);
    updateRouterSources();
    document.getElementById("clock").textContent = data.time.split(" ")[1] || data.time;
  } catch (error) {
    setMessage(error.message);
  }
}

async function serviceAction(name, action) {
  setMessage(name.toUpperCase() + " " + action.toUpperCase() + "...");
  try {
    await api("/api/service/" + name + "/" + action, {method: "POST", body: "{}"});
    setMessage(name.toUpperCase() + " " + action.toUpperCase() + " requested");
  } catch (error) {
    setMessage(error.message);
  }
  setTimeout(refresh, 500);
}

async function systemAction(action) {
  setMessage("SYSTEM " + action.toUpperCase() + "...");
  try {
    await api("/api/system/" + action, {method: "POST", body: "{}"});
    setMessage("SYSTEM " + action.toUpperCase() + " requested");
  } catch (error) {
    setMessage(error.message);
  }
  setTimeout(refresh, 500);
}

function togglePanel(id) {
  document.getElementById(id).classList.toggle("open");
}

async function referenceRefresh() {
  setMessage("Checking reference stores...");
  try {
    const data = await api("/api/reference/status");
    updateReference(data);
    setMessage("Reference status updated");
  } catch (error) {
    setMessage(error.message);
  }
}

async function browseReference(encodedName) {
  const name = decodeURIComponent(encodedName);
  setMessage("Opening folder picker...");
  try {
    const picked = await api("/api/reference/browse");
    if (!picked.success) {
      setMessage(picked.message);
      return;
    }
    await api("/api/reference/source", {
      method: "POST",
      body: JSON.stringify({name: name, folder: picked.path})
    });
    setMessage(name + " source updated");
    await referenceRefresh();
  } catch (error) {
    setMessage(error.message);
  }
}

async function validateReference(encodedName) {
  const name = decodeURIComponent(encodedName);
  setMessage("Validating " + name + "...");
  try {
    const result = await api("/api/reference/validate", {
      method: "POST",
      body: JSON.stringify({name: name})
    });
    setMessage(result.message);
    await referenceRefresh();
  } catch (error) {
    setMessage(error.message);
  }
}

async function reloadReference(encodedName) {
  const name = decodeURIComponent(encodedName);
  setMessage("Checking " + name + "...");
  try {
    const result = await api("/api/reference/reload", {
      method: "POST",
      body: JSON.stringify({name: name})
    });
    setMessage(result.message || "Parser reload requested");
    setTimeout(refresh, 800);
  } catch (error) {
    setMessage(error.message);
  }
}

setInterval(refresh, 2000);
refresh();
