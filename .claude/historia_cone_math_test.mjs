/* Prueba aislada del motor del cono (gráfica Historia, modo "cono").
 * No depende de Django ni del DOM: replica fitLine + exclusión de trolls
 * (mediana+MAD) + coneBands (alto ∝ dispersión^α) con datos sintéticos y
 * comprueba las invariantes. Ejecutar: node .claude/...mjs */

const pad = { top: 12, left: 34 };
const plotW = 1000, plotH = 400;
const CONE_ALPHA = 0.5;

// ---- fitLine (copia exacta de progress.js) -------------------------------
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

// ---- Motor del cono (réplica de progress.js) ------------------------------
function median(arr) {
    const a = [...arr].sort((x, y) => x - y);
    const m = a.length >> 1;
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
}

// Devuelve {bands, Y, excluded} para una lista de series (points[]).
function coneEngine(players, xf) {
    const N = xf.length;
    const totals = players.map(p => p[N - 1]);
    const medT = median(totals);
    const mad = median(totals.map(t => Math.abs(t - medT)));
    const excluded = new Set(players.length < 4 ? [] : players
        .map((p, j) => ({ j, dev: medT - totals[j] }))
        .filter(o => o.dev > 3 * mad && o.dev > 0.25 * medT)
        .sort((a, b) => b.dev - a.dev)
        .slice(0, 2).map(o => o.j));
    const cloud = players.filter((p, j) => !excluded.has(j));
    const loPt = xf.map((_, i) => Math.min(...cloud.map(p => p[i])));
    const hiPt = xf.map((_, i) => Math.max(...cloud.map(p => p[i])));
    const fit = xf.map((_, i) => i).filter(i => N <= 2 || i); // sin salida
    const L = fitLine(fit.map(i => xf[i]), fit.map(i => loPt[i]));
    const U = fitLine(fit.map(i => xf[i]), fit.map(i => hiPt[i]));
    let dDown = 0, dUp = 0;
    fit.forEach(i => {
        dDown = Math.max(dDown, (L.m * xf[i] + L.b) - loPt[i]);
        dUp = Math.max(dUp, hiPt[i] - (U.m * xf[i] + U.b));
    });
    L.b -= dDown; U.b += dUp;
    const bands = xf.map(t => {
        const lo = L.m * t + L.b, hi = U.m * t + U.b;
        const cush = 0.02 * Math.max(hi - lo, 1);
        const dlo = lo - cush;
        const dataH = Math.max((hi + cush) - dlo, 0.5);
        return { dlo, dataH };
    });
    const dataHMax = Math.max(...bands.map(b => b.dataH));
    bands.forEach(b => {
        b.pxH = Math.pow(b.dataH / dataHMax, CONE_ALPHA) * plotH;
        b.botPx = pad.top + plotH - (plotH - b.pxH) / 2;
    });
    const Y = (val, i) => bands[i].botPx
        - ((val - bands[i].dlo) / bands[i].dataH) * bands[i].pxH;
    return { bands, Y, excluded };
}

// ---- Series sintéticas: dispersión creciente + un caído legítimo + troll
const N = 8;                       // columnas (col 0 = salida, todos en 0)
const X = i => pad.left + (i / (N - 1)) * plotW;
const xf = Array.from({ length: N }, (_, i) => (X(i) - pad.left) / plotW);

const players = [0, 1, 2, 3, 4].map(j => Array.from({ length: N },
    (_, i) => i === 0 ? 0 : 3 * i + (j - 2) * (0.4 * i)));
// "Russ": sube y luego se hunde fuerte, pero remonta — caído legítimo.
const russ = [0, 5, 4, 2, 1, 6, 10, 14];
players.push(russ);
// "Troll": pierde a propósito con todo, se queda casi en cero.
const troll = [0, 0, 1, 1, 1, 2, 2, 2];
players.push(troll);

const { bands, Y, excluded } = coneEngine(players, xf);
const trollIdx = players.length - 1, russIdx = players.length - 2;

// ---- Invariantes ---------------------------------------------------------
let ok = true;
const assert = (c, m) => { if (!c) { ok = false; console.log("✗", m); } };
const near = (a, b, e = 0.01) => Math.abs(a - b) < e;
const coneTop = i => bands[i].botPx - bands[i].pxH;   // y del borde superior

// 1) fitLine recupera una recta perfecta.
const f = fitLine([0, 1, 2, 3], [1, 3, 5, 7]);
assert(near(f.m, 2) && near(f.b, 1), "fitLine recupera y=2x+1");

// 2) Exclusión: el troll sale del cálculo; Russ (caído legítimo) no.
assert(excluded.has(trollIdx), "el troll queda excluido del cálculo");
assert(!excluded.has(russIdx), "Russ (caído legítimo) NO se excluye");
assert(excluded.size <= 2, "nunca se excluye a más de 2");

// 2b) Grupo parejo: no se excluye a nadie (ni con MAD ~0).
const tight = [0, 1, 2, 3].map(j => xf.map((_, i) => 3 * i + (j ? 0 : -1)));
assert(coneEngine(tight, xf).excluded.size === 0,
    "grupo parejo: cero excluidos");

// 3) Cono: la columna más dispersa ocupa el 100%; el alto sigue
//    dispersión^α; banda centrada.
const dataHMax = Math.max(...bands.map(b => b.dataH));
bands.forEach((b, i) => {
    assert(near(b.pxH, Math.pow(b.dataH / dataHMax, CONE_ALPHA) * plotH),
        `col ${i}: alto = dispersión^α`);
    assert(near(b.botPx - b.pxH / 2, pad.top + plotH / 2), `col ${i}: centrada`);
});
assert(near(Math.max(...bands.map(b => b.pxH)), plotH),
    "la columna más dispersa llega al 100% del alto");

// 4) Escala (px/punto) DECRECE de izquierda a derecha (α<1 y dispersión
//    creciente ⇒ más zoom donde las diferencias son chicas).
for (let i = 1; i < N; i++) {
    const s0 = bands[i - 1].pxH / bands[i - 1].dataH;
    const s1 = bands[i].pxH / bands[i].dataH;
    assert(s1 < s0, `col ${i}: escala decrece (${s0.toFixed(1)}→${s1.toFixed(1)} px/pt)`);
}

// 5) CONTENCIÓN de los incluidos: toda línea no excluida cae DENTRO del
//    cono en cada columna, incluido el hundimiento de Russ.
players.forEach((p, j) => {
    if (excluded.has(j)) return;
    p.forEach((v, i) => {
        const y = Y(v, i);
        assert(y <= bands[i].botPx + 0.01 && y >= coneTop(i) - 0.01,
            `jugador ${j} col ${i}: dentro del cono (y=${y.toFixed(0)})`);
    });
});

// 6) El troll queda FUERA (bajo el borde inferior) donde va muy abajo: su
//    hueco ya no infla el cono de los demás.
const yT = Y(troll[N - 1], N - 1);
assert(yT > bands[N - 1].botPx, "el troll se dibuja bajo el cono al final");

// 7) Un anotador PAREJO sale CURVO, no recto.
const steady = xf.map((_, i) => 2 * i);
const ys = steady.map((v, i) => Y(v, i));
let curved = false;
for (let i = 1; i < N - 1; i++)
    if (Math.abs(ys[i + 1] - 2 * ys[i] + ys[i - 1]) > 0.5) curved = true;
assert(curved, "anotador parejo se ve como curva continua (no recta)");

console.log(ok ? "✓ Todas las invariantes del cono se cumplen" : "FALLÓ");
process.exit(ok ? 0 : 1);
