import { api, AuthError, clearToken, getToken, setToken } from "./api.js";
import { disposeCharts, renderCharts, rerenderCharts } from "./charts.js";

// ------------------------------------------------------------------ utilidades
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" }) : "—");
const fmtInt = (v) => (v === null || v === undefined ? "—" : Math.round(v).toLocaleString("es-ES"));
const fmtH = (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("es-ES", { maximumFractionDigits: 0 }));
const iso = (d) => d.toISOString().slice(0, 10);

const HEALTH = {
  verde: { label: "Normal", icon: "●", cls: "ok" },
  ambar: { label: "Vigilar", icon: "▲", cls: "warn" },
  rojo: { label: "Crítico", icon: "■", cls: "crit" },
  sin_datos: { label: "Sin datos", icon: "○", cls: "none" },
};
const badge = (estado) => {
  const h = HEALTH[estado] || HEALTH.sin_datos;
  return `<span class="badge ${h.cls}"><span aria-hidden="true">${h.icon}</span> ${h.label}</span>`;
};

const state = {
  meta: null,
  fleet: null,
  tipo: "Todos",
  sort: { key: "montado_en", dir: 1 },
  range: loadRange(),
};

function loadRange() {
  try {
    const r = JSON.parse(sessionStorage.getItem("ehm_range") || "null");
    if (r && r.desde && r.hasta) return r;
  } catch { /* sin almacenamiento */ }
  const hasta = new Date();
  const desde = new Date();
  desde.setFullYear(desde.getFullYear() - 1);
  return { desde: iso(desde), hasta: iso(hasta) };
}
function saveRange() {
  try { sessionStorage.setItem("ehm_range", JSON.stringify(state.range)); } catch { /* ignorar */ }
}

// ------------------------------------------------------------------ tema
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("ehm_theme", theme); } catch { /* ignorar */ }
  $("#btn-theme").textContent = theme === "dark" ? "☀ Claro" : "☾ Oscuro";
}
function initTheme() {
  let t = null;
  try { t = localStorage.getItem("ehm_theme"); } catch { /* ignorar */ }
  if (!t) t = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  applyTheme(t);
  $("#btn-theme").onclick = () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
    rerenderCharts();
  };
}

// ------------------------------------------------------------------ login
function showLogin(msg = "") {
  disposeCharts();
  $("#app-view").hidden = true;
  $("#login-view").hidden = false;
  $("#login-error").textContent = msg;
  $("#login-password").value = "";
  $("#login-password").focus();
}

async function doLogin(ev) {
  ev.preventDefault();
  const btn = $("#login-btn");
  btn.disabled = true;
  $("#login-error").textContent = "";
  try {
    const res = await api("/api/login", { method: "POST", body: { password: $("#login-password").value } });
    setToken(res.token);
    await start();
  } catch (e) {
    $("#login-error").textContent = e.message;
  } finally {
    btn.disabled = false;
  }
}

// ------------------------------------------------------------------ arranque
async function start() {
  try {
    state.meta = await api("/api/meta");
  } catch (e) {
    showLogin(e instanceof AuthError ? "" : e.message);
    return;
  }
  $("#login-view").hidden = true;
  $("#app-view").hidden = false;
  $("#demo-flag").hidden = !state.meta.demo;
  fillSearch();
  initRange();
  route();
}

function fillSearch() {
  const opts = [];
  for (const a of state.meta.aviones) opts.push(`<option value="${esc(a.matricula)}">Avión · ${esc(a.flota || "")} ${esc(a.variante || "")}</option>`);
  for (const a of state.meta.aviones) {
    for (const p of [1, 2]) {
      const sn = a[`sn${p}`];
      if (sn) opts.push(`<option value="${esc(sn)}">Motor ${p} de ${esc(a.matricula)}</option>`);
    }
  }
  $("#search-list").innerHTML = opts.join("");
}

function goSearch() {
  const q = $("#search").value.trim();
  if (!q) return;
  const ac = state.meta.aviones.find((a) => a.matricula.toUpperCase() === q.toUpperCase());
  location.hash = ac ? `#/avion/${ac.id}` : `#/motor/${encodeURIComponent(q)}`;
  $("#search").value = "";
}

