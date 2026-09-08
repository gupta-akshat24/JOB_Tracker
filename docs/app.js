/* Job Radar dashboard. Vanilla JS, no build step, no framework, no CDN
 * dependency beyond the Google Fonts stylesheet already linked in
 * index.html. Fetches ../data/*.json at load and renders whichever tab
 * the URL hash points to. */

(function () {
  "use strict";

  const STAGES = ["discovered", "saved", "applied", "responded", "interview", "offer", "rejected"];
  const DEFAULT_TAB = "feed";

  const state = {
    jobs: [],
    runs: [],
    pipeline: {},
    loaded: false,
    loadError: null,
  };

  const viewEl = document.getElementById("view");
  const lastRunChip = document.getElementById("last-run-chip");

  async function loadData() {
    try {
      const [jobsRes, runsRes, pipelineRes] = await Promise.all([
        fetch("../data/jobs.json", { cache: "no-store" }),
        fetch("../data/runs.json", { cache: "no-store" }),
        fetch("../data/pipeline.json", { cache: "no-store" }),
      ]);
      state.jobs = jobsRes.ok ? await jobsRes.json() : [];
      state.runs = runsRes.ok ? await runsRes.json() : [];
      state.pipeline = pipelineRes.ok ? await pipelineRes.json() : {};
      state.loaded = true;
    } catch (e) {
      state.loadError = String(e);
      state.jobs = [];
      state.runs = [];
      state.pipeline = {};
    }
  }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (k === "class") node.className = v;
        else if (k === "html") node.innerHTML = v;
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v);
      }
    }
    (children || []).forEach((c) => {
      if (c == null) return;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function timeAgo(iso) {
    if (!iso) return "date unknown";
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "date unknown";
    const diffMs = Date.now() - then;
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return new Date(then).toISOString().slice(0, 10);
  }

  function emptyState(title, body) {
    return el("div", { class: "empty" }, [
      el("div", {}, [el("b", {}, [title])]),
      el("div", { style: "margin-top:6px" }, [body]),
    ]);
  }

  // --- FEED ------------------------------------------------------------

  function renderFeed() {
    const container = el("div", {});
    container.appendChild(el("h1", { class: "page-title" }, ["Feed"]));
    container.appendChild(el("p", { class: "page-sub" }, ["Newest matches first."]));

    if (state.jobs.length === 0) {
      container.appendChild(
        emptyState(
          "No matches yet.",
          "The collector runs every 30 minutes once the GitHub Action is enabled. Check System Health to see if it's run at all, and add companies to config.yaml if it has run but found nothing."
        )
      );
      return container;
    }

    const tracks = [...new Set(state.jobs.map((j) => j.track).filter(Boolean))].sort();
    const cities = [...new Set(state.jobs.map((j) => (j.location || "").trim()).filter(Boolean))].sort();
    const sources = [...new Set(state.jobs.map((j) => j.source).filter(Boolean))].sort();

    const filters = { track: "", minScore: "", city: "", source: "" };

    const trackSel = el("select", { onchange: (e) => { filters.track = e.target.value; renderList(); } },
      [el("option", { value: "" }, ["All tracks"]), ...tracks.map((t) => el("option", { value: t }, [t]))]);
    const scoreSel = el("select", { onchange: (e) => { filters.minScore = e.target.value; renderList(); } },
      [el("option", { value: "" }, ["Any score"]), ...[9, 7, 5, 3].map((s) => el("option", { value: s }, [`score ≥ ${s}`]))]);
    const citySel = el("select", { onchange: (e) => { filters.city = e.target.value; renderList(); } },
      [el("option", { value: "" }, ["All cities"]), ...cities.map((c) => el("option", { value: c }, [c]))]);
    const sourceSel = el("select", { onchange: (e) => { filters.source = e.target.value; renderList(); } },
      [el("option", { value: "" }, ["All sources"]), ...sources.map((s) => el("option", { value: s }, [s]))]);

    const filterBar = el("div", { class: "filters" }, [trackSel, scoreSel, citySel, sourceSel]);
    container.appendChild(filterBar);

    const listHolder = el("div", {});
    container.appendChild(listHolder);

    function renderList() {
      const filtered = state.jobs.filter((j) => {
        if (filters.track && j.track !== filters.track) return false;
        if (filters.minScore && !((j.score || 0) >= Number(filters.minScore))) return false;
        if (filters.city && (j.location || "").trim() !== filters.city) return false;
        if (filters.source && j.source !== filters.source) return false;
        return true;
      });

      listHolder.innerHTML = "";
      if (filtered.length === 0) {
        listHolder.appendChild(emptyState("Nothing matches these filters.", "Clear a filter above to widen the feed."));
        return;
      }

      const ul = el("ul", { class: "feed" });
      filtered.forEach((j) => ul.appendChild(renderJobRow(j)));
      listHolder.appendChild(ul);
    }

    renderList();
    return container;
  }

  function renderJobRow(j) {
    const hasScore = j.score !== null && j.score !== undefined;
    const scoreEl = el("div", { class: "score" + (hasScore ? "" : " unscored") }, [hasScore ? String(j.score) : "?"]);

    const band = j.min_years_required != null
      ? `up to ${Number(j.min_years_required).toFixed(0)} yrs`
      : (j.experience_stated === false ? "yrs not stated" : "yrs n/a");

    const metaBits = [j.location || "location n/a", band, j.source || "", timeAgo(j.discovered_at || j.posted_at)];
    const meta = el("div", { class: "job-meta" });
    metaBits.forEach((bit, i) => {
      if (i > 0) meta.appendChild(el("span", { class: "sep" }, ["·"]));
      meta.appendChild(document.createTextNode(bit));
    });

    const titleLine = el("p", { class: "job-title" }, [
      (j.title || "untitled") + " ",
      el("span", { class: "company" }, ["— " + (j.company || "unknown company")]),
      j.track_priority === "low" ? el("span", { class: "badge-low-priority" }, ["low priority track"]) : null,
    ]);

    const body = [];
    if (j.track) body.push(el("p", { class: "job-line" }, [el("span", { class: "label" }, ["Track: "]), j.track]));
    if (j.why) body.push(el("p", { class: "job-line" }, [el("span", { class: "label" }, ["Why: "]), j.why]));
    if (j.gap) body.push(el("p", { class: "job-line" }, [el("span", { class: "label" }, ["Gap: "]), j.gap]));

    const foot = el("div", { class: "job-foot" }, [
      el("span", { class: "variant" }, [j.resume_variant ? `Use: ${j.resume_variant}` : ""]),
      j.url ? el("a", { class: "apply-link", href: j.url, target: "_blank", rel: "noopener" }, ["Open posting"]) : el("span", {}, [""]),
    ]);

    return el("li", { class: "job" }, [scoreEl, el("div", {}, [titleLine, meta, ...body, foot])]);
  }

  // --- WHERE -------------------------------------------------------------

  function renderWhere() {
    const container = el("div", {});
    container.appendChild(el("h1", { class: "page-title" }, ["Where the jobs are"]));
    container.appendChild(el("p", { class: "page-sub" }, ["Only counts what's actually in jobs.json — no decoration."]));

    if (state.jobs.length === 0) {
      container.appendChild(emptyState("Nothing to chart yet.", "Charts fill in once the collector finds matches."));
      return container;
    }

    container.appendChild(hbarChartBlock(
      "Matches by city",
      "location",
      (j) => (j.location || "unspecified").trim() || "unspecified",
      null
    ));
    container.appendChild(hbarChartBlock(
      "Matches by company (top 15)",
      "company",
      (j) => j.company || "unknown",
      15
    ));
    container.appendChild(sparklineBlock());

    return container;
  }

  function hbarChartBlock(title, key, keyFn, topN) {
    const counts = new Map();
    state.jobs.forEach((j) => {
      const k = keyFn(j);
      counts.set(k, (counts.get(k) || 0) + 1);
    });
    let entries = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    if (topN) entries = entries.slice(0, topN);
    const max = entries.length ? entries[0][1] : 1;

    const block = el("div", { class: "chart-block" }, [
      el("h2", {}, [title]),
      el("p", { class: "chart-note" }, [`x-axis: number of matches. ${entries.length} ${key === "location" ? "location(s)" : "compan" + (entries.length === 1 ? "y" : "ies")}.`]),
    ]);
    entries.forEach(([label, count]) => {
      const pct = Math.max(4, Math.round((count / max) * 100));
      block.appendChild(el("div", { class: "hbar-row" }, [
        el("div", { class: "hbar-label", title: label }, [label]),
        el("div", { class: "hbar-track" }, [el("div", { class: "hbar-fill", style: `width:${pct}%` })]),
        el("div", { class: "hbar-value" }, [String(count)]),
      ]));
    });
    return block;
  }

  function sparklineBlock() {
    const days = 30;
    const today = new Date();
    today.setUTCHours(0, 0, 0, 0);
    const counts = new Array(days).fill(0);
    const dayKeys = [];
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(today.getTime() - i * 86400000);
      dayKeys.push(d.toISOString().slice(0, 10));
    }
    const indexOf = new Map(dayKeys.map((k, i) => [k, i]));

    state.jobs.forEach((j) => {
      const ts = j.discovered_at || j.posted_at;
      if (!ts) return;
      const key = String(ts).slice(0, 10);
      if (indexOf.has(key)) counts[indexOf.get(key)] += 1;
    });

    const w = 800, h = 90, padL = 24, padB = 18, padT = 10;
    const max = Math.max(1, ...counts);
    const stepX = (w - padL - 8) / (days - 1);
    const points = counts.map((c, i) => {
      const x = padL + i * stepX;
      const y = padT + (h - padT - padB) * (1 - c / max);
      return [x, y];
    });
    const pathD = points.map((p, i) => (i === 0 ? "M" : "L") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");

    const svgNs = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNs, "svg");
    svg.setAttribute("class", "sparkline");
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.setAttribute("preserveAspectRatio", "none");

    const axis = document.createElementNS(svgNs, "line");
    axis.setAttribute("class", "axis");
    axis.setAttribute("x1", padL); axis.setAttribute("x2", w - 8);
    axis.setAttribute("y1", h - padB); axis.setAttribute("y2", h - padB);
    svg.appendChild(axis);

    const path = document.createElementNS(svgNs, "path");
    path.setAttribute("class", "line");
    path.setAttribute("d", pathD);
    svg.appendChild(path);

    [0, Math.floor(days / 2), days - 1].forEach((i) => {
      const t = document.createElementNS(svgNs, "text");
      t.setAttribute("class", "tick");
      t.setAttribute("x", points[i][0]);
      t.setAttribute("y", h - 4);
      t.setAttribute("text-anchor", i === 0 ? "start" : i === days - 1 ? "end" : "middle");
      t.textContent = dayKeys[i].slice(5);
      svg.appendChild(t);
    });
    const maxLabel = document.createElementNS(svgNs, "text");
    maxLabel.setAttribute("class", "tick");
    maxLabel.setAttribute("x", 2); maxLabel.setAttribute("y", padT + 8);
    maxLabel.textContent = String(max);
    svg.appendChild(maxLabel);

    return el("div", { class: "chart-block" }, [
      el("h2", {}, ["Matches per day, last 30 days"]),
      el("p", { class: "chart-note" }, ["y-axis: matches discovered that day (max " + max + "). x-axis: date."]),
      svg,
    ]);
  }

  // --- FUNNEL --------------------------------------------------------------

  function renderFunnel() {
    const container = el("div", {});
    container.appendChild(el("h1", { class: "page-title" }, ["My funnel"]));
    container.appendChild(el("p", { class: "page-sub" }, ["From data/pipeline.json — only what you've actually recorded."]));

    const entries = Object.entries(state.pipeline);
    const discoveredCount = state.jobs.length;

    if (discoveredCount === 0) {
      container.appendChild(emptyState("Nothing discovered yet.", "The funnel fills in once the collector finds matches and you start tracking them with scripts/track.py."));
      return container;
    }

    const statusCounts = {};
    STAGES.forEach((s) => (statusCounts[s] = 0));
    entries.forEach(([, e]) => {
      if (statusCounts[e.status] !== undefined) statusCounts[e.status] += 1;
    });

    // Cumulative "reached at least this stage" counts, since we only store
    // current status. rejected/offer are terminal outcomes counted on their
    // own, not stacked into each other.
    const rank = { saved: 1, applied: 2, responded: 3, interview: 4, offer: 5, rejected: 5 };
    function reached(minRank) {
      return entries.filter(([, e]) => (rank[e.status] || 0) >= minRank).length;
    }

    const rows = [
      { stage: "Discovered", count: discoveredCount },
      { stage: "Saved", count: reached(1) },
      { stage: "Applied", count: reached(2) },
      { stage: "Responded", count: reached(3) },
      { stage: "Interview", count: reached(4) },
      { stage: "Offer", count: statusCounts.offer },
      { stage: "Rejected", count: statusCounts.rejected },
    ];

    const max = discoveredCount || 1;
    let prev = null;
    rows.forEach((r) => {
      const pct = Math.max(2, Math.round((r.count / max) * 100));
      const dropText = prev == null ? "" : (prev - r.count >= 0 ? `-${prev - r.count}` : "");
      container.appendChild(el("div", { class: "funnel-row" }, [
        el("div", { class: "stage" }, [r.stage]),
        el("div", { class: "funnel-track" }, [el("div", { class: "funnel-fill", style: `width:${pct}%` })]),
        el("div", { class: "count" }, [String(r.count)]),
        el("div", { class: "drop" }, [r.stage === "Offer" || r.stage === "Rejected" ? "" : dropText]),
      ]));
      if (r.stage !== "Offer") prev = r.count; // offer/rejected are siblings off "Interview"
    });

    // Median days discovered -> applied
    const days = entries
      .map(([, e]) => {
        if (!e.applied_at || !e.discovered_at) return null;
        const d = (new Date(e.applied_at) - new Date(e.discovered_at)) / 86400000;
        return Number.isFinite(d) && d >= 0 ? d : null;
      })
      .filter((d) => d !== null)
      .sort((a, b) => a - b);
    let median = null;
    if (days.length) {
      const mid = Math.floor(days.length / 2);
      median = days.length % 2 ? days[mid] : (days[mid - 1] + days[mid]) / 2;
    }

    container.appendChild(el("div", { style: "margin-top:20px" }, [
      el("div", { class: "stat-line" }, [
        el("span", { class: "k" }, ["Median days, discovered → applied"]),
        el("span", { class: "v" }, [median != null ? median.toFixed(1) : "not enough data"]),
      ]),
      el("div", { class: "stat-line" }, [
        el("span", { class: "k" }, ["Jobs tracked in pipeline.json"]),
        el("span", { class: "v" }, [String(entries.length) + " / " + discoveredCount]),
      ]),
    ]));

    if (entries.length === 0) {
      container.appendChild(emptyState(
        "You haven't tracked any jobs yet.",
        "Run: python scripts/track.py <job-id> saved — job ids are in the Feed view's posting links, or in data/jobs.json."
      ));
    }

    return container;
  }

  // --- HEALTH ------------------------------------------------------------

  function renderHealth() {
    const container = el("div", {});
    container.appendChild(el("h1", { class: "page-title" }, ["System health"]));
    container.appendChild(el("p", { class: "page-sub" }, ["From data/runs.json."]));

    if (state.runs.length === 0) {
      container.appendChild(emptyState(
        "No runs recorded yet.",
        "Enable the collect.yml GitHub Action (or run python -m src.collect locally) to populate this view."
      ));
      return container;
    }

    const runsDesc = [...state.runs].sort((a, b) => new Date(b.started_at) - new Date(a.started_at));
    const lastRun = runsDesc[0];
    const now = Date.now();
    const runs24h = runsDesc.filter((r) => now - new Date(r.started_at).getTime() < 24 * 3600 * 1000);

    // Sources that failed in the last 3 successful runs, every time.
    const lastOk = runsDesc.filter((r) => r.status === "ok").slice(0, 3);
    const brokenTargets = [];
    if (lastOk.length === 3) {
      const targetFailCounts = new Map();
      const seenAtAll = new Map();
      lastOk.forEach((run) => {
        Object.entries(run.sources || {}).forEach(([sourceName, s]) => {
          (s.failures || []).forEach((f) => {
            const key = `${sourceName}: ${f.target}`;
            targetFailCounts.set(key, (targetFailCounts.get(key) || 0) + 1);
          });
        });
      });
      targetFailCounts.forEach((count, key) => {
        if (count >= 3) brokenTargets.push(key);
      });
    }

    if (brokenTargets.length) {
      container.appendChild(el("div", { class: "banner" }, [
        el("strong", {}, ["Failing 3 runs in a row: "]),
        brokenTargets.join(", "),
        " — check the slug/URL in config.yaml, the source may have changed its endpoint.",
      ]));
    }

    const f = lastRun.filter || {};
    container.appendChild(el("div", { style: "margin-top:8px" }, [
      el("div", { class: "stat-line" }, [el("span", { class: "k" }, ["Last run"]), el("span", { class: "v" }, [lastRun.started_at ? timeAgo(lastRun.started_at) : "unknown"])]),
      el("div", { class: "stat-line" }, [el("span", { class: "k" }, ["Last run status"]), el("span", { class: "v" }, [lastRun.status || "unknown"])]),
      el("div", { class: "stat-line" }, [el("span", { class: "k" }, ["Runs in last 24h"]), el("span", { class: "v" }, [String(runs24h.length) + " (expected ~48)"])]),
      el("div", { class: "stat-line" }, [el("span", { class: "k" }, ["Jobs seen (last run)"]), el("span", { class: "v" }, [String(f.input ?? "n/a")])]),
      el("div", { class: "stat-line" }, [el("span", { class: "k" }, ["Filtered out (last run)"]), el("span", { class: "v" }, [String((f.input ?? 0) - (f.kept ?? 0))])]),
      el("div", { class: "stat-line" }, [el("span", { class: "k" }, ["Matched (last run)"]), el("span", { class: "v" }, [String(f.kept ?? "n/a")])]),
    ]));

    container.appendChild(el("h2", { style: "font-size:14px; margin:24px 0 4px;" }, ["Sources (last run)"]));
    const sources = lastRun.sources || {};
    if (Object.keys(sources).length === 0) {
      container.appendChild(emptyState("No source data on the last run.", "This can happen on a run that failed before fetching started."));
    } else {
      Object.entries(sources).forEach(([name, s]) => {
        const broken = (s.failures || []).length > 0;
        container.appendChild(el("div", { class: "source-row" + (broken ? " broken" : "") }, [
          el("span", { class: "name" }, [name + ` (${s.targets} target${s.targets === 1 ? "" : "s"})`]),
          el("span", { class: broken ? "status-broken" : "status-ok" }, [
            broken ? `${s.failures.length} failing — ${s.jobs} jobs anyway` : `ok — ${s.jobs} jobs`,
          ]),
        ]));
      });
    }

    if (lastRun.error) {
      container.appendChild(el("div", { class: "banner", style: "margin-top:20px" }, [
        el("strong", {}, ["Last run failed: "]), lastRun.error,
      ]));
    }

    return container;
  }

  // --- routing -------------------------------------------------------------

  const RENDERERS = { feed: renderFeed, where: renderWhere, funnel: renderFunnel, health: renderHealth };

  function currentTab() {
    const h = (location.hash || "").replace("#", "");
    return RENDERERS[h] ? h : DEFAULT_TAB;
  }

  function render() {
    const tab = currentTab();
    document.querySelectorAll("nav.tabs a").forEach((a) => {
      a.classList.toggle("active", a.dataset.tab === tab);
    });
    viewEl.innerHTML = "";
    if (!state.loaded) {
      viewEl.appendChild(emptyState("Loading…", state.loadError ? `Couldn't load data: ${escapeHtml(state.loadError)}` : "Fetching data/jobs.json, runs.json and pipeline.json."));
      return;
    }
    viewEl.appendChild(RENDERERS[tab]());

    if (state.runs.length) {
      const runsDesc = [...state.runs].sort((a, b) => new Date(b.started_at) - new Date(a.started_at));
      lastRunChip.textContent = "last run " + timeAgo(runsDesc[0].started_at);
    } else {
      lastRunChip.textContent = "no runs yet";
    }
  }

  window.addEventListener("hashchange", render);

  loadData().then(render);
})();
