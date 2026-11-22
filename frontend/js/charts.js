// Gráficas de tendencia por vuelo (ECharts). Puntos = valor de cada vuelo; línea = media móvil.
// Motor 1 = serie 1 (azul), motor 2 = serie 2 (naranja). Nunca dos ejes Y en la misma gráfica.

const GROUP = "ehm";
const MA_WINDOW = 10;
const instances = [];
let lastArgs = null;

export const CHART_DEFS = [
  { section: "EGT", id: "tof_egt", title: "EGT en despegue", unit: "°C", field: "tof_egt", events: true },
  { section: "EGT", id: "crz_egt", title: "EGT en crucero", unit: "°C", field: "crz_egt", events: true },
  { section: "Aceite", id: "oil_rate", title: "Consumo de aceite en crucero", field: "rate", source: "aceite" },
  { section: "Aceite", id: "crz_oq", title: "Cantidad de aceite en crucero", field: "crz_oq" },
  { section: "Aceite", id: "crz_op", title: "Presión de aceite en crucero", field: "crz_op" },
  { section: "Aceite", id: "crz_ot", title: "Temperatura de aceite en crucero", unit: "°C", field: "crz_ot" },
  { section: "Combustible", id: "tof_ff", title: "Fuel flow en despegue", field: "tof_ff" },
  { section: "Combustible", id: "crz_ff", title: "Fuel flow en crucero", field: "crz_ff" },
  { section: "Combustible", id: "fuel_h", title: "Combustible consumido por hora de vuelo (avión)", field: "fuel_h", aircraftLevel: true },
  { section: "Combustible", id: "fuel_used", title: "Combustible consumido por vuelo (avión)", field: "fuel_used", aircraftLevel: true },
  { section: "Otros parámetros", id: "crz_n1", title: "N1 en crucero", unit: "%", field: "crz_n1" },
  { section: "Otros parámetros", id: "crz_n2", title: "N2 en crucero", unit: "%", field: "crz_n2" },
  { section: "Otros parámetros", id: "crz_vib_n1", title: "Vibración N1 en crucero", field: "crz_vib_n1" },
  { section: "Otros parámetros", id: "crz_vib_n2", title: "Vibración N2 en crucero", field: "crz_vib_n2" },
  { section: "Otros parámetros", id: "crz_torque", title: "Torque en crucero (ATR)", unit: "%", field: "crz_torque", hideIfEmpty: true },
];

const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmtDate = (t) => new Date(t).toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" });
const fmtNum = (v) => (v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toLocaleString("es-ES", { maximumFractionDigits: 2 }));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function disposeCharts() {
  while (instances.length) {
    const { chart, ro } = instances.pop();
    ro.disconnect();
    chart.dispose();
  }
}

export function rerenderCharts() {
  if (lastArgs) renderCharts(...lastArgs);
}