function initRange() {
  $("#desde").value = state.range.desde;
  $("#hasta").value = state.range.hasta;
  const changed = () => {
    if (!$("#desde").value || !$("#hasta").value) return;
    state.range = { desde: $("#desde").value, hasta: $("#hasta").value };
    saveRange();
    route();
  };
  $("#desde").onchange = changed;
  $("#hasta").onchange = changed;
  document.querySelectorAll("[data-range]").forEach((b) => {
    b.onclick = () => {
      const months = Number(b.dataset.range);
      const hasta = new Date();
      const desde = new Date();
      desde.setMonth(desde.getMonth() - months);
      $("#desde").value = iso(desde);
      $("#hasta").value = iso(hasta);
      changed();
    };
  });
}

// ------------------------------------------------------------------ enrutado
function route() {
  const h = location.hash || "#/flota";
  const [, view, arg] = h.split("/");
  document.querySelectorAll(".nav-link").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === `#/${view}`));
  $("#range-bar").hidden = view === "flota" || !view;
  if (view === "avion" && arg) return viewAircraft(Number(arg));
  if (view === "motor" && arg) return viewEngine(decodeURIComponent(arg));
  return viewFleet();
}

function guard(fn) {
  return async (...args) => {
    const main = $("#main");
    main.innerHTML = `<div class="loading">Cargando datos…</div>`;
    disposeCharts();
    try {
      await fn(...args);
    } catch (e) {
      if (e instanceof AuthError) return showLogin("La sesión ha caducado. Vuelve a entrar.");
      main.innerHTML = `<div class="card error">${esc(e.message)}</div>`;
    }
  };
}

// ------------------------------------------------------------------ vista flota
const viewFleet = guard(async () => {
  if (!state.fleet) state.fleet = (await api("/api/fleet")).motores;
  renderFleet();
});

