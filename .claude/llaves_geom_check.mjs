// Chequeo geométrico del bracket de llaves (herramienta de desarrollo, no se
// despliega). Porta computeLayout() de static/llaves.js SIN DOM: calcula los
// centros y radios de cada círculo (con el "explode" diagonal de las 4 alas
// desde el centro) para un juego de constantes, y reporta el gap mínimo entre
// círculos, los solapes, el bounding-box real y un viewBox sugerido. Uso:
// `node .claude/llaves_geom_check.mjs`.

// ---- Constantes candidatas (espejo de las de llaves.js) --------------------
const C = {
  CX: 192, CY: 345,
  AX: 170, AY: 280,
  K: [1.0, 0.74, 0.50, 0.20],
  L: [34, 40, 46, 44, 48],
  RAD: [14, 16, 18, 19, 21],
  SEAMR: 1.18,
  NUDGE_OCT: 20, NUDGE_QTR: 10, POLE_THRESH: 40,
  CLUSTER: 0.11,   // gap dentro del par que comparte octavos (compacto)
  INTER: 1.05,     // gap entre los 2 pares de octavos de un ala (en unidades da)
  DV: 16,          // "explode" vertical (separa arriba/abajo)
  DH: 6,           // "explode" horizontal (separa izq/der; < DV)
  FIN_DX: 0,
  VIEWBOX: { x: 0, y: 45, w: 384, h: 599 },
};

