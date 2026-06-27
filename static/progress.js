/* Gráfica "Historia": líneas de avance del acumulado de cada
 * participante, tanda por tanda.
 *
 * Render en SVG a mano (sin librería de dibujo) dentro de un contenedor
 * medido con ResizeObserver: se redibuja al cambiar de tamaño, así la
 * gráfica es responsiva y siempre ocupa todo el ancho sin distorsionar
 * los trazos (a diferencia de un viewBox estirado).
 *
 * Tres capas de línea: el telón de fondo en gris atenuado (todos los no
 * seleccionados), hasta 8 comparados con colores destacados (paleta
 * --chart-1..8, asignada por orden de selección vía Tom Select) y el
 * usuario activo en blanco grueso con halo, siempre encima.
 */
(function () {
    const root = document.getElementById("history-chart");
    const dataEl = document.getElementById("history-data");
    if (!root || !dataEl) return;

    const DATA = JSON.parse(dataEl.textContent);
    const SERIES = DATA.series;
    const TICKS = DATA.ticks;
    const ME = SERIES.find(s => s.me) || null;

    // Paleta y colores leídos de las variables CSS (fuente única en
    // source.css; se adaptan al tema sin tocar el JS).
    const css = getComputedStyle(document.documentElement);
    const v = name => css.getPropertyValue(name).trim();
    const PALETTE = [1, 2, 3, 4, 5, 6, 7, 8].map(i => v(`--chart-${i}`));
    const COLOR_ME = v("--chart-me") || "#ffffff";
    const COLOR_DIM = v("--chart-dim") || "rgba(231,231,231,.28)";

    const MAX_COMPARE = PALETTE.length; // 8

    // Estado: id -> índice de color (0..7) de cada comparado, y modo de
    // eje X. El usuario activo va aparte (blanco), no consume color.
    const colorIndex = new Map();
    const freeColors = PALETTE.map((_, i) => i);
    let xmode = "batch";
    let pinnedId = null; // línea "fijada" por clic/tap (tooltip persistente)

    // ----- Datos derivados por modo de eje X -------------------------

    function fmtDate(iso) {
        if (!iso) return "0";
        const [, m, d] = iso.split("-");
        return `${+d}/${+m}`;
    }

    // Columnas del eje X. Cada una apunta a un tick cuyo valor leer;
    // varias columnas pueden compartir tick (modo "partido": los
    // simultáneos comparten acumulado → tramo plano).
    function buildCols() {
        if (xmode === "match") {
            const cols = [{ label: "0", tick: 0 }];
            TICKS.forEach((t, ti) => {
                if (ti === 0) return;
                t.matches.forEach(lbl => cols.push({ label: lbl, tick: ti }));
            });
            return cols;
        }
        if (xmode === "day") {
            const lastOfDate = new Map();
            TICKS.forEach((t, ti) => { if (ti) lastOfDate.set(t.date, ti); });
            const cols = [{ label: "0", tick: 0 }];
            for (const [date, ti] of lastOfDate) {
                cols.push({ label: fmtDate(date), tick: ti });
            }
            return cols;
        }
        return TICKS.map((t, ti) => ({ label: fmtDate(t.date), tick: ti }));
    }

    const maxVal = Math.max(
        1, ...SERIES.map(s => s.points.length ? Math.max(...s.points) : 0)
    );

    // Adelgaza las etiquetas del eje X según el ancho disponible (~una
    // cada 110px): en celular ~6-8, en pantallas anchas (4K) muchas más,
    // así no se enciman pero tampoco quedan ralas al expandirse.
    function labelEvery(n, width) {
        const target = Math.max(6, Math.floor(width / 110));
        return Math.max(1, Math.ceil(n / target));
    }

    // ----- Render ----------------------------------------------------

    const tip = document.createElement("div");
    tip.className = "hist-tip";
    tip.hidden = true;
    root.appendChild(tip);

    function isSelected(s) {
        return s.me || colorIndex.has(s.id);
    }

    function strokeOf(s) {
        if (s.me) return COLOR_ME;
        const i = colorIndex.get(s.id);
        return i == null ? COLOR_DIM : PALETTE[i];
    }

    function render() {
        const w = root.clientWidth;
        const h = root.clientHeight;
        if (!w || !h) return;

        const cols = buildCols();
        const pad = { top: 12, right: 14, bottom: 26, left: 34 };
        const plotW = w - pad.left - pad.right;
        const plotH = h - pad.top - pad.bottom;
        const X = i => pad.left + (cols.length < 2
            ? plotW / 2 : (i / (cols.length - 1)) * plotW);
        const Y = val => pad.top + plotH * (1 - val / maxVal);

        const dFor = s => cols.map(
            (c, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(s.points[c.tick]).toFixed(1)}`
        ).join(" ");

        // Rejilla y etiquetas Y (puntos): 4 niveles.
        let grid = "";
        for (let k = 0; k <= 4; k++) {
            const val = (maxVal * k) / 4;
            const y = Y(val).toFixed(1);
            grid += `<line class="hist-grid" x1="${pad.left}" y1="${y}" x2="${w - pad.right}" y2="${y}"/>`;
            grid += `<text class="hist-ylabel" x="${pad.left - 6}" y="${y}">${Math.round(val)}</text>`;
        }

        // Etiquetas X adelgazadas.
        const step = labelEvery(cols.length, plotW);
        let xlabels = "";
        cols.forEach((c, i) => {
            if (i % step && i !== cols.length - 1) return;
            xlabels += `<text class="hist-xlabel" x="${X(i).toFixed(1)}" y="${h - pad.bottom + 16}">${c.label}</text>`;
        });

        // Líneas en 3 capas (fondo → comparados → yo).
        const dim = [], hi = [];
        SERIES.forEach(s => {
            if (s.me) return;
            const cls = isSelected(s) ? "hist-line is-hi" : "hist-line";
            const path = `<path class="${cls}" data-id="${s.id}" d="${dFor(s)}" style="stroke:${strokeOf(s)}"/>`;
            (isSelected(s) ? hi : dim).push(path);
        });
        const mePath = ME
            ? `<path class="hist-line is-me" data-id="${ME.id}" d="${dFor(ME)}" style="stroke:${COLOR_ME}"/>`
            : "";

        root.querySelector("svg")?.remove();
        root.insertAdjacentHTML("afterbegin",
            `<svg class="hist-svg" width="${w}" height="${h}">
                <defs><filter id="hist-glow" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="2.4" result="b"/>
                    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter></defs>
                ${grid}${xlabels}
                <g class="hist-dim">${dim.join("")}</g>
                <g class="hist-hi">${hi.join("")}</g>
                ${mePath}
            </svg>`);

        // Reaplica el resaltado de la línea fijada tras reconstruir el SVG.
        if (pinnedId != null) {
            root.querySelector(`path[data-id="${pinnedId}"]`)
                ?.classList.add("is-hover");
        }
    }

    // ----- Leyenda ---------------------------------------------------

    function renderLegend() {
        const box = document.getElementById("history-legend");
        const chips = [];
        if (ME) {
            chips.push(chip(ME, COLOR_ME, false));
        }
        // En el orden de los colores asignados.
        [...colorIndex.entries()]
            .sort((a, b) => a[1] - b[1])
            .forEach(([id]) => {
                const s = SERIES.find(x => x.id === id);
                if (s) chips.push(chip(s, PALETTE[colorIndex.get(id)], true));
            });
        box.innerHTML = chips.join("");
    }

    function chip(s, color, removable) {
        const rm = removable
            ? `<button class="hist-chip-x" data-remove="${s.id}" aria-label="Quitar">×</button>`
            : "";
        return `<span class="hist-chip"${s.me ? ' data-me="1"' : ""}>
            <span class="hist-chip-dot" style="background:${color}"></span>
            <span class="hist-chip-name">${s.name}</span>${rm}</span>`;
    }

    // Conteo "N seleccionados" en el control (los chips se ocultan por
    // CSS; el dato se expone como data-label y el ::after lo pinta).
    function updateCount() {
        const ctrl = document.querySelector(".history .ts-control");
        if (!ctrl) return;
        const n = ctrl.querySelectorAll(".item").length;
        ctrl.dataset.label = n === 0 ? ""
            : (n === 1 ? "1 seleccionado" : `${n} seleccionados`);
    }

    // ----- Selección (Tom Select) ------------------------------------

    function assignColor(id) {
        if (colorIndex.has(id) || !freeColors.length) return;
        colorIndex.set(id, freeColors.shift());
    }
    function releaseColor(id) {
        if (!colorIndex.has(id)) return;
        freeColors.push(colorIndex.get(id));
        freeColors.sort((a, b) => a - b);
        colorIndex.delete(id);
    }

    // Búsqueda sin acentos ni mayúsculas: campo normalizado aparte
    // (NFD descompone la tilde en diacrítico y se elimina).
    const norm = str => str.normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "").toLowerCase();

    const options = SERIES.filter(s => !s.me).map(s => ({
        value: String(s.id),
        name: s.name,
        search: norm(s.name),
        pos: s.virtual ? "IC" : (s.position || "—"),
    }));

    const select = new TomSelect("#history-users", {
        options,
        items: DATA.defaults.map(String).slice(0, MAX_COMPARE),
        maxItems: MAX_COMPARE,
        valueField: "value",
        labelField: "name",
        searchField: ["name", "search"],
        hideSelected: false,
        // checkbox_options: los seleccionados siguen visibles y marcados
        // en el desplegable y se alternan al clic (no desaparecen).
        plugins: ["remove_button", "checkbox_options"],
        render: {
            option: (d, esc) =>
                `<div class="hist-opt"><span class="hist-opt-pos">${esc(d.pos)}</span>${esc(d.name)}</div>`,
        },
        onItemAdd: id => { assignColor(+id); refresh(); },
        onItemRemove: id => { releaseColor(+id); refresh(); },
    });

    // Colores de los defaults antes del primer render.
    select.getValue().forEach(id => assignColor(+id));

    function refresh() {
        renderLegend();
        updateCount();
        render();
    }

    // ----- Interacción -----------------------------------------------

    // Quitar desde la leyenda (sincroniza Tom Select → dispara refresh).
    document.getElementById("history-legend").addEventListener("click", e => {
        const id = e.target.closest("[data-remove]")?.dataset.remove;
        if (id) select.removeItem(id);
    });

    // Toggle de modo de eje X.
    document.querySelector("[data-xmode-switch]").addEventListener("click", e => {
        const btn = e.target.closest("[data-xmode]");
        if (!btn) return;
        xmode = btn.dataset.xmode;
        document.querySelectorAll("[data-xmode]").forEach(
            b => b.classList.toggle("active", b === btn));
        render();
    });

    // Tooltip: al señalar (hover) o al hacer clic/tap aparece el nombre y
    // los puntos. El clic "fija" la línea (clave en móvil, sin hover);
    // otro clic en vacío la suelta.
    function clearHover() {
        root.querySelectorAll(".hist-line.is-hover")
            .forEach(p => p.classList.remove("is-hover"));
    }
    function seriesAt(target) {
        const path = target.closest && target.closest("path[data-id]");
        if (!path) return null;
        return [path, SERIES.find(s => s.id === +path.dataset.id)];
    }
    function highlight(path, s, e) {
        clearHover();
        path.classList.add("is-hover");
        const r = root.getBoundingClientRect();
        const last = s.points[s.points.length - 1];
        tip.textContent = `${s.name} · ${(+last).toLocaleString("es")}`;
        tip.style.left = `${e.clientX - r.left}px`;
        tip.style.top = `${e.clientY - r.top}px`;
        tip.hidden = false;
    }

    root.addEventListener("mousemove", e => {
        if (pinnedId != null) return;          // una línea fijada manda
        const hit = seriesAt(e.target);
        if (!hit) { clearHover(); tip.hidden = true; return; }
        highlight(hit[0], hit[1], e);
    });
    root.addEventListener("mouseleave", () => {
        if (pinnedId != null) return;
        clearHover();
        tip.hidden = true;
    });
    root.addEventListener("click", e => {
        const hit = seriesAt(e.target);
        if (!hit) { pinnedId = null; clearHover(); tip.hidden = true; return; }
        pinnedId = hit[1].id;
        highlight(hit[0], hit[1], e);
    });

    new ResizeObserver(() => render()).observe(root);
    refresh();
})();