function renderFleet() {
  const tipos = ["Todos", ...new Set(state.meta.aviones.map((a) => a.tipo))];
  const byTipo = (x) => state.tipo === "Todos" || x.tipo === state.tipo;
  const aviones = state.meta.aviones.filter(byTipo);
  const activos = aviones.filter((a) => (a.activo || "").toUpperCase() !== "N");
  const motores = state.fleet.filter(byTipo);
  const { key, dir } = state.sort;
  motores.sort((a, b) => {
    const va = a[key], vb = b[key];
    if (va == null || vb == null) return va == null ? (vb == null ? 0 : 1) : -1; // vacíos al final
    return (va > vb ? 1 : va < vb ? -1 : 0) * dir;
  });
  const parados = motores.filter((m) => m.montado_en && m.dias_sin_volar > state.meta.dias_parada).length;

  const th = (k, label, cls = "") =>
    `<th class="sortable ${cls}" data-sort="${k}">${label}${key === k ? (dir > 0 ? " ▲" : " ▼") : ""}</th>`;

  $("#main").innerHTML = `
    <div class="page-head">
      <div><h2>Flota</h2><p class="muted">Resumen de aviones y motores. Pulsa una fila para ver el detalle.</p></div>
      <div class="chips">${tipos.map((t) => `<button class="chip ${t === state.tipo ? "on" : ""}" data-tipo="${esc(t)}">${esc(t)}</button>`).join("")}</div>
    </div>
    <div class="kpis">
      <div class="kpi"><span class="kpi-l">Aviones activos</span><span class="kpi-v">${activos.length}</span></div>
      <div class="kpi"><span class="kpi-l">Motores con vuelos registrados</span><span class="kpi-v">${motores.length}</span></div>
      <div class="kpi"><span class="kpi-l">Motores montados sin volar &gt; ${state.meta.dias_parada} días</span><span class="kpi-v">${parados}</span></div>
    </div>
    <div class="card">
      <h3>Aviones</h3>
      <div class="table-wrap"><table class="tbl">
        <thead><tr><th>Matrícula</th><th>Flota</th><th>Variante</th><th>Motor</th><th>Motor 1</th><th>Motor 2</th><th>Estado</th></tr></thead>
        <tbody>${aviones.map((a) => `
          <tr class="row-link" data-href="#/avion/${a.id}">
            <td><b>${esc(a.matricula)}</b></td><td>${esc(a.flota)}</td><td>${esc(a.variante)}</td><td>${esc(a.motor)}</td>
            <td>${a.sn1 ? `<a href="#/motor/${encodeURIComponent(a.sn1)}">${esc(a.sn1)}</a>` : "—"}</td>
            <td>${a.sn2 ? `<a href="#/motor/${encodeURIComponent(a.sn2)}">${esc(a.sn2)}</a>` : "—"}</td>
            <td>${(a.activo || "").toUpperCase() === "N" ? '<span class="muted">Inactivo</span>' : "Activo"}</td>
          </tr>`).join("")}</tbody>
      </table></div>
    </div>
    <div class="card">
      <h3>Motores</h3>
      <div class="table-wrap"><table class="tbl" id="tbl-engines">
        <thead><tr>${th("sn", "Nº de serie")}${th("montado_en", "Montado en")}${th("posicion", "Pos.")}${th("tipo", "Tipo")}
          ${th("horas", "Horas (BD)", "num")}${th("ciclos", "Ciclos (BD)", "num")}${th("horas_acms", "Horas ACMS", "num")}${th("ciclos_acms", "Ciclos ACMS", "num")}
          ${th("ultimo_vuelo", "Último vuelo")}${th("dias_sin_volar", "Días sin volar", "num")}</tr></thead>
        <tbody>${motores.map((m) => `
          <tr class="row-link" data-href="#/motor/${encodeURIComponent(m.sn)}">
            <td><b>${esc(m.sn)}</b></td>
            <td>${m.montado_en ? esc(m.montado_en) : `<span class="muted">Desmontado (último: ${esc(m.ultimo_avion)})</span>`}</td>
            <td>${m.posicion ?? "—"}</td><td>${esc(m.tipo)}</td>
            <td class="num">${fmtH(m.horas)}</td><td class="num">${fmtInt(m.ciclos)}</td>
            <td class="num">${m.acms_reiniciado ? '<span class="warn-text" title="Contador ACMS reiniciado: ver ficha del motor">⚠ </span>' : ""}${fmtH(m.horas_acms)}</td>
            <td class="num">${fmtInt(m.ciclos_acms)}</td>
            <td>${fmtDate(m.ultimo_vuelo)}</td>
            <td class="num ${m.montado_en && m.dias_sin_volar > state.meta.dias_parada ? "warn-text" : ""}">${fmtInt(m.dias_sin_volar)}</td>
          </tr>`).join("")}</tbody>
      </table></div>
      <p class="hint">Horas y ciclos (BD): calculados con los vuelos registrados que llevan el nº de serie del motor; no incluyen la vida anterior.
        Horas y ciclos ACMS: contadores que reporta el avión para cada motor (solo A321); ⚠ = el contador se reinició.</p>
    </div>`;

  document.querySelectorAll("[data-tipo]").forEach((b) => (b.onclick = () => { state.tipo = b.dataset.tipo; renderFleet(); }));
  document.querySelectorAll("[data-sort]").forEach((t) => (t.onclick = () => {
    const k = t.dataset.sort;
    state.sort = { key: k, dir: state.sort.key === k ? -state.sort.dir : 1 };
    renderFleet();
  }));
  bindRowLinks();
}

function bindRowLinks() {
  document.querySelectorAll(".row-link").forEach((tr) => {
    tr.onclick = (ev) => { if (ev.target.closest("a")) return; location.hash = tr.dataset.href; };
  });
}