function computeLayout(C) {
  const { CX, CY, AX, AY, K, L, RAD, SEAMR, NUDGE_OCT, NUDGE_QTR,
          POLE_THRESH, CLUSTER, INTER, DV, DH, FIN_DX } = C;
  const nodes = [];
  const matches = Array.from({ length: 16 }, (_, i) => ({ id: i }));

  function ept(scale, th) {
    const r = (th * Math.PI) / 180;
    return [CX + AX * scale * Math.cos(r), CY + AY * scale * Math.sin(r)];
  }
  function tang(scale, th) {
    const r = (th * Math.PI) / 180;
    const vx = -AX * scale * Math.sin(r), vy = AY * scale * Math.cos(r);
    const m = Math.hypot(vx, vy) || 1;
    return [vx / m, vy / m];
  }
  function pair(scale, th, Lp) {
    const M = ept(scale, th), t = tang(scale, th);
    return {
      a: [M[0] + (Lp / 2) * t[0], M[1] + (Lp / 2) * t[1]],
      b: [M[0] - (Lp / 2) * t[0], M[1] - (Lp / 2) * t[1]],
      mid: M,
    };
  }
  function apex(scale, P0in, P1in) {
    const P0 = [P0in[0] - CX, P0in[1] - CY], P1 = [P1in[0] - CX, P1in[1] - CY];
    const a = P1[0] - P0[0], b = P1[1] - P0[1];
    const c = ((P1[0] * P1[0] + P1[1] * P1[1]) -
               (P0[0] * P0[0] + P0[1] * P0[1])) / 2;
    const rx = AX * scale, ry = AY * scale;
    const Mx = (P0[0] + P1[0]) / 2, My = (P0[1] + P1[1]) / 2;
    const sols = [];
    if (Math.abs(b) >= Math.abs(a)) {
      const A = 1 / (rx * rx) + (a * a) / (b * b * ry * ry);
      const B = -2 * a * c / (b * b * ry * ry);
      const Cc = c * c / (b * b * ry * ry) - 1;
      const d = B * B - 4 * A * Cc;
      if (d < 0) return null;
      const sd = Math.sqrt(d);
      [(-B + sd) / (2 * A), (-B - sd) / (2 * A)].forEach((x) => {
        sols.push([x, (c - a * x) / b]);
      });
    } else {
      const A2 = 1 / (ry * ry) + (b * b) / (a * a * rx * rx);
      const B2 = -2 * b * c / (a * a * rx * rx);
      const C2 = c * c / (a * a * rx * rx) - 1;
      const d2 = B2 * B2 - 4 * A2 * C2;
      if (d2 < 0) return null;
      const sd2 = Math.sqrt(d2);
      [(-B2 + sd2) / (2 * A2), (-B2 - sd2) / (2 * A2)].forEach((y) => {
        sols.push([(c - b * y) / a, y]);
      });
    }
    sols.sort((p, q) =>
      Math.hypot(p[0] - Mx, p[1] - My) - Math.hypot(q[0] - Mx, q[1] - My));
    return sols[0];
  }
  function thOf(scale, pt) {
    return (Math.atan2(pt[1] / (AY * scale), pt[0] / (AX * scale)) * 180)
      / Math.PI;
  }
  function arcPerDeg(scale, th) {
    const r = (th * Math.PI) / 180;
    return Math.hypot(AX * scale * Math.sin(r), AY * scale * Math.cos(r))
      * Math.PI / 180;
  }
  function nudgePole(scale, th, px) {
    const poles = [270, 90];
    for (let i = 0; i < 2; i++) {
      const dd = ((th - poles[i] + 540) % 360) - 180;
      if (Math.abs(dd) < POLE_THRESH) {
        return th + Math.sign(dd) * (px / arcPerDeg(scale, th));
      }
    }
    return th;
  }

  const Ns = 1440, ths = [], cum = [0];
  for (let i = 0; i <= Ns; i++) ths.push((360 * i) / Ns);
  let prev = ept(1, ths[0]);
  for (let i = 1; i <= Ns; i++) {
    const p = ept(1, ths[i]);
    cum.push(cum[i - 1] + Math.hypot(p[0] - prev[0], p[1] - prev[1]));
    prev = p;
  }
  const P = cum[Ns];
  function arc2th(s) {
    s = ((s % P) + P) % P;
    let lo = 0, hi = Ns;
    while (lo < hi) { const mid = (lo + hi) >> 1;
      if (cum[mid] < s) lo = mid + 1; else hi = mid; }
    if (lo <= 0) return 0;
    const f = (s - cum[lo - 1]) / (cum[lo] - cum[lo - 1]);
    return ths[lo - 1] + f * (ths[lo] - ths[lo - 1]);
  }
  function arc0(qs) { return cum[Math.round(((qs % 360) / 360) * Ns)]; }

  const da = (P / 4) / (3 + SEAMR);
  // Huecos dentro de un ala: par que comparte octavos (compacto) y la división
  // entre los 2 pares de octavos. El resto del cuadrante es la costura (seam).
  const gIntra = da * (1 - CLUSTER);
  const gInter = da * INTER;
  const off = [0, gIntra, gIntra + gInter, 2 * gIntra + gInter];
  const wingSpan = 2 * gIntra + gInter;

  // "Explode": cada ala se corre en diagonal hacia afuera; semis sólo vertical;
  // final quieta. Índices: 0-3 alas, 4 semi-arriba, 5 semi-abajo, 6 final.
  const SHIFT = [
    { dx: -DH, dy: -DV }, { dx: +DH, dy: -DV },
    { dx: +DH, dy: +DV }, { dx: -DH, dy: +DV },
    { dx: 0, dy: -DV }, { dx: 0, dy: +DV }, { dx: 0, dy: 0 },
  ];

  const wings = [
    { start: 180, ms: matches.slice(0, 4) },   // topL  (arriba-izq)  ala 0
    { start: 270, ms: matches.slice(4, 8) },   // topR  (arriba-der)  ala 1
    { start: 0, ms: matches.slice(12, 16) },   // botR  (abajo-der)   ala 2
    { start: 90, ms: matches.slice(8, 12) },   // botL  (abajo-izq)   ala 3
  ];

  wings.forEach((w, wi) => {
    const ang = [];
    const seam = (P / 4) - wingSpan;
    for (let j = 0; j < 4; j++)
      ang.push(arc2th(arc0(w.start) + seam / 2 + off[j]));

    const mid16 = [];
    for (let j = 0; j < 4; j++) {
      const pp = pair(1, ang[j], L[0]);
      mid16.push(pp.mid);
      nodes.push({ x: pp.b[0], y: pp.b[1], r: RAD[0], ph: 0, g: wi });
      nodes.push({ x: pp.a[0], y: pp.a[1], r: RAD[0], ph: 0, g: wi });
    }

    const midOct = [];
    for (let g = 0; g < 2; g++) {
      const ap = apex(K[1], mid16[2 * g], mid16[2 * g + 1]);
      let th = ap ? thOf(K[1], ap) : (ang[2 * g] + ang[2 * g + 1]) / 2;
      th = nudgePole(K[1], th, NUDGE_OCT);
      const po = pair(K[1], th, L[1]);
      midOct.push(po.mid);
      nodes.push({ x: po.b[0], y: po.b[1], r: RAD[1], ph: 1, g: wi });
      nodes.push({ x: po.a[0], y: po.a[1], r: RAD[1], ph: 1, g: wi });
    }

    const apq = apex(K[2], midOct[0], midOct[1]);
    let thq = apq ? thOf(K[2], apq) : (ang[0] + ang[1] + ang[2] + ang[3]) / 4;
    thq = nudgePole(K[2], thq, NUDGE_QTR);
    const pq = pair(K[2], thq, L[2]);
    nodes.push({ x: pq.b[0], y: pq.b[1], r: RAD[2], ph: 2, g: wi });
    nodes.push({ x: pq.a[0], y: pq.a[1], r: RAD[2], ph: 2, g: wi });
  });

  // Final: pareja HORIZONTAL centrada.
  const finMid = [CX + FIN_DX, CY];
  nodes.push({ x: finMid[0] - L[4] / 2, y: CY, r: RAD[4], ph: 4, g: 6 });
  nodes.push({ x: finMid[0] + L[4] / 2, y: CY, r: RAD[4], ph: 4, g: 6 });

  [
    { th: 270, g: 4 }, { th: 90, g: 5 },
  ].forEach((s) => {
    const ps = pair(K[3], s.th, L[3]);
    const lft = ps.a[0] <= ps.b[0] ? ps.a : ps.b;
    const rgt = ps.a[0] <= ps.b[0] ? ps.b : ps.a;
    nodes.push({ x: lft[0], y: lft[1], r: RAD[3], ph: 3, g: s.g });
    nodes.push({ x: rgt[0], y: rgt[1], r: RAD[3], ph: 3, g: s.g });
  });

  // Aplica el "explode" a cada nodo según su grupo.
  nodes.forEach((n) => { n.x += SHIFT[n.g].dx; n.y += SHIFT[n.g].dy; });
  return { nodes };
}

