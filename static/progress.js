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
 * El eje X no es uniforme: una columna por partido, con ancho proporcional
 * a su multiplicador de ventana; los partidos simultáneos comparten tanda
 * (acumulado) y dejan un tramo plano. Líneas verticales tenues separan las
 * fases (Grupos | 16avos | …).
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

    // Estado: id -> índice de color (0..7) de cada comparado. El usuario
    // activo va aparte (blanco), no consume color.
    const colorIndex = new Map();
    const freeColors = PALETTE.map((_, i) => i);
    let view = "cono"; // "cono" eje elástico por columna · "abs" eje fijo
    let zoom = "1x"; // ancho del lienzo: "1x" cabe · "2x" doble · "full" todo
    let pinnedId = null; // línea "fijada" por clic/tap (tooltip persistente)

    // Zoom horizontal: en "full" la columna más angosta recibe
    // PX_PER_MATCH px (suficiente para una bandera de 20px con aire), así
    // caben TODAS. Se reparte por peso (multiplicador de ventana), no por
    // número de partidos: con multiplicadores las columnas no son iguales.
    // LABEL_GAP (umbral para pintar etiqueta) va 2px por debajo como margen
    // de seguridad, para que ninguna se descarte por redondeo.
    const PX_PER_MATCH = 28;
    const LABEL_GAP = PX_PER_MATCH - 2;
    const zoomSwitch = document.querySelector("[data-zoom-switch]");

    // ----- Datos derivados del eje X ---------------------------------

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

    // Columnas del eje X: una por partido. Cada una apunta a su tick (de
    // donde leer el acumulado) y lleva un ``weight`` = multiplicador de su
    // ventana (ancho relativo del tramo). El origen pesa 0 (pegado al borde
    // izquierdo). Los partidos simultáneos comparten tick → mismo acumulado
    // → tramo plano, ya ponderado por el multiplicador.
    function buildCols() {
        const cols = [{ label: "0", vtick: 0, weight: 0, phase: "Salida" }];
        TICKS.forEach((t, ti) => {
            if (ti === 0) return;
            const last = t.matches.length - 1;
            t.matches.forEach((mt, mi) => cols.push({
                match: mt,
                // Los partidos simultáneos comparten acumulado; para que el
                // salto se alinee con la ÚLTIMA bandera de la tanda (y no con
                // la primera), las columnas previas leen el valor de la tanda
                // anterior (``ti - 1``) y sólo la última sube al de ésta.
                vtick: mi === last ? ti : ti - 1,
                weight: t.multiplier,
                phase: t.phase,
            }));
        });
        return cols;
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
        const baseW = root.clientWidth;
        const h = root.clientHeight;
        if (!baseW || !h) return;

        // Líneas más finas cuando hay poco alto (inmersivo/móvil): el CSS
        // ``.is-short`` adelgaza los trazos para que no se empasten.
        root.classList.toggle("is-short", h < 580);

        const cols = buildCols();
        // El canalón inferior aloja las dos banderas apiladas (local sobre
        // visitante). Los márgenes laterales: en "abs" dejan sitio a las
        // etiquetas numéricas del eje Y (izq) y un respiro a la derecha; en
        // "cono" no hay etiquetas de borde, así que basta el medio ancho de
        // bandera para que la primera/última no se recorten.
        const pad = view === "cono"
            ? { top: 12, right: 12, bottom: 42, left: 12 }
            : { top: 12, right: 14, bottom: 42, left: 34 };

        // Ancho "full": el área de trazado debe ser tan ancha que la columna
        // de MENOR peso reciba PX_PER_MATCH px (cada columna ocupa
        // plotW·weight/totalW). Despejando minW·plotW/totalW = PX_PER_MATCH.
        // Se le suman los márgenes para obtener el ancho del lienzo. El switch
        // solo aparece si ese ancho supera al de la ventana (a 1x no cabe).
        const totalW = cols.reduce((a, c) => a + c.weight, 0);
        const weights = cols.filter(c => c.weight > 0).map(c => c.weight);
        const minW = weights.length ? Math.min(...weights) : 1;
        const fullW = totalW
            ? PX_PER_MATCH * totalW / minW + pad.left + pad.right
            : baseW;
        const showZoom = fullW > baseW;
        zoomSwitch.style.display = showZoom ? "" : "none";
        let w = baseW;
        if (showZoom) {
            if (zoom === "2x") w = baseW * 2;
            else if (zoom === "full") w = Math.max(baseW, fullW);
        }

        const plotW = w - pad.left - pad.right;
        const plotH = h - pad.top - pad.bottom;
        // Posiciones X por suma acumulada de pesos: el ancho de cada
        // tramo es proporcional a su ``weight``. El origen (peso 0) cae en
        // ``pad.left`` y la última columna en el borde derecho del área.
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
                Math.min(...SERIES.map(s => s.points[c.vtick])));
            const hiPt = cols.map(c =>
                Math.max(...SERIES.map(s => s.points[c.vtick])));
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
            (c, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(s.points[c.vtick], i).toFixed(1)}`
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
        // dibuja una etiqueta si dista ≥``LABEL_GAP`` de la última (primera
        // y última siempre). El umbral ronda el ancho de bandera + aire, así
        // que cuando hay holgura caben más banderas (y sus líneas
        // verticales); las zonas densas siguen colapsando. Cada etiqueta
        // visible lleva su línea vertical de rejilla (punteada, como las
        // horizontales). El umbral ``LABEL_GAP`` está definido arriba, ligado
        // a ``PX_PER_MATCH`` para que en "full" se muestren todas.
        const yTickTop = h - pad.bottom;
        let xlabels = "", xgrid = "";
        let lastLabelX = -Infinity;
        cols.forEach((c, i) => {
            const x = X(i);
            const isEnd = i === 0 || i === cols.length - 1;
            if (!isEnd && x - lastLabelX < LABEL_GAP) return;
            lastLabelX = x;
            const xr = x.toFixed(1);
            xlabels += xLabel(c, x, yTickTop);
            xgrid += `<line class="hist-grid" x1="${xr}" x2="${xr}" y1="${pad.top}" y2="${yTickTop}"/>`;
        });

        // Divisores de fase: línea vertical tenue en la frontera donde cambia
        // la fase (las 3 jornadas de grupos van colapsadas en "Grupos"), en
        // el punto medio entre columnas. Se arranca en i=2 para ignorar el
        // origen sintético (Salida→Grupos no separa fases).
        let phaseDiv = "";
        for (let i = 2; i < cols.length; i++) {
            if (cols[i].phase === cols[i - 1].phase) continue;
            const xm = ((X(i) + X(i - 1)) / 2).toFixed(1);
            phaseDiv += `<line class="hist-phase" stroke="${COLOR_AXIS}" stroke-opacity=".22" x1="${xm}" x2="${xm}" y1="${pad.top}" y2="${yTickTop}"/>`;
        }

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
            // Punto exacto donde la iso cruza una recta envolvente:
            // interpolación lineal entre las dos columnas vecinas donde
            // ``Y(v,·) - borde`` cambia de signo. Devuelve {x, y} justo sobre
            // la recta (no la columna "casi dentro"), para que todas las
            // etiquetas queden pegadas a su cruce con un desplazamiento
            // uniforme y no dispares. ``null`` si la iso nunca toca ese borde
            // (p. ej. un valor alto que jamás baja hasta la recta inferior):
            // esa etiqueta se omite en vez de pegarse al borde derecho. Se
            // ignora el origen (desde i=1).
            const crossEdge = (v, edge) => {
                let p0 = Y(v, 1) - edge(bands[1]);
                for (let i = 2; i < cols.length; i++) {
                    const p1 = Y(v, i) - edge(bands[i]);
                    if ((p0 < 0) !== (p1 < 0)) {
                        const t = p0 / (p0 - p1); // fracción del cruce
                        return {
                            x: X(i - 1) + t * (X(i) - X(i - 1)),
                            y: Y(v, i - 1) + t * (Y(v, i) - Y(v, i - 1)),
                        };
                    }
                    p0 = p1;
                }
                return null;
            };
            // Mantiene la etiqueta dentro del área (sin invadir el canalón de
            // banderas abajo ni salirse por arriba).
            const clampY = y =>
                Math.max(pad.top + 8, Math.min(y, pad.top + plotH - 2));
            const label = (x, y, txt, anchor) =>
                `<text font-size="10" text-anchor="${anchor}" fill="${COLOR_AXIS}" fill-opacity=".7" x="${x.toFixed(1)}" y="${clampY(y).toFixed(1)}">${txt}</text>`;
            // Etiquetas de una iso, pegadas a su cruce con desplazamiento
            // constante: arriba-derecha del cruce con la recta superior,
            // abajo-izquierda del cruce con la inferior; cada una sólo si ese
            // cruce existe. El 0 lleva sólo la de abajo.
            const isoLabels = (v, txt, withTop) => {
                let s = "";
                const b = crossEdge(v, bot);
                if (b) s += label(b.x - 3, b.y + 11, txt, "end");
                if (withTop) {
                    const t = crossEdge(v, top);
                    if (t) s += label(t.x + 3, t.y - 4, txt, "start");
                }
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
            cono += `<path class="hist-zero" fill="none" stroke="${COLOR_AXIS}" stroke-opacity=".55" stroke-width="1.2" stroke-dasharray="6 4" d="${isoPath(0)}" clip-path="url(#hist-clip)"/>`;
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
                ${grid}${cono}${xgrid}${phaseDiv}${xlabels}
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

    // ----- Selección (Tom Select) ------------------------------------

    // Persistencia de la selección en UserQuiniela: la última comparación
    // se recuerda por usuario y quiniela. Se autoguarda con debounce al
    // agregar/quitar (espejo del autoguardado por partido de submit.js).
    function getCookie(name) {
        const m = document.cookie.match(
            new RegExp("(?:^|; )" + name + "=([^;]*)"));
        return m ? decodeURIComponent(m[1]) : null;
    }
    const csrftoken = getCookie("csrftoken");
    const saveUrl = `/${window.QUINIELA_SLUG || ""}/historia/seleccion/`;
    let ready = false; // evita persistir los items iniciales (defaults)
    let saveTimer = null;
    function persistSelection() {
        if (!ready) return;
        clearTimeout(saveTimer);
        saveTimer = setTimeout(() => {
            fetch(saveUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrftoken,
                },
                body: JSON.stringify({ ids: select.getValue().map(Number) }),
            }).catch(() => {}); // best-effort: una preferencia de UI
        }, 500);
    }

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
        onItemAdd: id => { assignColor(+id); refresh(); persistSelection(); },
        onItemRemove: id => {
            releaseColor(+id); refresh(); persistSelection();
        },
    });

    // Colores de los defaults antes del primer render.
    select.getValue().forEach(id => assignColor(+id));
    ready = true; // a partir de aquí, los cambios del usuario sí se guardan

    function refresh() {
        renderLegend();
        render();
    }

    // ----- Interacción -----------------------------------------------

    // Quitar desde la leyenda (sincroniza Tom Select → dispara refresh).
    document.getElementById("history-legend").addEventListener("click", e => {
        const id = e.target.closest("[data-remove]")?.dataset.remove;
        if (id) select.removeItem(id);
    });

    // Toggle de vista: eje fijo (Simple) vs eje elástico (Cono).
    document.querySelector("[data-view-switch]").addEventListener("click", e => {
        const btn = e.target.closest("[data-view]");
        if (!btn) return;
        view = btn.dataset.view;
        document.querySelectorAll("[data-view]").forEach(
            b => b.classList.toggle("active", b === btn));
        render();
    });

    // Toggle de zoom horizontal: 1x · 2x · full. Al cambiar se vuelve al
    // inicio (sin desplazamiento residual).
    zoomSwitch.addEventListener("click", e => {
        const btn = e.target.closest("[data-zoom]");
        if (!btn) return;
        zoom = btn.dataset.zoom;
        zoomSwitch.querySelectorAll("[data-zoom]").forEach(
            b => b.classList.toggle("active", b === btn));
        root.scrollLeft = 0;
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
        // El tip vive dentro del contenedor scrolleable; se suma scrollLeft
        // para que no se desfase cuando la gráfica está desplazada (2x/full).
        tip.style.left = `${e.clientX - r.left + root.scrollLeft}px`;
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

    // ----- Modo inmersivo (móvil): horizontal a pantalla completa ----

    // Híbrido: intenta Fullscreen API + bloqueo nativo de orientación; si el
    // dispositivo no lo soporta (p. ej. iOS Safari) cae a una rotación por
    // CSS y avisa al usuario que gire el teléfono. La rotación se aplica de
    // forma reactiva (clase ``is-rotated`` según la orientación real), así
    // que la vista siempre se ve horizontal sin "doble giro".
    const body = document.body;
    const portraitMQ = window.matchMedia("(orientation: portrait)");
    let nativeLock = false; // true si el lock nativo de orientación funcionó

    function immersive() {
        return body.classList.contains("history-immersive");
    }
    // Con lock nativo el SO ya pone horizontal; sólo rotamos por CSS en el
    // respaldo y únicamente mientras el aparato siga en vertical.
    function applyRotation() {
        if (!immersive()) return;
        body.classList.toggle("is-rotated", !nativeLock && portraitMQ.matches);
        render();
    }

    let hintTimer = null;
    function showRotateHint() {
        const plot = document.querySelector(".history-plot");
        let hint = document.getElementById("history-rotate-hint");
        if (!hint) {
            hint = document.createElement("div");
            hint.id = "history-rotate-hint";
            hint.className = "history-hint";
            hint.textContent =
                "Gira tu teléfono a horizontal para aprovechar la pantalla.";
            plot.appendChild(hint);
        }
        hint.classList.add("show");
        clearTimeout(hintTimer);
        hintTimer = setTimeout(() => hint.classList.remove("show"), 4500);
    }

    async function enterImmersive() {
        body.classList.add("history-immersive");
        nativeLock = false;
        try {
            if (document.documentElement.requestFullscreen) {
                await document.documentElement.requestFullscreen();
            }
            if (screen.orientation && screen.orientation.lock) {
                await screen.orientation.lock("landscape");
                nativeLock = true;
            }
        } catch (_) { /* no soportado: seguimos con la rotación CSS */ }
        applyRotation();
        if (!nativeLock && portraitMQ.matches) showRotateHint();
    }

    function exitImmersive() {
        body.classList.remove("history-immersive", "is-rotated");
        nativeLock = false;
        try {
            if (screen.orientation && screen.orientation.unlock) {
                screen.orientation.unlock();
            }
            if (document.fullscreenElement) document.exitFullscreen();
        } catch (_) { /* nada que deshacer */ }
        render();
    }

    document.querySelector("[data-immersive-open]")
        ?.addEventListener("click", enterImmersive);
    document.querySelector("[data-immersive-close]")
        ?.addEventListener("click", exitImmersive);
    // Salir del fullscreen nativo (gesto/tecla del sistema) cierra también
    // el overlay. En el modo CSS no hay fullscreenElement, así que este
    // evento no se dispara y no interfiere.
    document.addEventListener("fullscreenchange", () => {
        if (!document.fullscreenElement && immersive()) exitImmersive();
    });
    // Reajusta la rotación al girar físicamente el aparato.
    portraitMQ.addEventListener("change", applyRotation);

    new ResizeObserver(() => render()).observe(root);
    refresh();
})();