// ------------------------------------------------------------------ bloques comunes
function summaryKpis(r) {
  const up = r.ultima_parada;
  const a = r.acms;
  const rs = a && a.reinicio;
  const acms = !a ? "" : rs ? `
      <div class="kpi hero"><span class="kpi-l">Horas del motor (ACMS) · estimadas</span><span class="kpi-v">≈ ${fmtH(a.estimado_horas)}</span>
        <span class="kpi-f warn-text">⚠ Contador reiniciado el ${fmtDate(rs.fecha)}: antes ${fmtH(rs.antes_horas)} h, ahora ${fmtH(a.horas)} h</span></div>
      <div class="kpi hero"><span class="kpi-l">Ciclos del motor (ACMS) · estimados</span><span class="kpi-v">≈ ${fmtInt(a.estimado_ciclos)}</span>
        <span class="kpi-f warn-text">⚠ Antes ${fmtInt(rs.antes_ciclos)}, ahora ${fmtInt(a.ciclos)}. Estimación = antes + ahora; confírmala con Ingeniería.</span></div>` : `
      <div class="kpi hero"><span class="kpi-l">Horas del motor (ACMS)</span><span class="kpi-v">${fmtH(a.horas)}</span>
        <span class="kpi-f">Último reporte ${fmtDate(a.fecha)} · ${esc(a.matricula || "")}</span></div>
      <div class="kpi hero"><span class="kpi-l">Ciclos del motor (ACMS)</span><span class="kpi-v">${fmtInt(a.ciclos)}</span>
        <span class="kpi-f">Contadores que reporta el avión para este motor</span></div>`;
  const reg = a ? " registradas en BD" : " totales";
  return `
    <div class="kpis">
      ${acms}
      <div class="kpi ${a ? "" : "hero"}"><span class="kpi-l">Horas${reg}</span><span class="kpi-v ${a ? "sm" : ""}">${fmtH(r.horas_totales)}</span></div>
      <div class="kpi ${a ? "" : "hero"}"><span class="kpi-l">Ciclos${reg}</span><span class="kpi-v ${a ? "sm" : ""}">${fmtInt(r.ciclos_totales)}</span></div>
      <div class="kpi"><span class="kpi-l">Últimos 30 días</span><span class="kpi-v sm">${fmtH(r.horas_30d)} h · ${fmtInt(r.ciclos_30d)} ciclos</span></div>
      <div class="kpi"><span class="kpi-l">Últimos 12 meses</span><span class="kpi-v sm">${fmtH(r.horas_12m)} h · ${fmtInt(r.ciclos_12m)} ciclos</span></div>
      <div class="kpi"><span class="kpi-l">Desde la última parada (posible C-check)</span>
        <span class="kpi-v sm">${up ? `${fmtH(r.horas_desde_ultima_parada)} h · ${fmtInt(r.ciclos_desde_ultima_parada)} ciclos` : "Sin paradas"}</span>
        ${up ? `<span class="kpi-f">${fmtDate(up.desde)} → ${fmtDate(up.hasta)} (${up.dias} días)</span>` : ""}</div>
      <div class="kpi"><span class="kpi-l">Último vuelo</span><span class="kpi-v sm">${fmtDate(r.ultimo_vuelo)}</span>
        <span class="kpi-f">${r.dias_sin_volar != null ? `hace ${fmtInt(r.dias_sin_volar)} días` : ""} · primer registro ${fmtDate(r.primer_vuelo)}</span></div>
    </div>`;
}

function stopsTable(paradas) {
  if (!paradas.length) return `<p class="muted">No hay paradas de más de ${state.meta.dias_parada} días.</p>`;
  return `<div class="table-wrap"><table class="tbl compact"><thead><tr><th>Último vuelo antes</th><th>Primer vuelo después</th><th class="num">Días</th></tr></thead>
    <tbody>${[...paradas].reverse().map((p) => `<tr><td>${fmtDate(p.desde)}</td><td>${fmtDate(p.hasta)}</td><td class="num">${p.dias}</td></tr>`).join("")}</tbody></table></div>`;
}

