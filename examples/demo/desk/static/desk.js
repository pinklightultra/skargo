(function () {
  const outcome = document.getElementById("outcome");
  let busy = false;

  function format(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "";
    return String(Math.round(n * 1000) / 1000);
  }

  function payload(el) {
    const body = { id: el.dataset.id, control: el.dataset.control || "" };
    if (el instanceof HTMLInputElement) {
      if (el.dataset.control === "pod-override" && el.value === "") body.value = null;
      else if (el.type === "number" || el.type === "range") body.value = Number(el.value);
      else body.value = el.value;
    }
    return body;
  }

  function paintOutcome(o) {
    const tone = o.tone || (o.ok ? "ok" : "fail");
    outcome.dataset.ready = "1";
    outcome.dataset.tone = tone;
    outcome.dataset.ran = o.id || "";
    document.getElementById("outcome-kicker").textContent = tone;
    document.getElementById("outcome-title").textContent = o.title || "Outcome";
    document.getElementById("outcome-summary").textContent = o.summary || "";
    document.getElementById("outcome-detail").textContent = o.detail || "";
    const list = document.getElementById("outcome-wrote");
    list.replaceChildren();
    const wrote = o.wrote || [];
    wrote.slice(0, 12).forEach(function (path) {
      const li = document.createElement("li");
      li.textContent = path;
      list.appendChild(li);
    });
    if (wrote.length > 12) {
      const li = document.createElement("li");
      li.textContent = "and " + (wrote.length - 12) + " more";
      list.appendChild(li);
    }
    document.querySelectorAll("button[data-id]").forEach(function (button) {
      if (button.dataset.id === o.id) button.dataset.last = tone;
    });
  }

  function paintState(s) {
    if (!s || !s.mix) return;
    const root = document.getElementById("root-path");
    const parts = String(s.root).replace(/\\/g, "/").split("/").filter(Boolean);
    root.textContent = parts.length <= 2 ? s.root : parts.slice(-2).join("/");
    root.title = s.root;
    function press(selector, on) {
      document.querySelectorAll(selector).forEach(function (el) {
        el.setAttribute("aria-pressed", on(el) ? "true" : "false");
      });
    }
    const eps = (s.eps || []).map(String);
    const muted = s.mix.muted_keys || [];
    const off = s.mix.off || {};
    press('[data-control="cast"]', function (el) { return el.dataset.value === s.cast; });
    press('[data-control="voices"]', function (el) { return el.dataset.value === s.voices; });
    press('[data-control="episode"]', function (el) { return eps.indexOf(el.dataset.value) !== -1; });
    press('[data-control="force"]', function () { return !!s.force; });
    press('[data-control="defaults"]', function () { return !!s.defaults; });
    press('[data-control="bus"]', function (el) { return off[el.dataset.bus] !== false; });
    press('[data-control="mute"]', function (el) { return muted.indexOf(el.dataset.key) !== -1; });
    document.querySelectorAll('input[data-control="fader"]').forEach(function (el) {
      if (document.activeElement === el) return;
      const value = s.mix[el.dataset.key];
      el.value = value;
      const out = el.parentElement.querySelector("output");
      if (out) out.textContent = format(value);
    });
    const pod = document.querySelector('[data-id="pod-override"]');
    if (pod && document.activeElement !== pod) pod.value = s.pod == null ? "" : s.pod;
    const kbps = document.querySelector('[data-id="kbps"]');
    if (kbps && document.activeElement !== kbps) kbps.value = s.kbps;
    const backlog = document.querySelector('[data-id="backlog"]');
    if (backlog && document.activeElement !== backlog) backlog.value = s.backlog || "";
  }

  async function post(el) {
    if (busy) {
      paintOutcome({
        id: el.dataset.id,
        title: "Busy",
        tone: "warn",
        ok: true,
        summary: "Still working. Wait for this pass to finish.",
        detail: "",
        wrote: [],
      });
      return;
    }
    busy = true;
    document.body.dataset.busy = "1";
    el.setAttribute("aria-busy", "true");
    try {
      const res = await fetch("/api/click", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload(el)),
      });
      const data = await res.json();
      if (!data.outcome) throw new Error("The desk returned no outcome.");
      paintOutcome(data.outcome);
      if (data.state) paintState(data.state);
    } catch (err) {
      paintOutcome({
        id: el.dataset.id,
        title: "Desk",
        tone: "fail",
        ok: false,
        summary: "The desk could not complete that click.",
        detail: String(err),
        wrote: [],
      });
    } finally {
      busy = false;
      document.body.dataset.busy = "0";
      el.removeAttribute("aria-busy");
    }
  }

  document.addEventListener("click", function (ev) {
    const el = ev.target.closest("button[data-id]");
    if (!el) return;
    ev.preventDefault();
    post(el);
  });

  document.addEventListener("change", function (ev) {
    const el = ev.target.closest("input[data-id]");
    if (!el) return;
    post(el);
  });

  document.addEventListener("input", function (ev) {
    const el = ev.target.closest('input[data-control="fader"]');
    if (!el) return;
    const out = el.parentElement.querySelector("output");
    if (out) out.textContent = format(el.value);
  });

})();
