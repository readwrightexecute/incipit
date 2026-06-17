/*
  Client-side session history (no server state).

  Each wizard page embeds <script id="session-meta" type="application/json">
  with {id, idea, phase}. This script upserts that into localStorage (capturing
  the final mega-prompt text on the final page), renders a "Recent" list on the
  home page, and offers a client-side viewer so past results survive even after
  the server has dropped the in-memory session.
*/
(function () {
  var KEY = "promptgen.history.v1";
  var MAX = 50;

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || []; }
    catch (e) { return []; }
  }
  function save(list) {
    try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX))); }
    catch (e) { /* quota / disabled — ignore */ }
  }

  function ensureClientId() {
    if (/(^|;\s*)pg_client=/.test(document.cookie)) return;
    var id = (Date.now().toString(36) + Math.random().toString(36).slice(2, 8));
    document.cookie = "pg_client=" + id + ";path=/;max-age=31536000;samesite=lax";
  }

  function meta() {
    var el = document.getElementById("session-meta");
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  function nowTs() { return Date.now(); }

  function upsert() {
    var m = meta();
    if (!m || !m.id) return;
    var list = load();
    var rec = null;
    for (var i = 0; i < list.length; i++) { if (list[i].id === m.id) { rec = list.splice(i, 1)[0]; break; } }
    rec = rec || { id: m.id, created: nowTs() };
    rec.idea = m.idea || rec.idea || "(untitled)";
    rec.phase = m.phase || rec.phase || "";
    rec.ts = nowTs();
    // On the final page, snapshot the assembled mega-prompt so it survives a
    // server restart / TTL sweep.
    var mp = document.getElementById("mega-prompt");
    if (m.phase === "final" && mp) rec.markdown = mp.innerText.trim();
    list.unshift(rec);
    save(list);
  }

  function rel(ts) {
    var s = Math.max(1, Math.round((nowTs() - ts) / 1000));
    if (s < 60) return s + "s ago";
    var m = Math.round(s / 60); if (m < 60) return m + "m ago";
    var h = Math.round(m / 60); if (h < 24) return h + "h ago";
    return Math.round(h / 24) + "d ago";
  }

  function esc(t) {
    var d = document.createElement("div"); d.textContent = t == null ? "" : t; return d.innerHTML;
  }

  function viewer(rec) {
    var ov = document.createElement("div");
    ov.className = "history-modal";
    ov.innerHTML =
      '<article>' +
        '<header><strong>' + esc((rec.idea || "").slice(0, 80)) + '</strong></header>' +
        (rec.markdown
          ? '<div class="section-content" style="max-height:55vh;overflow:auto">' + esc(rec.markdown) + '</div>'
          : '<p class="assumption">No saved result for this session yet.</p>') +
        '<footer class="refine-row" style="margin-top:.75rem">' +
          (rec.markdown ? '<button data-act="copy">Copy</button>' +
                          '<button class="secondary" data-act="download">Download .md</button>' : '') +
          '<a href="/sessions/' + encodeURIComponent(rec.id) + '" role="button" class="contrast outline">Open in server</a>' +
          '<button class="secondary outline" data-act="close">Close</button>' +
        '</footer>' +
      '</article>';
    function close() { ov.remove(); }
    ov.addEventListener("click", function (e) {
      if (e.target === ov) return close();
      var act = e.target.getAttribute("data-act");
      if (act === "close") return close();
      if (act === "copy") { navigator.clipboard.writeText(rec.markdown || ""); e.target.textContent = "Copied ✓"; }
      if (act === "download") {
        var blob = new Blob([rec.markdown || ""], { type: "text/markdown" });
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob); a.download = "mega-prompt.md"; a.click();
        URL.revokeObjectURL(a.href);
      }
    });
    document.body.appendChild(ov);
  }

  function renderHistory() {
    var host = document.getElementById("history");
    if (!host) return;
    var list = load();
    if (!list.length) { host.innerHTML = ""; return; }
    var rows = list.map(function (r) {
      var badge = r.markdown ? "✓ result" : esc(r.phase || "in progress");
      return '<div class="hist-item" data-id="' + esc(r.id) + '">' +
        '<div class="hist-idea">' + esc((r.idea || "(untitled)").slice(0, 90)) + '</div>' +
        '<div class="hist-meta"><small class="assumption">' + rel(r.ts) + ' · ' + badge + '</small></div>' +
        '<div class="hist-actions">' +
          '<a href="/sessions/' + encodeURIComponent(r.id) + '" role="button" class="secondary outline">Open</a>' +
          '<button class="secondary outline" data-act="view">View saved</button>' +
        '</div></div>';
    }).join("");
    host.innerHTML =
      '<details open><summary class="seg-legend" style="cursor:pointer">Recent sessions (' + list.length + ')</summary>' +
        '<div class="hist-list">' + rows + '</div>' +
        '<p><button class="secondary outline" id="hist-clear" style="font-size:.8rem">Clear history</button></p>' +
      '</details>';

    host.querySelectorAll(".hist-item").forEach(function (item) {
      var id = item.getAttribute("data-id");
      var btn = item.querySelector('[data-act="view"]');
      if (btn) btn.addEventListener("click", function () {
        var rec = load().filter(function (r) { return r.id === id; })[0];
        if (rec) viewer(rec);
      });
    });
    var clear = document.getElementById("hist-clear");
    if (clear) clear.addEventListener("click", function () {
      if (confirm("Clear all saved session history on this device?")) { save([]); renderHistory(); }
    });
  }

  function refresh() { ensureClientId(); upsert(); renderHistory(); }

  document.addEventListener("DOMContentLoaded", refresh);
  // Wizard steps swap into #wizard via htmx; re-scan after each settle so newly
  // swapped #session-meta / #history elements are picked up.
  document.body.addEventListener("htmx:afterSettle", refresh);
})();