function eventsTable(eventos, mode) {
  if (!eventos.length) return `<p class="muted">No hay eventos registrados.</p>`;
  const { desde, hasta } = state.range;
  const inRange = eventos.filter((e) => !e.fecha || (e.fecha.slice(0, 10) >= desde && e.fecha.slice(0, 10) <= hasta));
  return `
    <p class="hint">${inRange.length} evento(s) en el periodo seleccionado · ${eventos.length} en total.</p>
    <div class="table-wrap tall"><table class="tbl compact">
      <thead><tr><th>Fecha</th><th>Matrícula</th><th>Ruta</th>${mode === "aircraft" ? "<th>Motor</th>" : ""}<th>Tipo</th><th>Descripción</th></tr></thead>
      <tbody>${inRange.map((e) => `<tr>
        <td class="nowrap">${e.fecha ? fmtDate(e.fecha) : esc(e.fecha_texto)}</td><td>${esc(e.matricula)}</td>
        <td class="nowrap">${esc(e.origen || "")}→${esc(e.destino || "")}</td>
        ${mode === "aircraft" ? `<td>${e.motor ? `${e.motor}${e.sn ? ` <span class="muted">(${esc(e.sn)})</span>` : ""}` : "Avión"}</td>` : ""}
        <td>${e.tipos.map((t) => `<span class="tag ${["EGT", "Core", "Vibración"].includes(t) ? "tag-eng" : ""}">${esc(t)}</span>`).join(" ")}</td>
        <td class="desc">${esc(e.texto)}</td></tr>`).join("")}</tbody>
    </table></div>`;
}

function healthCard(salud) {
  return `<ul class="reasons">${salud.motivos.map((m) => `<li>${badge(m.nivel)} ${esc(m.texto)}</li>`).join("")}</ul>
    <p class="hint">Media de los últimos vuelos frente a la referencia de hace 6–12 meses. Umbrales en <code>backend/app/health_rules.json</code>.</p>`;
}

function sourceNote(tipo, hasSeries) {
  const empty = hasSeries ? "" : " <b>No hay reportes en el periodo seleccionado.</b>";
  if (tipo === "A321") return `<div class="card note">Parámetros de motor de los reportes ACMS del A321: REPORT01 (crucero) y REPORT04 (despegue).${empty}</div>`;
  if (tipo === "ATR") return `<div class="card note">Parámetros de motor del reporte REPORT02 del ATR, que se genera en crucero (no hay reporte de despegue).
    En ATR, la gráfica de "EGT" muestra la <b>ITT</b>, "N1" es <b>NL</b> y "N2" es <b>NH</b>.${empty}</div>`;
  if (hasSeries) return "";
  return `<div class="card note">No hay parámetros de motor en <code>t_qar_flightsfile</code> para este periodo.</div>`;
}

// ------------------------------------------------------------------ vista motor
const viewEngine = guard(async (sn) => {
  const d = await api("/api/engine", { params: { sn, desde: state.range.desde, hasta: state.range.hasta } });
  const cur = d.actual;
  const where = cur
    ? (cur.desmontado ? `Desmontado · último avión <a href="#/avion/${cur.id_avion}">${esc(cur.matricula)}</a> (posición ${cur.pos})`
      : `Montado en <a href="#/avion/${cur.id_avion}">${esc(cur.matricula)}</a> · posición ${cur.pos} · ${esc(cur.tipo)}`)
    : "Sin vuelos registrados con este número de serie";

  $("#main").innerHTML = `
    <div class="page-head">
      <div><p class="crumb"><a href="#/flota">Flota</a> / Motor</p><h2>Motor ${esc(d.sn)} ${badge(d.salud.estado)}</h2><p class="muted">${where}</p></div>
    </div>
    ${summaryKpis(d.resumen)}
    <div class="two-col">
      <div class="card"><h3>Salud del motor</h3>${healthCard(d.salud)}</div>
      <div class="card"><h3>Historial de instalación</h3>
        <div class="table-wrap"><table class="tbl compact"><thead><tr><th>Avión</th><th>Pos.</th><th>Desde</th><th>Hasta</th><th class="num">Horas</th><th class="num">Ciclos</th></tr></thead>
        <tbody>${[...d.instalaciones].reverse().map((i) => `<tr><td><a href="#/avion/${i.id_avion}">${esc(i.matricula)}</a></td><td>${i.pos}</td>
          <td>${fmtDate(i.desde)}</td><td>${fmtDate(i.hasta)}</td><td class="num">${fmtH(i.horas)}</td><td class="num">${fmtInt(i.ciclos)}</td></tr>`).join("")}</tbody></table></div>
      </div>
    </div>
    ${sourceNote(cur?.tipo, d.series.length)}
    <div id="charts"></div>
    <div class="two-col">
      <div class="card"><h3>Paradas &gt; ${state.meta.dias_parada} días (posible C-check)</h3>${stopsTable(d.resumen.paradas)}</div>
      <div class="card"><h3>Eventos del motor</h3>${eventsTable(d.eventos, "engine")}</div>
    </div>`;
  renderCharts($("#charts"), { ...d, paradas: d.resumen.paradas, diasParada: state.meta.dias_parada }, "engine", d.sn);
});

