/* Prueba aislada del motor del cono (gráfica Historia, modo "cono").
 * No depende de Django ni del DOM: replica fitLine + coneBands con datos
 * sintéticos y comprueba las invariantes. Ejecutar: node .claude/...mjs */

const pad = { top: 12, left: 34 };
const plotW = 1000, plotH = 400;

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

// ---- Series sintéticas: dispersión creciente + un outlier que cae temprano
const N = 8;                       // columnas (col 0 = salida, todos en 0)
const X = i => pad.left + (i / (N - 1)) * plotW;
const xf = Array.from({ length: N }, (_, i) => (X(i) - pad.left) / plotW);

const players = [0, 1, 2, 3, 4].map(j => Array.from({ length: N },
    (_, i) => i === 0 ? 0 : 3 * i + (j - 2) * (0.4 * i)));
// "Russ": sube y luego se hunde fuerte a mitad del primer tramo.
const russ = [0, 5, 4, 2, 1, 6, 10, 14];
players.push(russ);

// ---- coneBands (réplica de progress.js) ----------------------------------
const loPt = xf.map((_, i) => Math.min(...players.map(p => p[i])));
const hiPt = xf.map((_, i) => Math.max(...players.map(p => p[i])));
const fit = xf.map((_, i) => i).filter(i => N <= 2 || i);   // sin la salida
const L = fitLine(fit.map(i => xf[i]), fit.map(i => loPt[i]));
const U = fitLine(fit.map(i => xf[i]), fit.map(i => hiPt[i]));
let dDown = 0, dUp = 0;
fit.forEach(i => {
    dDown = Math.max(dDown, (L.m * xf[i] + L.b) - loPt[i]);
    dUp = Math.max(dUp, hiPt[i] - (U.m * xf[i] + U.b));
});
L.b -= dDown; U.b += dUp;

const bands = xf.map((t) => {
    const lo = L.m * t + L.b, hi = U.m * t + U.b;
    const cush = 0.06 * Math.max(hi - lo, 1);
    const dlo = lo - cush, dataH = Math.max((hi + cush) - dlo, 0.5);
    const pxH = (0.45 + 0.55 * t) * plotH;
    const botPx = pad.top + plotH - (plotH - pxH) / 2;
    return { dlo, dataH, botPx, pxH };
});
const Y = (val, i) => bands[i].botPx - ((val - bands[i].dlo) / bands[i].dataH) * bands[i].pxH;

// ---- Invariantes ---------------------------------------------------------
let ok = true;
const assert = (c, m) => { if (!c) { ok = false; console.log("✗", m); } };
const near = (a, b, e = 0.01) => Math.abs(a - b) < e;
const coneTop = i => bands[i].botPx - bands[i].pxH;   // y del borde superior

// 1) fitLine recupera una recta perfecta.
const f = fitLine([0, 1, 2, 3], [1, 3, 5, 7]);
assert(near(f.m, 2) && near(f.b, 1), "fitLine recupera y=2x+1");

// 2) Cono: 45% en la primera columna, 100% en la última; banda centrada.
assert(near(bands[0].pxH, 0.45 * plotH), "primera columna al 45%");
assert(near(bands[N - 1].pxH, plotH), "última columna al 100%");
bands.forEach((b, i) =>
    assert(near(b.botPx - b.pxH / 2, pad.top + plotH / 2), `col ${i}: centrada`));

// 3) Escala (px/punto) DECRECE de izquierda a derecha.
for (let i = 1; i < N; i++) {
    const s0 = bands[i - 1].pxH / bands[i - 1].dataH;
    const s1 = bands[i].pxH / bands[i].dataH;
    assert(s1 < s0, `col ${i}: escala decrece (${s0.toFixed(1)}→${s1.toFixed(1)} px/pt)`);
}

// 4) CONTENCIÓN (el bug de Russ): toda línea, incl. el outlier, cae DENTRO
//    del cono en cada columna; nunca se va al fondo de la gráfica.
players.forEach((p, j) => p.forEach((v, i) => {
    const y = Y(v, i);
    assert(y <= bands[i].botPx + 0.01 && y >= coneTop(i) - 0.01,
        `jugador ${j} col ${i}: dentro del cono (y=${y.toFixed(0)})`);
}));

// 5) Russ hundido NO llega al fondo: en su peor columna queda cerca del
//    borde inferior del cono, no al 2-5% del alto.
const ri = russ.indexOf(Math.min(...russ.slice(1))) ;
const yr = Y(russ[ri], ri);
const pctFromBottom = (pad.top + plotH - yr) / plotH * 100;
assert(pctFromBottom > 10, `Russ no se va al fondo (queda al ${pctFromBottom.toFixed(0)}% del alto)`);

// 6) Un anotador PAREJO sale CURVO, no recto.
const steady = xf.map((_, i) => 2 * i);
const ys = steady.map((v, i) => Y(v, i));
let curved = false;
for (let i = 1; i < N - 1; i++)
    if (Math.abs(ys[i + 1] - 2 * ys[i] + ys[i - 1]) > 0.5) curved = true;
assert(curved, "anotador parejo se ve como curva continua (no recta)");

console.log(ok ? "✓ Todas las invariantes del cono se cumplen" : "FALLÓ");
process.exit(ok ? 0 : 1);