/** Construye los grupos (series) de una gráfica a partir de las filas. */
function buildGroups(def, rows, mode, snLabel) {
  const colors = [css("--series-1"), css("--series-2")];
  let groups;
  if (def.aircraftLevel) {
    const seen = new Set();
    const uniq = rows.filter((r) => {
      const k = r.id_flightfile ?? r.id_vuelo;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
    groups = [{ name: "Avión", color: colors[0], rows: uniq }];
  } else if (mode === "aircraft") {
    groups = [1, 2].map((p) => ({ name: `Motor ${p}`, color: colors[p - 1], rows: rows.filter((r) => r.pos === p) }));
  } else {
    groups = [{ name: snLabel, color: colors[0], rows }];
  }
  for (const g of groups) {
    g.points = g.rows
      .filter((r) => r.fecha && r[def.field] !== null && r[def.field] !== undefined)
      .map((r) => ({ t: Date.parse(r.fecha), v: Number(r[def.field]), r }))
      .sort((a, b) => a.t - b.t);
    const win = [];
    let sum = 0;
    g.ma = g.points.map((p) => {
      win.push(p.v);
      sum += p.v;
      if (win.length > MA_WINDOW) sum -= win.shift();
      return [p.t, +(sum / win.length).toFixed(2)];
    });
  }
  return groups.filter((g) => g.points.length);
}

function chartOption(def, groups, stops, events) {
  const text2 = css("--text-secondary");
  const border = css("--border");
  const many = groups.length > 1;
  const engineEvents = def.events ? events.filter((e) => e.de_motor && e.fecha) : [];

  const series = [];
  groups.forEach((g, i) => {
    series.push({
      name: g.name, type: "scatter", symbolSize: 5,
      itemStyle: { color: g.color, opacity: 0.35 },
      emphasis: { itemStyle: { opacity: 1, borderColor: css("--surface"), borderWidth: 2 }, scale: 1.8 },
      data: g.points.map((p) => ({ value: [p.t, p.v], meta: p.r })),
    });
    const line = {
      name: g.name, type: "line", showSymbol: false, data: g.ma, z: 3,
      lineStyle: { width: 2, color: g.color }, itemStyle: { color: g.color },
      endLabel: many ? { show: true, formatter: "{a}", color: text2, fontSize: 11 } : undefined,
    };
    if (i === 0) {
      line.markArea = {
        silent: true, itemStyle: { color: css("--stop-fill") },
        label: { color: text2, fontSize: 10, position: "insideTop" },
        data: stops.map((s) => [{ name: `Parada ${s.dias} d`, xAxis: Date.parse(s.desde) }, { xAxis: Date.parse(s.hasta) }]),
      };
      if (engineEvents.length) {
        line.markLine = {
          silent: true, symbol: "none", label: { show: false },
          lineStyle: { color: css("--text-primary"), type: "dashed", width: 1, opacity: 0.45 },
          data: engineEvents.map((e) => ({ xAxis: Date.parse(e.fecha) })),
        };
      }
    }
    series.push(line);
  });

  return {
    animation: false,
    backgroundColor: "transparent",
    textStyle: { fontFamily: css("--font") },
    grid: { left: 56, right: many ? 72 : 20, top: many ? 34 : 18, bottom: 56 },
    legend: many ? {
      top: 0, left: 0, icon: "roundRect", itemWidth: 14, itemHeight: 4,
      textStyle: { color: text2 }, data: groups.map((g) => g.name),
    } : undefined,
    tooltip: {
      trigger: "axis", confine: true,
      axisPointer: { type: "line", lineStyle: { color: css("--text-muted") } },
      backgroundColor: css("--surface"), borderColor: border, textStyle: { color: css("--text-primary"), fontSize: 12 },
      formatter: (params) => tooltipHtml(params, def, engineEvents),
    },
    xAxis: {
      type: "time", axisLine: { lineStyle: { color: border } }, axisTick: { show: false },
      axisLabel: { color: text2, hideOverlap: true }, splitLine: { show: false },
    },
    yAxis: {
      type: "value", scale: true,
      axisLabel: { color: text2 }, splitLine: { lineStyle: { color: css("--grid") } },
    },
    dataZoom: [
      { type: "inside", filterMode: "none" },
      {
        type: "slider", height: 18, bottom: 10, borderColor: border, filterMode: "none",
        textStyle: { color: text2 }, fillerColor: css("--zoom-fill"), dataBackground: { lineStyle: { color: border }, areaStyle: { color: "transparent" } },
      },
    ],
    series,
  };
}

function tooltipHtml(params, def, engineEvents) {
  if (!params.length) return "";
  const t = params[0].axisValue;
  let html = `<div class="tt"><div class="tt-h">${fmtDate(t)}</div>`;
  for (const p of params) {
    if (p.seriesType === "scatter") {
      const m = p.data.meta || {};
      html += `<div>${p.marker}<b>${esc(p.seriesName)}</b>: ${fmtNum(p.value[1])}${def.unit ? " " + def.unit : ""}`
        + ` <span class="tt-m">${esc(m.matricula || "")}${m.origen || m.destino ? ` ${esc(m.origen || "")}→${esc(m.destino || "")}` : ""}`
        + ` · ${fmtDate(p.value[0])}${m.fuente ? ` · ${esc(m.fuente)}` : ""}</span></div>`;
    } else {
      html += `<div class="tt-m">${p.marker}${esc(p.seriesName)} · media ${MA_WINDOW} vuelos: ${fmtNum(p.value[1])}</div>`;
    }
  }
  const near = engineEvents.filter((e) => Math.abs(Date.parse(e.fecha) - t) < 36 * 3600 * 1000);
  for (const e of near) html += `<div class="tt-ev">⚠ Evento motor ${e.motor ?? ""}: ${esc(e.tipos.join(", "))}</div>`;
  return html + "</div>";
}

function tableHtml(def, groups) {
  const rows = groups.flatMap((g) => g.points.map((p, i) => ({ g: g.name, p, ma: g.ma[i][1] })))
    .sort((a, b) => b.p.t - a.p.t).slice(0, 300);
  return `<table class="tbl compact"><thead><tr><th>Fecha</th><th>Serie</th><th>Matrícula</th><th>Ruta</th>`
    + `<th class="num">Valor</th><th class="num">Media ${MA_WINDOW}</th></tr></thead><tbody>`
    + rows.map((x) => `<tr><td>${fmtDate(x.p.t)}</td><td>${esc(x.g)}</td><td>${esc(x.p.r.matricula)}</td>`
      + `<td>${esc(x.p.r.origen || "")}→${esc(x.p.r.destino || "")}</td><td class="num">${fmtNum(x.p.v)}</td>`
      + `<td class="num">${fmtNum(x.ma)}</td></tr>`).join("")
    + `</tbody></table><p class="hint">Últimos ${rows.length} vuelos del periodo.</p>`;
}

/**
 * Pinta todas las gráficas dentro de `container`.
 * data: { series, aceite, eventos, paradas }, mode: "aircraft" | "engine", snLabel: nombre de la serie en modo motor.
 */
export function renderCharts(container, data, mode, snLabel) {
  lastArgs = [container, data, mode, snLabel];
  disposeCharts();
  container.innerHTML = "";
  const sections = [...new Set(CHART_DEFS.map((d) => d.section))];
  let anyData = false;

  for (const section of sections) {
    const sec = document.createElement("section");
    sec.className = "chart-section";
    sec.innerHTML = `<h3>${esc(section)}</h3><div class="chart-grid"></div>`;
    const grid = sec.querySelector(".chart-grid");

    for (const def of CHART_DEFS.filter((d) => d.section === section)) {
      const rows = def.source === "aceite" ? data.aceite : data.series;
      const groups = buildGroups(def, rows || [], mode, snLabel);
      if (!groups.length && def.hideIfEmpty) continue;
      const card = document.createElement("div");
      card.className = "card chart-card";
      const sub = def.events ? `<span class="chart-sub">Línea discontinua = evento de motor · zona gris = parada &gt; ${data.diasParada} días</span>` : "";
      card.innerHTML = `
        <div class="chart-head">
          <div><h4>${esc(def.title)}${def.unit ? ` <span class="chart-unit">(${esc(def.unit)})</span>` : ""}</h4>${sub}</div>
          <div class="chart-actions">
            <button class="btn-ghost" data-act="table" type="button">Tabla</button>
            <button class="btn-ghost" data-act="png" type="button">PNG</button>
          </div>
        </div>
        <div class="chart-body"></div>
        <div class="chart-table" hidden></div>`;
      grid.appendChild(card);
      const body = card.querySelector(".chart-body");

      if (!groups.length) {
        body.classList.add("empty");
        body.textContent = "Sin datos en el periodo seleccionado";
        card.querySelectorAll("button").forEach((b) => (b.disabled = true));
        continue;
      }
      anyData = true;
      const chart = echarts.init(body, null, { renderer: "canvas" });
      chart.group = GROUP;
      chart.setOption(chartOption(def, groups, data.paradas || [], data.eventos || []));
      const ro = new ResizeObserver(() => chart.resize());
      ro.observe(body);
      instances.push({ chart, ro });

      card.querySelector('[data-act="png"]').onclick = () => {
        const a = document.createElement("a");
        a.href = chart.getDataURL({ pixelRatio: 2, backgroundColor: css("--surface") });
        a.download = `${def.id}_${(snLabel || "avion").replace(/[^\w-]+/g, "_")}.png`;
        a.click();
      };
      card.querySelector('[data-act="table"]').onclick = (ev) => {
        const tbl = card.querySelector(".chart-table");
        const show = tbl.hidden;
        if (show && !tbl.innerHTML) tbl.innerHTML = tableHtml(def, groups);
        tbl.hidden = !show;
        body.hidden = show;
        ev.target.textContent = show ? "Gráfica" : "Tabla";
        if (!show) chart.resize();
      };
    }
    container.appendChild(sec);
  }
  echarts.connect(GROUP);
  return anyData;
}
