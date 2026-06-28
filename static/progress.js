/* Gráfica "Historia": líneas de avance del acumulado de cada
 * participante, tanda por tanda.
 *
 * Render en SVG a mano (sin librería de dibujo) dentro de un contenedor
 * medido con ResizeObserver: se redibuja al cambiar de tamaño, así la
 * gráfica es responsiva y siempre ocupa todo el ancho sin distorsionar
 * los trazos (a diferencia de un viewBox estirado).
 *
 * Tres capas de línea: al fondo el usuario activo en blanco con halo,
 * encima el telón en gris atenuado (todos los no seleccionados) y arriba
 * hasta 8 comparados con colores destacados (paleta --chart-1..8, asignada
 * por orden de selección vía Tom Select).
 *
 * El eje X no es uniforme: el ancho de cada bloque (tanda, día o partido)
 * es proporcional a su nº de partidos × el multiplicador de su ventana.
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
    // Color de ejes/ticks como atributo de presentación SVG (sobrevive a un
    // tailwind.css cacheado sin las clases nuevas; el CSS, cuando existe,
    // manda sobre el atributo).
    const COLOR_AXIS = v("--color-base-content") || "#888";

    const MAX_COMPARE = PALETTE.length; // 8

    // Estado: id -> índice de color (0..7) de cada comparado, y modo de
    // eje X. El usuario activo va aparte (blanco), no consume color.
    const colorIndex = new Map();
    const freeColors = PALETTE.map((_, i) => i);
    let xmode = "match";
    let view = "abs"; // "abs" eje fijo · "cono" eje elástico por columna
    let pinnedId = null; // línea "fijada" por clic/tap (tooltip persistente)

    // ----- Datos derivados por modo de eje X -------------------------

    function fmtDate(iso) {
        if (!iso) return "0";
        const [, m, d] = iso.split("-");
        return `${+d}/${+m}`;
    }

    // Ajuste de recta por mínimos cuadrados: dados xs/ys devuelve la
    // pendiente (m) y el intercepto (b) de y = m·x + b que minimiza el
    // error cuadrático. Es la base del marco recto (cono): la recta
    // inferior ajusta el contorno bajo de la nube y la superior el alto.
    function fitLine(xs, ys) {
        const n = xs.length;
        let sx = 0, sy = 0, sxy = 0, sxx = 0;
        for (let i = 0; i < n; i++) {
            sx += xs[i]; sy += ys[i];
            sxy += xs[i] * ys[i]; sxx += xs[i] * xs[i];
        }
        const den = n * sxx - sx * sx;
        const m = den ? (n * sxy - sx * sy) / den : 0;
        return { m, b: (sy - m * sx) / n };
    }

    // "Paso redondo" más cercano a un valor crudo (1, 2, 5 × 10ⁿ): separa
    // las líneas iso-valor del cono con números legibles (10, 20, 50…).
    function niceStep(rough) {
        if (!(rough > 0)) return 1;
        const pow = Math.pow(10, Math.floor(Math.log10(rough)));
        const n = rough / pow;
        return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * pow;
    }

    // Columnas del eje X. Cada una apunta a un tick cuyo valor leer y
    // lleva un ``weight``: el ancho relativo del tramo que entra en ella,
    // = nº de partidos × multiplicador de su ventana. El origen pesa 0
    // (queda pegado al borde izquierdo). Varias columnas pueden compartir
    // tick (modo "partido": los simultáneos comparten acumulado → tramo
    // plano, ya ponderado por el multiplicador).
    function buildCols() {
        if (xmode === "match") {
            const cols = [{ label: "0", tick: 0, weight: 0 }];
            TICKS.forEach((t, ti) => {
                if (ti === 0) return;
                t.matches.forEach(mt =>
                    cols.push({ match: mt, tick: ti, weight: t.multiplier }));
            });
            return cols;
        }
        if (xmode === "day") {
            // Por fecha: último tick (para leer el acumulado del día),
            // total de partidos del día y su multiplicador (uno solo por
            // día, garantizado por dominio).
            const byDate = new Map();
            TICKS.forEach((t, ti) => {
                if (!ti) return;
                const d = byDate.get(t.date)
                    || { tick: ti, matches: 0, mult: t.multiplier };
                d.tick = ti;
                d.matches += t.matches.length;
                byDate.set(t.date, d);
            });
            const cols = [{ label: "0", tick: 0, weight: 0 }];
            for (const [date, d] of byDate) {
                cols.push({
                    label: fmtDate(date), tick: d.tick,
                    weight: d.matches * d.mult,
                });
            }
            return cols;
        }
        return TICKS.map((t, ti) => ({
            label: fmtDate(t.date), tick: ti,
            weight: t.matches.length * t.multiplier,
        }));
    }

    const maxVal = Math.max(
        1, ...SERIES.map(s => s.points.length ? Math.max(...s.points) : 0)
    );

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

    // Etiqueta de una columna del eje X. En modo "partido", dos banderas
    // apiladas (local arriba, visitante abajo) de máx. 20×15 sin distorsión
    // (``meet`` encaja la bandera dentro de la caja). Si falta bandera, o es
    // fecha/origen, texto centrado.
    const FLAG_W = 20, FLAG_H = 15;
    function xLabel(c, x, yTop) {
        const m = c.match;
        if (m && m.home_flag && m.away_flag) {
            const fx = (x - FLAG_W / 2).toFixed(1);
            const img = (href, y, code) =>
                `<image href="${href}" x="${fx}" y="${y}" width="${FLAG_W}" height="${FLAG_H}" preserveAspectRatio="xMidYMid meet"><title>${code}</title></image>`;
            return img(m.home_flag, yTop + 3, m.home)
                + img(m.away_flag, yTop + 20, m.away);
        }
        const txt = m ? `${m.home} ${m.away}` : c.label;
        return `<text class="hist-xlabel" x="${x.toFixed(1)}" y="${yTop + 16}">${txt}</text>`;
    }

    function render() {
        const w = root.clientWidth;
        const h = root.clientHeight;
        if (!w || !h) return;

        const cols = buildCols();
        // En modo "partido" el canalón inferior crece para las dos banderas
        // apiladas (local sobre visitante); en los demás basta una fila.
        const pad = { top: 12, right: 14,
            bottom: xmode === "match" ? 42 : 26, left: 34 };
        const plotW = w - pad.left - pad.right;
        const plotH = h - pad.top - pad.bottom;
        // Posiciones X por suma acumulada de pesos: el ancho de cada
        // tramo es proporcional a su ``weight``. El origen (peso 0) cae en
        // ``pad.left`` y la última columna en el borde derecho del área.
        const totalW = cols.reduce((a, c) => a + c.weight, 0);
        let acc = 0;
        const xPos = cols.map(c => {
            acc += c.weight;
            return pad.left + (totalW ? acc / totalW : 0) * plotW;
        });
        const X = i => cols.length < 2 ? pad.left + plotW / 2 : xPos[i];

        // Eje Y: regla fija ("abs", 0 abajo y maxVal arriba, igual en toda
        // la gráfica) o regla elástica por columna ("cono"). En "cono" la
        // escala se recalcula columna a columna para seguir a la nube de
        // líneas visibles; por eso Y recibe el índice de columna.
        let Y, bands = null;
        if (view === "cono") {
            // Posición horizontal normalizada [0,1] de cada columna (no
            // depende del ancho; sobrevive al resize).
            const xf = cols.map((c, i) => plotW ? (X(i) - pad.left) / plotW : 0);
            // Contorno de TODA la nube por columna: el más bajo y el más
            // alto de todos los participantes en cada momento.
            const loPt = cols.map(c =>
                Math.min(...SERIES.map(s => s.points[c.tick])));
            const hiPt = cols.map(c =>
                Math.max(...SERIES.map(s => s.points[c.tick])));
            // Marco del cono: dos rectas continuas (mínimos cuadrados) entre
            // las que flota la nube. No se fuerza el ajuste columna a
            // columna, por eso la escala cambia suave y un anotador parejo
            // sale como curva, no como zigzag. Se ignora la columna de
            // salida (todos en 0) para que el ajuste no quede pellizcado en
            // 0 a la izquierda y refleje la dispersión real.
            const fit = cols.map((c, i) => i).filter(i => cols.length <= 2 || i);
            const L = fitLine(fit.map(i => xf[i]), fit.map(i => loPt[i]));
            const U = fitLine(fit.map(i => xf[i]), fit.map(i => hiPt[i]));
            // Las rectas no arrancan en 0: se desplazan hacia afuera lo
            // justo para CONTENER la nube (la inferior baja hasta el punto
            // más hundido, la superior sube hasta el más saliente). Ese
            // "varios puntos" se calcula solo, como la desviación máxima.
            let dDown = 0, dUp = 0;
            fit.forEach(i => {
                dDown = Math.max(dDown, (L.m * xf[i] + L.b) - loPt[i]);
                dUp = Math.max(dUp, hiPt[i] - (U.m * xf[i] + U.b));
            });
            L.b -= dDown;
            U.b += dUp;
            bands = cols.map((c, i) => {
                const lo = L.m * xf[i] + L.b, hi = U.m * xf[i] + U.b;
                const cush = 0.02 * Math.max(hi - lo, 1); // colchón pequeño
                const dlo = lo - cush;
                const dataH = Math.max((hi + cush) - dlo, 0.5);
                // Alto de la banda en píxeles: 45% (izq) → 100% (der),
                // centrada. La nube se ve angosta a la izquierda aunque la
                // escala (px/punto) sea mayor ahí.
                const pxH = (0.45 + 0.55 * xf[i]) * plotH;
                const botPx = pad.top + plotH - (plotH - pxH) / 2;
                return { dlo, dataH, botPx, pxH };
            });
            Y = (val, i) => bands[i].botPx
                - ((val - bands[i].dlo) / bands[i].dataH) * bands[i].pxH;
        } else {
            Y = val => pad.top + plotH * (1 - val / maxVal);
        }

        const dFor = s => cols.map(
            (c, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(s.points[c.tick], i).toFixed(1)}`
        ).join(" ");

        // Rejilla y etiquetas Y (puntos): 4 niveles. El nivel 0 es el eje
        // (sólido), el resto rejilla punteada, para que no se confundan con
        // las líneas grises sin color.
        let grid = "";
        if (view === "abs") {
            for (let k = 0; k <= 4; k++) {
                const val = (maxVal * k) / 4;
                const y = Y(val).toFixed(1);
                const axis = k === 0
                    ? ` style="stroke:${COLOR_AXIS};stroke-opacity:.32"` : "";
                const cls = k === 0 ? "hist-axis" : "hist-grid";
                grid += `<line class="${cls}"${axis} x1="${pad.left}" y1="${y}" x2="${w - pad.right}" y2="${y}"/>`;
                grid += `<text class="hist-ylabel" x="${pad.left - 6}" y="${y}">${Math.round(val)}</text>`;
            }
        }

        // Etiquetas X adelgazadas por posición (no por índice): con anchos
        // desiguales el espaciado deja de ser uniforme, así que sólo se
        // dibuja una etiqueta si dista ≥44px de la última (primera y última
        // siempre). Cada etiqueta visible lleva su línea vertical de rejilla
        // (mismo estilo punteado y tenue que las horizontales).
        const yTickTop = h - pad.bottom;
        let xlabels = "", xgrid = "";
        let lastLabelX = -Infinity;
        cols.forEach((c, i) => {
            const x = X(i);
            const isEnd = i === 0 || i === cols.length - 1;
            if (!isEnd && x - lastLabelX < 44) return;
            lastLabelX = x;
            const xr = x.toFixed(1);
            xlabels += xLabel(c, x, yTickTop);
            xgrid += `<line class="hist-grid" x1="${xr}" x2="${xr}" y1="${pad.top}" y2="${yTickTop}"/>`;
        });

        // Adornos del modo Cono: el marco (las dos rectas envolventes,
        // rectas en pantalla → basta unir extremos) y la línea diagonal del
        // 0 (imagen del valor 0: curva suave que se hunde fuera del área,
        // recortada). Van al fondo, tenues, detrás de las líneas.
        let cono = "";
        if (view === "cono" && bands) {
            const iN = cols.length - 1;
            const top = b => b.botPx - b.pxH, bot = b => b.botPx;
            // Curva iso-valor: une Y(v, i) en cada columna (una "horizontal"
            // del eje fijo se vuelve curva con el eje elástico). Recortada.
            const isoPath = v => cols.map((c, i) =>
                `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(v, i).toFixed(1)}`).join(" ");
            // Vértice visible más alto / más bajo de una iso: los extremos
            // por donde la curva entra (cerca del borde superior) y sale
            // (cerca del inferior). Ahí van sus números, arriba y abajo.
            const isoEnd = (v, lowest) => {
                let best = null;
                cols.forEach((c, i) => {
                    const y = Y(v, i);
                    const vis = y >= top(bands[i]) - 0.5 && y <= bot(bands[i]) + 0.5;
                    if (vis && (!best || (lowest ? y > best.y : y < best.y)))
                        best = { i, y };
                });
                return best;
            };
            // Mantiene la etiqueta dentro del área (sin invadir el canalón de
            // banderas abajo ni salirse por arriba).
            const clampY = y =>
                Math.max(pad.top + 8, Math.min(y, pad.top + plotH - 2));
            const label = (x, y, txt) =>
                `<text font-size="10" text-anchor="start" fill="${COLOR_AXIS}" fill-opacity=".7" x="${x.toFixed(1)}" y="${clampY(y).toFixed(1)}">${txt}</text>`;
            // Etiquetas de una iso: abajo (siempre) y arriba (sólo las > 0; la
            // del 0 va únicamente abajo, "junto a las demás"). Pegadas a la
            // derecha de la curva, no centradas en la columna.
            const isoLabels = (v, txt, withTop) => {
                let s = "";
                const b = isoEnd(v, true);
                if (b) s += label(X(b.i) + 2, b.y + 13, txt);
                const t = withTop && isoEnd(v, false);
                if (t) s += label(X(t.i) + 2, t.y - 5, txt);
                return s;
            };

            // 1) "Anti-faro": oscurece el área del cono (relleno NEGRO con
            //    algo de opacidad), en vez de iluminarla.
            const poly = `M${X(0).toFixed(1)} ${top(bands[0]).toFixed(1)}`
                + ` L${X(iN).toFixed(1)} ${top(bands[iN]).toFixed(1)}`
                + ` L${X(iN).toFixed(1)} ${bot(bands[iN]).toFixed(1)}`
                + ` L${X(0).toFixed(1)} ${bot(bands[0]).toFixed(1)} Z`;
            cono += `<path fill="#000" fill-opacity=".22" stroke="none" d="${poly}"/>`;

            // 2) Iso-líneas de puntos (curvas paralelas a la del 0), punteadas
            //    como la rejilla original pero visibles; número arriba y abajo
            //    del cono, a la derecha de cada curva.
            const step = niceStep(maxVal / 7);
            for (let v = step; v < maxVal; v += step) {
                cono += `<path fill="none" stroke="${COLOR_AXIS}" stroke-opacity=".18" stroke-dasharray="3 4" d="${isoPath(v)}" clip-path="url(#hist-clip)"/>`;
                cono += isoLabels(v, Math.round(v), true);
            }

            // 3) Marco: dos rectas envolventes (límites real inferior/superior).
            const edge = sel =>
                `<line class="hist-envelope" fill="none" stroke="${COLOR_AXIS}" stroke-opacity=".2" x1="${X(0).toFixed(1)}" y1="${sel(bands[0]).toFixed(1)}" x2="${X(iN).toFixed(1)}" y2="${sel(bands[iN]).toFixed(1)}"/>`;
            cono += edge(top) + edge(bot);

            // 4) Línea del 0 (punteada); su "0" va sólo abajo, junto a las
            //    demás etiquetas inferiores.
            cono += `<path class="hist-zero" fill="none" stroke="${COLOR_AXIS}" stroke-opacity=".28" stroke-dasharray="2 5" d="${isoPath(0)}" clip-path="url(#hist-clip)"/>`;
            cono += isoLabels(0, "0", false);
        }

        // Líneas en 3 capas; la propia va al fondo (detrás de todas) con
        // su halo, luego el telón gris y encima los comparados.
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
                </filter>
                <clipPath id="hist-clip"><rect x="${pad.left}" y="${pad.top}" width="${plotW}" height="${plotH}"/></clipPath></defs>
                ${grid}${cono}${xgrid}${xlabels}
                <g clip-path="url(#hist-clip)">
                    ${mePath}
                    <g class="hist-dim">${dim.join("")}</g>
                    <g class="hist-hi">${hi.join("")}</g>
                </g>
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

    // Toggle de vista: eje fijo (Absoluta) vs eje elástico (Cono).
    document.querySelector("[data-view-switch]").addEventListener("click", e => {
        const btn = e.target.closest("[data-view]");
        if (!btn) return;
        view = btn.dataset.view;
        document.querySelectorAll("[data-view]").forEach(
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
