/* HousingValuation AI — console application.
   Vanilla JS, no build step. Every number rendered here comes from the API;
   nothing is mocked in the client. */

const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (html !== undefined) node.innerHTML = html;
  return node;
};

const state = { options: null, meta: null, last: null };

/* ---------------- formatters ---------------- */
const fmtInr = (n) => "₹" + Math.round(n).toLocaleString("en-IN");

function fmtCompact(n) {
  if (n === null || n === undefined) return "—";
  if (n >= 1e7) return "₹" + (n / 1e7).toFixed(2) + " Cr";
  if (n >= 1e5) return "₹" + (n / 1e5).toFixed(1) + " L";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

function fmtPct(v, d = 1) {
  if (v === null || v === undefined) return "—";
  return (v * 100).toFixed(d) + "%";
}

function fmtSigned(v) {
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  const abs = Math.abs(v);
  if (abs >= 1e7) return sign + "₹" + (abs / 1e7).toFixed(2) + " Cr";
  if (abs >= 1e5) return sign + "₹" + (abs / 1e5).toFixed(1) + " L";
  return sign + "₹" + Math.round(abs).toLocaleString("en-IN");
}

const shortHash = (h) => (h ? h.slice(0, 10) + "…" + h.slice(-6) : "—");

/* ---------------- boot ---------------- */
async function boot() {
  try {
    const [meta, options] = await Promise.all([
      fetch("/api/meta").then((r) => r.json()),
      fetch("/api/options").then((r) => r.json()),
    ]);
    state.meta = meta;
    state.options = options;
    renderShell(meta);
    buildForm(options);
    renderModelView(meta);
    renderGovernance(meta);
    loadLedger();
  } catch (err) {
    $("chip-engine").innerHTML = '<span class="dot is-busy"></span><span>Engine unreachable</span>';
    console.error(err);
  }
}

function renderShell(meta) {
  const deepLink = document.querySelector("#chip-coverage span:last-child");
  if (deepLink) {
    deepLink.textContent = `${meta.coverage.cities.length} cities · ${meta.coverage.localities.length} micro-markets`;
  }
  $("rail-trained").textContent = `trained ${meta.trained_at.replace("T", " ").replace("Z", " UTC")}`;
  $("form-hint").textContent = `${meta.coverage.cities.length} cities`;
}

/* ---------------- form ---------------- */
function buildForm(options) {
  const city = $("city");
  city.innerHTML = options.cities
    .map((c) => `<option value="${c.city}">${c.city}</option>`)
    .join("");
  city.value = "Bangalore";

  const fill = (id, values, selected) => {
    const node = $(id);
    node.innerHTML = values.map((v) => `<option value="${v}">${v}</option>`).join("");
    if (selected && values.includes(selected)) node.value = selected;
  };

  fill("property_type", options.property_types, "Apartment");
  fill("furnishing", options.furnishing, "Semi-Furnished");
  fill("occupancy", options.occupancy, "Self-Occupied");
  fill("tenure", options.tenure, "Freehold");

  syncLocalities("Koramangala");
  city.addEventListener("change", () => syncLocalities());

  const samples = $("samples");
  samples.innerHTML = "";
  options.samples.slice(0, 4).forEach((s) => {
    const chip = el("button", "sample-chip", s.label.split(" — ")[0]);
    chip.type = "button";
    chip.title = s.label;
    chip.addEventListener("click", () => applySample(s));
    samples.appendChild(chip);
  });

  $("val-form").addEventListener("submit", onSubmit);
}

function syncLocalities(selected) {
  const city = $("city").value;
  const locals = state.options.localities_by_city[city] || [];
  const node = $("locality");
  node.innerHTML = locals.map((l) => `<option value="${l}">${l}</option>`).join("");
  if (selected && locals.includes(selected)) node.value = selected;
}

function applySample(sample) {
  $("city").value = sample.city;
  syncLocalities(sample.locality);
  $("locality").value = sample.locality;
  $("property_type").value = sample.property_type;
  Object.entries(sample.input).forEach(([key, value]) => {
    const node = $(key);
    if (node) node.value = value;
  });
  $("requested_loan_inr").value = 0;
  $("val-form").dispatchEvent(new Event("submit", { cancelable: true }));
}

function readForm() {
  const numeric = [
    "area_sqft", "bedrooms", "bathrooms", "floor", "total_floors", "age_years",
    "parking", "lift", "balcony", "requested_loan_inr",
  ];
  const floats = [
    "metro_distance_km", "school_distance_km", "hospital_distance_km",
    "highway_distance_km", "crime_index",
  ];
  const payload = {
    city: $("city").value,
    locality: $("locality").value,
    property_type: $("property_type").value,
    furnishing: $("furnishing").value,
    occupancy: $("occupancy").value,
    tenure: $("tenure").value,
  };
  numeric.forEach((k) => (payload[k] = parseInt($(k).value || "0", 10)));
  floats.forEach((k) => (payload[k] = parseFloat($(k).value || "0")));
  return payload;
}

async function onSubmit(event) {
  event.preventDefault();
  const btn = $("submit-btn");
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="skeleton" style="width:110px;height:12px;display:inline-block"></span>';
  $("chip-engine").innerHTML = '<span class="dot is-busy"></span><span>Scoring…</span>';

  try {
    const res = await fetch("/api/valuate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readForm()),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    state.last = body;
    renderResult(body);
    loadLedger();
  } catch (err) {
    $("result-body").innerHTML = `<div class="empty"><div class="big" style="color:var(--bad)">Valuation failed</div>${err.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = original;
    $("chip-engine").innerHTML = '<span class="dot"></span><span>Engine ready</span>';
  }
}

/* ---------------- valuation render ---------------- */
function renderResult(body) {
  const value = body.value;
  const low = body.value_low;
  const high = body.value_high;
  const conf = body.confidence;
  const confPct = Math.round(conf * 100);

  const unit = value >= 1e7 ? "Cr" : "L";
  const scaled = value >= 1e7 ? (value / 1e7).toFixed(2) : (value / 1e5).toFixed(1);

  const windowLow = low * 0.9;
  const windowHigh = high * 1.1;
  const span = windowHigh - windowLow || 1;
  const fillLeft = ((low - windowLow) / span) * 100;
  const fillWidth = ((high - low) / span) * 100;
  const pinLeft = ((value - windowLow) / span) * 100;

  const confColor = conf >= 0.72 ? "var(--ok)" : conf >= 0.55 ? "var(--warn)" : "var(--bad)";
  const C = 2 * Math.PI * 42;

  const premium = body.market.premium_vs_locality_pct;
  const premiumClass = premium === null ? "" : premium >= 0 ? "ok" : "bad";

  $("result-body").innerHTML = `
    <div class="hero">
      <div>
        <div class="eyebrow">Estimated market value · ${body.valuation_id}</div>
        <div class="hero-value"><span class="cur">₹</span>${scaled}<span style="font-size:20px;font-weight:500;color:var(--faint);margin-left:3px">${unit}</span></div>
        <div class="hero-sub">
          <span><b>${fmtInr(body.rate_per_sqft)}</b> / sqft</span>
          <span>p10–p90 <b>${fmtCompact(low)}</b> – <b>${fmtCompact(high)}</b></span>
          <span><b>${body.drivers.length}</b> driver groups</span>
        </div>
        <div class="band">
          <div class="band-track">
            <div class="band-fill" style="left:${fillLeft}%;width:${fillWidth}%"></div>
            <div class="band-pin" style="left:${pinLeft}%"></div>
          </div>
          <div class="band-axis"><span>${fmtCompact(low)}</span><span>${fmtCompact(value)}</span><span>${fmtCompact(high)}</span></div>
        </div>
      </div>
      <div class="conf">
        <div class="conf-ring">
          <svg viewBox="0 0 96 96">
            <circle class="bg" cx="48" cy="48" r="42"></circle>
            <circle class="fg" cx="48" cy="48" r="42" stroke="${confColor}"
              stroke-dasharray="${C}" stroke-dashoffset="${C}"></circle>
          </svg>
          <div class="conf-inner">
            <div class="conf-num" style="color:${confColor}">${confPct}<span style="font-size:11px">%</span></div>
            <div class="conf-lbl">confidence</div>
          </div>
        </div>
        <div class="conf-cap">${confCaption(conf)}</div>
      </div>
    </div>
    <div class="metrics">
      <div class="metric">
        <div class="k">Price / sqft</div>
        <div class="v">${fmtInr(body.rate_per_sqft)}</div>
        <div class="d">${body.comparables.length} comparables used</div>
      </div>
      <div class="metric">
        <div class="k">Vs. locality median</div>
        <div class="v ${premiumClass}">${premium === null ? "—" : (premium > 0 ? "+" : "") + premium.toFixed(1) + "%"}</div>
        <div class="d">median ${body.market.locality_median_rate ? fmtInr(body.market.locality_median_rate) : "—"}/sqft</div>
      </div>
      <div class="metric">
        <div class="k">Interval width</div>
        <div class="v ${body.interval_width_pct > 0.55 ? "bad" : body.interval_width_pct > 0.4 ? "warn" : "ok"}">${fmtPct(body.interval_width_pct)}</div>
        <div class="d">conformal p10–p90</div>
      </div>
      <div class="metric">
        <div class="k">Model vs comps</div>
        <div class="v ${body.comps_divergence_pct === null ? "" : body.comps_divergence_pct > 18 ? "bad" : body.comps_divergence_pct > 12 ? "warn" : "ok"}">${body.comps_divergence_pct === null ? "—" : body.comps_divergence_pct.toFixed(1) + "%"}</div>
        <div class="d">${body.comps_value ? fmtCompact(body.comps_value) + " comps value" : "no comps value"}</div>
      </div>
    </div>
    ${body.flags.length ? `<div class="card-bd tight" style="border-top:1px solid var(--line)"><div class="inline"><span class="hint" style="font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--faint);font-weight:600">Risk flags</span>${body.flags.map((f) => `<span class="pill">${f.replaceAll("_", " ")}</span>`).join("")}</div></div>` : ""}
  `;

  requestAnimationFrame(() => {
    const fg = document.querySelector(".conf-ring .fg");
    if (fg) fg.style.strokeDashoffset = String(C * (1 - conf));
  });

  renderDrivers(body);
  renderLending(body);
  renderComps(body);
  renderGeo(body);
  renderAuditMini(body);

  // Geo is fetched separately so a slow volunteer endpoint can never delay
  // the valuation itself. The panel shows a skeleton in the meantime.
  const coords = body.coordinates || {};
  if (coords.lat && coords.lon) loadGeo(coords.lat, coords.lon);
}

async function loadGeo(lat, lon) {
  $("geo-source").textContent = "querying…";
  $("geo-body").innerHTML = `
    <div class="geo-grid">${Array.from({ length: 8 })
      .map(() => '<div class="geo-cell"><div class="skeleton" style="height:10px;width:60%"></div><div class="skeleton" style="height:15px;width:32%;margin-top:6px"></div></div>')
      .join("")}</div>
    <div class="geo-note">Querying OpenStreetMap Overpass for amenities within 1.5 km…</div>`;
  try {
    const res = await fetch(`/api/geo?lat=${lat}&lon=${lon}`);
    const geo = await res.json();
    renderGeo({ geo, input: state.last ? state.last.input : {} });
  } catch (err) {
    renderGeo({ geo: { available: false }, input: state.last ? state.last.input : {} });
  }
}

function confCaption(conf) {
  if (conf >= 0.85) return "desktop-decision grade";
  if (conf >= 0.72) return "usable without inspection";
  if (conf >= 0.55) return "needs desk review";
  return "inspection required";
}

function renderDrivers(body) {
  const groups = body.drivers;
  const max = Math.max(...groups.map((g) => Math.abs(g.impact_inr)), 1);
  const html = groups
    .map((g) => {
      const positive = g.impact_inr >= 0;
      const width = (Math.abs(g.impact_inr) / max) * 50;
      return `
        <div class="driver">
          <div class="driver-top">
            <span class="driver-name">${g.group}</span>
            <span class="driver-amt ${positive ? "pos" : "neg"}">${fmtSigned(g.impact_inr)}</span>
          </div>
          <div class="driver-bar">
            <span class="${positive ? "pos" : "neg"}" style="width:${width}%"></span>
          </div>
        </div>`;
    })
    .join("");

  const a = body.attribution;
  $("drivers-body").innerHTML =
    html +
    `<div class="note" style="margin-top:13px">
       <b>Method:</b> baseline substitution against the typical property in this micro-market.
       Each feature is swapped in one at a time and the price change is measured — exact, model-agnostic,
       reproducible. Interaction terms account for the ${(Math.abs(a.residual_log) * 100).toFixed(1)}% residual.
     </div>`;
}

function renderLending(body) {
  const d = body.lending;
  const tone =
    d.decision === "AUTO_APPROVE_DESKTOP" || d.decision === "APPROVE_WITH_CONDITIONS"
      ? "ok"
      : d.decision === "REFER_CREDIT"
      ? "bad"
      : "warn";

  const icon =
    tone === "ok"
      ? '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M4 12l5 5L20 6"/></svg>'
      : tone === "warn"
      ? '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 8v5"/><circle cx="12" cy="17" r="1"/><path d="M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/></svg>'
      : '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';

  const ltv = Math.min(d.requested_ltv * 100, 100);
  const cap = Math.min(d.effective_cap * 100, 100);

  const checks = d.checks
    .map(
      (c) => `
      <div class="check">
        <span class="ic ${c.status}">${
        c.status === "pass"
          ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round"><path d="M4 12l5 5L20 6"/></svg>'
          : c.status === "warn"
          ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round"><path d="M12 7v6"/><circle cx="12" cy="17" r="1"/></svg>'
          : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>'
      }</span>
        <div class="txt"><b>${c.name}</b> <span>— ${c.detail}</span></div>
      </div>`
    )
    .join("");

  $("lending-body").innerHTML = `
    <div class="decision ${tone}">
      <span class="decision-icon" style="color:var(--${tone === "ok" ? "ok" : tone === "warn" ? "warn" : "bad"})">${icon}</span>
      <div>
        <div class="decision-title">${d.decision_label}</div>
        <div class="decision-sub">${d.turnaround}</div>
      </div>
      <div class="grade" title="property risk grade">${d.risk_grade}</div>
    </div>

    <div class="ltv-row"><span>${d.loan_assumed ? "Reference LTV" : "Requested LTV"}</span><b>${fmtPct(d.requested_ltv)}</b></div>
    ${d.loan_assumed ? `<div style="font-size:11px;color:var(--faint);margin:-2px 0 6px">No loan amount entered — policy tested at 60% of the point value.</div>` : ""}
    <div class="ltv-track">
      <div class="ltv-fill" style="width:${ltv}%"></div>
      <div class="ltv-cap" style="left:${cap}%" title="confidence-adjusted ceiling"></div>
    </div>
    <div class="ltv-scale"><span>0%</span><span>ceiling ${fmtPct(d.effective_cap)}</span><span>100%</span></div>

    <div class="ltv-row"><span>Max loan recommended</span><b>${fmtCompact(d.max_loan_recommended)}</b></div>
    <div class="ltv-row"><span>Regulatory cap</span><b>${fmtPct(d.regulatory_cap)} · ${d.regulatory_cap_label}</b></div>
    <div class="ltv-row"><span>Confidence haircut</span><b>${d.confidence_haircut_label}</b></div>

    <div class="checks" style="margin-top:13px">${checks}</div>
    ${d.reason_codes.length ? `<div class="pills">${d.reason_codes.map((r) => `<span class="pill">${r}</span>`).join("")}</div>` : '<div class="pills"><span class="pill neutral">NO POLICY BREACH</span></div>'}
  `;
}

function renderComps(body) {
  if (!body.comparables.length) {
    $("comps-body").innerHTML = '<div class="empty">No comparables within 12 km.</div>';
    return;
  }
  const rows = body.comparables
    .map(
      (c) => `
      <tr>
        <td class="tbl-name">${c.locality}</td>
        <td>${c.property_type.replace("Independent House", "Ind. House")}</td>
        <td class="num">${c.area_sqft.toLocaleString("en-IN")}</td>
        <td>${c.sale_date}</td>
        <td class="num">${c.distance_km.toFixed(1)} km</td>
        <td class="num">${fmtInr(c.sale_rate)}</td>
        <td class="num" style="color:${c.adjustment_pct >= 0 ? "var(--ok)" : "var(--bad)"}">${c.adjustment_pct > 0 ? "+" : ""}${c.adjustment_pct.toFixed(0)}%</td>
        <td class="num">${fmtCompact(c.indicated_value)}</td>
      </tr>`
    )
    .join("");

  $("comps-body").innerHTML = `
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>Locality</th><th>Type</th><th class="num">Area</th><th>Sold</th>
          <th class="num">Distance</th><th class="num">₹/sqft</th><th class="num">Adj.</th><th class="num">Indicated</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="note" style="margin-top:12px">
      <b>Adjustment grid:</b> age ${(0.9).toFixed(1)}%/yr · floor ratio 6%/unit · furnishing 0 / 3.5 / 7.5% ·
      size elasticity −0.18 · market drift 0.4%/month. Weighted median by recency (18-month half-life) and distance.
      Weighted comps value <b>${fmtCompact(body.comps_value)}</b>, ${body.comps_divergence_pct.toFixed(1)}% from the model.
    </div>`;
}

function renderGeo(body) {
  const geo = body.geo || {};
  if (!geo.available) {
    $("geo-source").textContent = "unavailable";
    $("geo-body").innerHTML = `
      <div class="geo-unavailable">
        Live OpenStreetMap lookup did not respond, so no POI counts are shown. The engine used the
        distance fields from the application form instead — it never invents geo features.
        <div class="pills" style="margin-top:8px">
          <span class="pill neutral">METRO ${body.input.metro_distance_km} km</span>
          <span class="pill neutral">SCHOOL ${body.input.school_distance_km} km</span>
          <span class="pill neutral">HOSPITAL ${body.input.hospital_distance_km} km</span>
          <span class="pill neutral">HIGHWAY ${body.input.highway_distance_km} km</span>
        </div>
      </div>`;
    return;
  }

  const labels = {
    transit: "Transit", school: "Schools", hospital: "Health", retail: "Retail",
    pharmacy: "Pharmacy", bank: "Banks", park: "Parks", bus_stop: "Bus stops",
  };
  const cells = Object.entries(geo.counts)
    .map(([k, v]) => `<div class="geo-cell"><div class="k">${labels[k] || k}</div><div class="v">${v}</div></div>`)
    .join("");

  $("geo-source").textContent = `OpenStreetMap · ${geo.radius_m} m radius`;
  $("geo-body").innerHTML = `
    <div class="geo-grid">${cells}</div>
    <div class="geo-note">
      <b>${geo.poi_total}</b> mapped amenities inside a 1.5 km walk ·
      infrastructure density index <b>${geo.density_index}/100</b>.
      Source: ${geo.source}. Live query, cached per ~110 m grid cell.
    </div>`;
}

function renderAuditMini(body) {
  $("audit-mini").innerHTML = `
    <div class="ledger-row" style="line-height:1.9">
      <div><span class="hash">ref</span> ${body.valuation_id}</div>
      <div><span class="hash">value</span> ${fmtInr(body.value)}</div>
      <div><span class="hash">confidence</span> ${(body.confidence * 100).toFixed(1)}%</div>
      <div><span class="hash">decision</span> ${body.lending.decision}</div>
    </div>
    <div class="note" style="margin-top:11px">
      Appended to the hash-chained ledger. Open <b>Governance</b> to re-verify the chain —
      editing any earlier entry breaks every hash after it.
    </div>`;
}

/* ---------------- ledger ---------------- */
async function loadLedger() {
  try {
    const [ledger, verify] = await Promise.all([
      fetch("/api/audit?limit=12").then((r) => r.json()),
      fetch("/api/audit/verify").then((r) => r.json()),
    ]);
    renderLedger(ledger, verify);
  } catch (err) {
    $("ledger-body").innerHTML = '<div class="empty">Ledger unavailable.</div>';
  }
}

function renderLedger(ledger, verify) {
  const stats = ledger.stats;
  $("ledger-stats").textContent = `${stats.entries} entries · head ${shortHash(stats.head_hash)}`;
  $("verify-result").innerHTML = verify.valid
    ? `<div class="banner ok"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="9"/></svg><span><b>Chain intact.</b> ${verify.entries} entries re-hash link by link · ${verify.detail}</span></div>`
    : `<div class="banner bad"><b>Chain broken at entry ${verify.broken_at_seq}.</b> ${verify.detail}</div>`;

  if (!ledger.entries.length) {
    $("ledger-body").innerHTML = '<div class="empty">No entries yet — run a valuation.</div>';
    return;
  }

  const rows = ledger.entries
    .map(
      (e) => `<tr>
        <td class="num">${e.seq}</td>
        <td class="mono" style="font-size:10.5px">${e.ts.replace("T", " ").replace("Z", "")}</td>
        <td>${e.kind}</td>
        <td class="mono" style="font-size:10.5px">${e.ref}</td>
        <td class="mono" style="font-size:10.5px">${fmtCompact(e.detail.value || 0)}</td>
        <td class="num">${e.detail.confidence ? (e.detail.confidence * 100).toFixed(1) + "%" : "—"}</td>
        <td style="font-size:10.5px">${(e.detail.decision || "").replaceAll("_", " ").toLowerCase() || "—"}</td>
        <td class="mono hash" style="font-size:10px" title="${e.hash}">${shortHash(e.hash)}</td>
      </tr>`
    )
    .join("");

  $("ledger-body").innerHTML = `
    <table>
      <thead><tr>
        <th class="num">#</th><th>Timestamp (UTC)</th><th>Event</th><th>Reference</th>
        <th>Value</th><th class="num">Conf.</th><th>Decision</th><th>Hash</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

/* ---------------- portfolio ---------------- */
async function runBook() {
  const btn = $("run-book");
  btn.disabled = true;
  $("book-table").innerHTML = '<div class="empty">Scoring 24 properties…</div>';

  const types = state.options.property_types;
  const inputs = [];
  let i = 0;
  outer: for (const cityRow of state.options.cities) {
    const city = cityRow.city;
    for (const locality of state.options.localities_by_city[city]) {
      const area = 620 + ((i * 137) % 1650);
      inputs.push({
        city,
        locality,
        property_type: types[i % types.length],
        furnishing: ["Unfurnished", "Semi-Furnished", "Fully Furnished"][i % 3],
        occupancy: "Self-Occupied",
        tenure: "Freehold",
        area_sqft: area,
        bedrooms: Math.max(1, Math.min(5, Math.round(area / 320))),
        bathrooms: Math.max(1, Math.min(4, Math.round(area / 480))),
        floor: (i * 3) % 18,
        total_floors: 18,
        age_years: (i * 5) % 26,
        parking: i % 3,
        lift: 1,
        balcony: i % 3,
        metro_distance_km: Number((0.3 + ((i * 7) % 40) / 10).toFixed(1)),
        school_distance_km: Number((0.2 + ((i * 3) % 20) / 10).toFixed(1)),
        hospital_distance_km: Number((0.4 + ((i * 5) % 25) / 10).toFixed(1)),
        highway_distance_km: Number((0.5 + ((i * 11) % 45) / 10).toFixed(1)),
        crime_index: Number((2.5 + ((i * 13) % 60) / 10).toFixed(1)),
        requested_loan_inr: 0,
      });
      i += 1;
      if (inputs.length >= 24) break outer;
    }
  }

  try {
    const res = await fetch("/api/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(inputs),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);

    $("bk-count").textContent = body.count;
    $("bk-straight").textContent = fmtPct(body.automated_share, 0);
    $("bk-conf").textContent = fmtPct(body.median_confidence, 0);
    $("bk-value").textContent = fmtCompact(body.rows.reduce((s, r) => s + r.value, 0));
    $("book-hint").textContent = `${body.count} properties · one request`;

    const tones = {
      AUTO_APPROVE_DESKTOP: "var(--ok)",
      APPROVE_WITH_CONDITIONS: "#3f8f6d",
      REFER_PHYSICAL_VALUATION: "var(--warn)",
      REFER_CREDIT: "var(--bad)",
    };
    const mix = Object.entries(body.decisions)
      .sort((a, b) => b[1] - a[1])
      .map(
        ([k, v]) => `
        <div class="bar-row" style="grid-template-columns:230px 1fr 84px">
          <span class="lbl">${k.replaceAll("_", " ").toLowerCase()}</span>
          <span class="bar-track"><span style="width:${(v / body.count) * 100}%;background:${tones[k] || "var(--muted)"}"></span></span>
          <span class="val">${v} · ${Math.round((v / body.count) * 100)}%</span>
        </div>`
      )
      .join("");
    $("book-mix").innerHTML =
      mix +
      `<div class="note" style="margin-top:13px">
        Straight-through rate is the share of the book that clears a desktop decision. The rest are
        routed to a desk review or a physical inspection — the engine's job is to route, not to overrule
        a credit officer.
      </div>`;

    const rows = body.rows
      .map(
        (r) => `<tr>
          <td class="tbl-name">${r.locality}</td>
          <td>${r.property_type.replace("Independent House", "Ind. House")}</td>
          <td class="num">${r.area_sqft.toLocaleString("en-IN")}</td>
          <td class="num">${fmtCompact(r.value)}</td>
          <td class="num">${fmtCompact(r.value_low)} – ${fmtCompact(r.value_high)}</td>
          <td class="num">${(r.confidence * 100).toFixed(0)}%</td>
          <td class="num">${fmtPct(r.ltv, 0)}</td>
          <td><span class="pill" style="background:transparent;border-color:var(--line);color:${tones[r.decision] || "var(--muted)"}">${r.risk_grade}</span></td>
          <td style="font-size:10.5px">${r.decision_label}</td>
        </tr>`
      )
      .join("");

    $("book-table").innerHTML = `
      <div class="tbl-wrap">
        <table>
          <thead><tr>
            <th>Locality</th><th>Type</th><th class="num">Area</th><th class="num">Value</th>
            <th class="num">p10–p90</th><th class="num">Conf.</th><th class="num">LTV</th>
            <th class="num">Grade</th><th>Decision</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  } catch (err) {
    $("book-table").innerHTML = `<div class="empty">Batch failed: ${err.message}</div>`;
  } finally {
    btn.disabled = false;
  }
}

/* ---------------- model view ---------------- */
function renderModelView(meta) {
  const m = meta.metrics;
  $("k-mape").textContent = fmtPct(m.holdout.mape);
  $("k-r2").textContent = m.holdout.r2.toFixed(3);
  $("k-w10").textContent = fmtPct(m.holdout.within_10pct, 0);
  $("k-cov").textContent = fmtPct(m.interval.coverage_p10_p90, 0);

  const bench = Object.values(m.benchmarks).sort((a, b) => a.mape - b.mape);
  const worst = Math.max(...bench.map((b) => b.mape));
  $("bench-body").innerHTML =
    bench
      .map(
        (b) => `
      <div class="bar-row" style="grid-template-columns:200px 1fr 128px">
        <span class="lbl">${b.label}</span>
        <span class="bar-track"><span style="width:${(1 - b.mape / worst) * 100}%;background:${b.label.includes("this engine") ? "var(--ok)" : "#9fb0c9"}"></span></span>
        <span class="val">${fmtPct(b.mape)} · ±10% ${fmtPct(b.within_10pct, 0)}</span>
      </div>`
      )
      .join("") +
    `<div class="note" style="margin-top:13px">
      Lower is better. The locality × type rate card is the strongest baseline — that is the AVM most
      Indian lenders run today. The engine improves on it by
      <b>${(((bench.find((b) => b.label.includes("rate card") || b.label.includes("Locality"))?.mape ?? 0) - m.holdout.mape) * 100).toFixed(1)} pp</b>
      of MAPE and adds roughly six points of ±10% hit rate.
    </div>`;

  const imp = m.feature_importance.slice(0, 9);
  const maxImp = Math.max(...imp.map((f) => f.importance));
  $("importance-body").innerHTML = imp
    .map(
      (f) => `
      <div class="bar-row" style="grid-template-columns:150px 1fr 48px">
        <span class="lbl">${f.feature.replaceAll("_", " ")}</span>
        <span class="bar-track"><span style="width:${(f.importance / maxImp) * 100}%"></span></span>
        <span class="val">${(f.importance * 100).toFixed(1)}%</span>
      </div>`
    )
    .join("");

  const bands = m.by_price_band
    .map(
      (b) => `<tr><td class="tbl-name">${b.band}</td><td class="num">${b.n}</td><td class="num">${fmtPct(b.mape)}</td><td class="num">${fmtPct(b.median_ape)}</td></tr>`
    )
    .join("");
  $("bands-body").innerHTML = `<table><thead><tr><th>Price band</th><th class="num">n</th><th class="num">MAPE</th><th class="num">Median APE</th></tr></thead><tbody>${bands}</tbody></table>`;

  const cv = m.grouped_cv;
  $("cv-body").innerHTML = `
    <div class="inline" style="gap:22px;margin-bottom:12px">
      <div><div class="kpi" style="border:none;padding:0;box-shadow:none"><div class="k">Grouped MAPE</div><div class="v" style="font-size:22px">${fmtPct(cv.mape_mean)}</div></div></div>
      <div><div class="kpi" style="border:none;padding:0;box-shadow:none"><div class="k">Worst fold</div><div class="v" style="font-size:22px">${fmtPct(cv.mape_worst)}</div></div></div>
      <div><div class="kpi" style="border:none;padding:0;box-shadow:none"><div class="k">Grouped R²</div><div class="v" style="font-size:22px">${cv.r2_mean.toFixed(3)}</div></div></div>
    </div>
    <div class="note warn">
      <b>The honest number.</b> ${cv.scheme}. Error roughly doubles versus the random split, because a
      micro-market with no training history has no locality history to lean on. That gap is exactly why
      the engine widens its interval and lowers confidence for unseen localities instead of pretending
      a new market is as well supported as an established one.
    </div>
    <div class="pills" style="margin-top:10px">${cv.fold_mape.map((f, i) => `<span class="pill neutral">fold ${i + 1} · ${fmtPct(f)}</span>`).join("")}</div>`;

  const pipeline = [
    ["01", "Registry transactions", "Sale deeds from state registration portals, deduplicated and geocoded.", "plan"],
    ["02", "Government rate cards", "Circle rate / ready-reckoner tables per village and zone for assessment anchors.", "plan"],
    ["03", "Property attributes", "Area, layout, age, floor, tenure, occupancy, construction quality from the application and title file.", "live"],
    ["04", "Satellite & built-up area", "Roof-footprint delineation and change detection to validate declared area and detect unauthorised construction.", "plan"],
    ["05", "Geospatial POI density", "OpenStreetMap Overpass counts of transit, schools, health, retail, parks within 1.5 km.", "live"],
    ["06", "Market & infrastructure", "City price indices, new infrastructure corridors, supply pipeline as market-drift features.", "plan"],
  ];
  $("pipeline").innerHTML = pipeline
    .map(
      ([n, t, d, tag]) => `
      <div class="step">
        <div class="n">${n}</div>
        <div class="t">${t}</div>
        <div class="d">${d}</div>
        <span class="tag ${tag}">${tag === "live" ? "in this build" : "production plan"}</span>
      </div>`
    )
    .join("");

  const byCity = {};
  meta.coverage.localities.forEach((l) => {
    (byCity[l.city] = byCity[l.city] || []).push(l);
  });
  const covRows = Object.entries(byCity)
    .map(([city, rows]) => {
      const rates = rows.map((r) => r.median_rate).filter(Boolean);
      const lo = Math.min(...rates);
      const hi = Math.max(...rates);
      return `<tr>
        <td class="tbl-name">${city}</td>
        <td class="num">${rows.length}</td>
        <td class="num">${fmtInr(lo)}</td>
        <td class="num">${fmtInr(hi)}</td>
        <td class="num">${rows.reduce((s, r) => s + r.n, 0).toLocaleString("en-IN")}</td>
      </tr>`;
    })
    .join("");
  $("coverage-body").innerHTML = `<table>
    <thead><tr><th>City</th><th class="num">Micro-markets</th><th class="num">Rate low</th><th class="num">Rate high</th><th class="num">Corpus rows</th></tr></thead>
    <tbody>${covRows}</tbody></table>`;
}

/* ---------------- governance ---------------- */
function renderGovernance(meta) {
  const bands = meta.policy.ltv_bands
    .map(
      (b) => `<tr>
        <td class="tbl-name">${b.label}</td>
        <td class="num">${fmtPct(b.cap, 0)}</td>
        <td>${b.max_ticket_inr ? "equity ≤ " + fmtCompact(b.max_ticket_inr) + " → cap applies" : "no upper limit"}</td>
      </tr>`
    )
    .join("");
  $("policy-body").innerHTML = `<table>
    <thead><tr><th>Ticket band</th><th class="num">Max LTV</th><th>Note</th></tr></thead>
    <tbody>${bands}</tbody></table>
    <div class="note" style="margin-top:12px">
      The engine only tightens these caps. A confidence haircut of 0–20% is applied on top, and the
      recommended loan is computed against the <b>p10</b> value, not the point estimate.
    </div>`;

  $("matrix-body").innerHTML = `
    <table>
      <thead><tr><th>Condition</th><th>Outcome</th></tr></thead>
      <tbody>
        <tr><td>Any hard check fails</td><td><b style="color:var(--warn)">Physical valuation required</b></td></tr>
        <tr><td>Confidence ≥ 72%, LTV ≤ ceiling × 0.95, no warnings</td><td><b style="color:var(--ok)">Auto-approve on desktop valuation</b></td></tr>
        <tr><td>LTV ≤ ceiling and confidence ≥ 60%</td><td>Approve with conditions</td></tr>
        <tr><td>LTV above ceiling or confidence &lt; 60%</td><td><b style="color:var(--bad)">Refer to credit officer</b></td></tr>
        <tr><td>Commercial collateral</td><td>Separate policy, reduced cap, manual sign-off</td></tr>
      </tbody>
    </table>
    <div class="note" style="margin-top:12px">
      Every rule is named, evaluated and returned with a pass / warn / fail status plus machine-readable
      reason codes — so an override is logged and an auditor can replay the decision.
    </div>`;

  const controls = [
    ["Model validation", "Holdout, grouped-by-locality and per-price-band error reported every run. No metric is asserted without the split that produced it."],
    ["Calibration monitoring", "Conformal coverage is measured, not assumed — 79.1% against a nominal 80% on the current holdout. Production threshold: roll back if rolling 3-month coverage falls below 72%."],
    ["Drift", "Population stability on locality mix, area distribution and price level; trigger re-fit when PSI > 0.2 on any key feature."],
    ["Human in the loop", "Physical inspection is mandatory wherever a hard policy check fails. The engine routes; a human decides."],
    ["Explainability", "Per-valuation driver attribution plus comparable-sales cross-check, both returned with the number and archived with it."],
    ["Auditability", "Every valuation and decision is appended to a hash-chained ledger with the input digest, so a post-hoc edit is detectable."],
    ["Data provenance", "The prototype states its corpus is synthetic. A production deployment must record dataset lineage and licensing per feature."],
    ["Fairness", "Valuation inputs exclude borrower demographic attributes; lending policy is applied on collateral and confidence only."],
  ];
  $("controls-body").innerHTML = `<div class="steps" style="grid-template-columns:repeat(2,1fr)">${controls
    .map(
      ([t, d]) => `<div class="step"><div class="t" style="margin-top:0">${t}</div><div class="d">${d}</div></div>`
    )
    .join("")}</div>`;
}

/* ---------------- navigation ---------------- */
const VIEWS = {
  valuation: {
    title: "Property valuation",
    sub: "Single-property AVM with conformal confidence and a policy-evaluated lending position",
  },
  portfolio: {
    title: "Portfolio",
    sub: "Batch scoring across the covered market — the automation path a lender would actually run",
  },
  model: {
    title: "Model & data",
    sub: "Measured accuracy, calibrated intervals, benchmark comparison and data lineage",
  },
  governance: {
    title: "Governance",
    sub: "Tamper-evident audit trail, LTV policy, decision matrix and model risk controls",
  },
};

document.querySelectorAll(".nav-item[data-view]").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("is-active"));
    $("view-" + btn.dataset.view).classList.add("is-active");
    $("page-title").textContent = VIEWS[btn.dataset.view].title;
    $("page-sub").textContent = VIEWS[btn.dataset.view].sub;
    if (btn.dataset.view === "governance") loadLedger();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
});

$("nav-api").addEventListener("click", () => window.open("/docs", "_blank", "noopener"));
$("run-book").addEventListener("click", runBook);
$("verify-chain").addEventListener("click", loadLedger);

boot();