// ------------------------------------------------------------------ vista avión
const viewAircraft = guard(async (id) => {
  const d = await api("/api/aircraft", { params: { id, desde: state.range.desde, hasta: state.range.hasta } });
  const a = d.avion;
  $("#main").innerHTML = `
    <div class="page-head">
      <div><p class="crumb"><a href="#/flota">Flota</a> / Avión</p><h2>${esc(a.matricula)}</h2>
      <p class="muted">${esc(a.flota)} · ${esc(a.variante)} · motores ${esc(a.motor)}</p></div>
    </div>
    ${summaryKpis(d.resumen)}
    <div class="two-col">
      ${d.motores.map((m) => `
        <div class="card engine-card pos-${m.pos}">
          <div class="engine-head"><span class="swatch" aria-hidden="true"></span>
            <h3>Motor ${m.pos} · <a href="#/motor/${encodeURIComponent(m.sn)}">${esc(m.sn)}</a></h3>${badge(m.salud.estado)}</div>
          <div class="mini-kpis">
            ${(() => {
              const a = m.resumen.acms;
              if (!a) return `<div><span class="kpi-l">Horas</span><b>${fmtH(m.resumen.horas_totales)}</b></div>
                <div><span class="kpi-l">Ciclos</span><b>${fmtInt(m.resumen.ciclos_totales)}</b></div>`;
              const est = !!a.reinicio;
              return `<div><span class="kpi-l">Horas ACMS${est ? " ⚠ estimadas" : ""}</span><b>${est ? "≈ " + fmtH(a.estimado_horas) : fmtH(a.horas)}</b></div>
                <div><span class="kpi-l">Ciclos ACMS${est ? " ⚠ estimados" : ""}</span><b>${est ? "≈ " + fmtInt(a.estimado_ciclos) : fmtInt(a.ciclos)}</b></div>`;
            })()}
            <div><span class="kpi-l">Desde última parada</span><b>${m.resumen.ultima_parada ? `${fmtH(m.resumen.horas_desde_ultima_parada)} h · ${fmtInt(m.resumen.ciclos_desde_ultima_parada)} c` : "—"}</b></div>
          </div>
          ${healthCard(m.salud)}
        </div>`).join("")}
    </div>
    ${sourceNote(a.tipo, d.series.length)}
    <div id="charts"></div>
    <div class="two-col">
      <div class="card"><h3>Paradas &gt; ${state.meta.dias_parada} días (posible C-check)</h3>${stopsTable(d.resumen.paradas)}</div>
      <div class="card"><h3>Eventos del avión</h3>${eventsTable(d.eventos, "aircraft")}</div>
    </div>`;
  renderCharts($("#charts"), { ...d, paradas: d.resumen.paradas, diasParada: state.meta.dias_parada }, "aircraft");
});

// ------------------------------------------------------------------ init
initTheme();
$("#login-form").onsubmit = doLogin;
$("#btn-logout").onclick = () => { clearToken(); state.fleet = null; showLogin(); };
$("#search").addEventListener("change", goSearch);
$("#search").addEventListener("keydown", (e) => { if (e.key === "Enter") goSearch(); });
$("#btn-refresh").onclick = () => { state.fleet = null; route(); };
window.addEventListener("hashchange", () => { if (getToken()) route(); });
if (getToken()) start(); else showLogin();