// ---- Chequeo ---------------------------------------------------------------
const PHASE = ["16avos", "octavos", "cuartos", "semis", "final"];
const { nodes } = computeLayout(C);
const GAP_MIN = 3;

let worst = Infinity, worstPair = null;
const overlaps = [];
for (let i = 0; i < nodes.length; i++) {
  for (let j = i + 1; j < nodes.length; j++) {
    const a = nodes[i], b = nodes[j];
    const gap = Math.hypot(a.x - b.x, a.y - b.y) - (a.r + b.r);
    if (gap < worst) { worst = gap; worstPair = [a, b]; }
    if (gap < GAP_MIN) overlaps.push({ a, b, gap });
  }
}

let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
for (const n of nodes) {
  minX = Math.min(minX, n.x - n.r); maxX = Math.max(maxX, n.x + n.r);
  minY = Math.min(minY, n.y - n.r); maxY = Math.max(maxY, n.y + n.r);
}
const M = 8;
const suggest = {
  x: Math.round(minX - M), y: Math.round(minY - M),
  w: Math.round((maxX - minX) + 2 * M), h: Math.round((maxY - minY) + 2 * M),
};

const fmt = (n) => `${PHASE[n.ph]}(${n.x.toFixed(0)},${n.y.toFixed(0)} r${n.r})`;
console.log(`nodos: ${nodes.length}`);
console.log(`gap mínimo entre círculos: ${worst.toFixed(1)}px` +
  (worstPair ? `  → ${fmt(worstPair[0])} vs ${fmt(worstPair[1])}` : ""));
console.log(`solapes (gap < ${GAP_MIN}px): ${overlaps.length}`);
overlaps.sort((x, y) => x.gap - y.gap).slice(0, 20)
  .forEach((o) => console.log(`  gap ${o.gap.toFixed(1)}  ${fmt(o.a)} vs ${fmt(o.b)}`));
console.log(`bbox contenido: x[${minX.toFixed(0)}..${maxX.toFixed(0)}] ` +
  `y[${minY.toFixed(0)}..${maxY.toFixed(0)}]`);
console.log(`viewBox sugerido: "${suggest.x} ${suggest.y} ${suggest.w} ${suggest.h}"`);
console.log(overlaps.length === 0 ? "OK ✅ sin encimes" : "AJUSTAR ❌");
