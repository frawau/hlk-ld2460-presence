const screensEl = document.getElementById("screens");
const statusEl = document.getElementById("status");
const screens = new Map();

function personSvg(motion) {
  const arrow =
    motion === "approaching" ? "▼" : motion === "moving_away" ? "▲" : "";
  return `<div class="person ${motion}" title="${motion}">
    <svg viewBox="0 0 24 34" width="26" height="34" fill="currentColor">
      <circle cx="12" cy="6" r="5"/>
      <rect x="6" y="13" width="12" height="16" rx="5"/>
    </svg>
    <div style="text-align:center;font-size:.7rem;line-height:1">${arrow}</div>
  </div>`;
}

function render() {
  const names = [...screens.keys()].sort();
  screensEl.innerHTML = names
    .map((name) => {
      const s = screens.get(name);
      const persons = (s.report.persons || []);
      const count = s.report.count != null ? s.report.count : persons.length;
      const icons = persons.length
        ? persons.map((p) => personSvg(p.motion || "unknown")).join("")
        : '<span class="empty">no one</span>';
      const sub = s.online
        ? `${count} ${count === 1 ? "person" : "people"} present`
        : `last seen ${s.last_seen_age}s ago`;
      return `<div class="card ${s.online ? "" : "offline"}">
        <h2><span class="dot"></span>${name}</h2>
        <div class="monitor"></div>
        <div class="people">${icons}</div>
        <div class="count">${sub}</div>
      </div>`;
    })
    .join("");
}

function applyScreen(s) {
  screens.set(s.name, s);
}

function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => (statusEl.textContent = "live");
  ws.onclose = () => {
    statusEl.textContent = "reconnecting…";
    setTimeout(connect, 1500);
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "state") {
      screens.clear();
      msg.screens.forEach(applyScreen);
    } else if (msg.type === "screen") {
      applyScreen(msg.screen);
    } else if (msg.type === "drop") {
      screens.delete(msg.name);
    }
    render();
  };
}

connect();
