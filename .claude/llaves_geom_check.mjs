// Chequeo geométrico del bracket de llaves (herramienta de desarrollo, no se
// despliega). Porta computeLayout() de static/llaves.js SIN DOM: sólo calcula
// los centros y radios de cada círculo para un juego de constantes, y reporta
// el gap mínimo entre parejas de círculos + los que se enciman + los que se
// salen del viewBox. Uso: `node .claude/llaves_geom_check.mjs`.

// ---- Constantes candidatas (espejo de las de llaves.js) --------------------
const C = {
  CX: 192, CY: 345,
  AX: 170, AY: 280,
  K: [1.0, 0.74, 0.46, 0.20],
  L: [34, 44, 52, 60, 82],
  RAD: [14, 18, 22, 28, 37],
  SEAMR: 1.18,
  NUDGE_OCT: 20, NUDGE_QTR: 10, POLE_THRESH: 40,
  VIEWBOX: { x: 0, y: 10, w: 384, h: 670 },
};

function computeLayout(C) {
  const { CX, CY, AX, AY, K, L, RAD, SEAMR, NUDGE_OCT, NUDGE_QTR,
          POLE_THRESH } = C;
  const nodes = [], links = [];
  // 16 partidos ficticios: la geometría no depende de equipos/ganadores.
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

  const da = (P / 4) / (3 + SEAMR), dg = SEAMR * da;

  const wings = [
    { start: 180, ms: matches.slice(0, 4) },
    { start: 270, ms: matches.slice(4, 8) },
    { start: 0, ms: matches.slice(12, 16) },
    { start: 90, ms: matches.slice(8, 12) },
  ];

  wings.forEach((w) => {
    const ang = [];
    for (let j = 0; j < 4; j++) ang.push(arc2th(arc0(w.start) + dg / 2 + j * da));

    const mid16 = [];
    for (let j = 0; j < 4; j++) {
      const pp = pair(1, ang[j], L[0]);
      mid16.push(pp.mid);
      nodes.push({ x: pp.b[0], y: pp.b[1], r: RAD[0], ph: 0 });
      nodes.push({ x: pp.a[0], y: pp.a[1], r: RAD[0], ph: 0 });
    }

    const midOct = [];
    for (let g = 0; g < 2; g++) {
      const ap = apex(K[1], mid16[2 * g], mid16[2 * g + 1]);
      let th = ap ? thOf(K[1], ap) : (ang[2 * g] + ang[2 * g + 1]) / 2;
      th = nudgePole(K[1], th, NUDGE_OCT);
      const po = pair(K[1], th, L[1]);
      midOct.push(po.mid);
      nodes.push({ x: po.b[0], y: po.b[1], r: RAD[1], ph: 1 });
      nodes.push({ x: po.a[0], y: po.a[1], r: RAD[1], ph: 1 });
    }

    const apq = apex(K[2], midOct[0], midOct[1]);
    let thq = apq ? thOf(K[2], apq) : (ang[0] + ang[1] + ang[2] + ang[3]) / 4;
    thq = nudgePole(K[2], thq, NUDGE_QTR);
    const pq = pair(K[2], thq, L[2]);
    nodes.push({ x: pq.b[0], y: pq.b[1], r: RAD[2], ph: 2 });
    nodes.push({ x: pq.a[0], y: pq.a[1], r: RAD[2], ph: 2 });
    w.quarterMid = pq.mid;
  });

  const fin = [[CX, CY - L[4] / 2], [CX, CY + L[4] / 2]];
  nodes.push({ x: fin[0][0], y: fin[0][1], r: RAD[4], ph: 4 });
  nodes.push({ x: fin[1][0], y: fin[1][1], r: RAD[4], ph: 4 });

  [
    { th: 270, left: wings[0], right: wings[1], finC: fin[0] },
    { th: 90, left: wings[3], right: wings[2], finC: fin[1] },
  ].forEach((s) => {
    const ps = pair(K[3], s.th, L[3]);
    const lft = ps.a[0] <= ps.b[0] ? ps.a : ps.b;
    const rgt = ps.a[0] <= ps.b[0] ? ps.b : ps.a;
    nodes.push({ x: lft[0], y: lft[1], r: RAD[3], ph: 3 });
    nodes.push({ x: rgt[0], y: rgt[1], r: RAD[3], ph: 3 });
  });

  return { nodes, links };
}

// ---- Chequeo ---------------------------------------------------------------
const PHASE = ["16avos", "octavos", "cuartos", "semis", "final"];
const { nodes } = computeLayout(C);
const GAP_MIN = 3; // holgura mínima aceptable entre círculos (px)

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

const vb = C.VIEWBOX, outside = [];
for (const n of nodes) {
  if (n.x - n.r < vb.x || n.x + n.r > vb.x + vb.w ||
      n.y - n.r < vb.y || n.y + n.r > vb.y + vb.h) outside.push(n);
}

const fmt = (n) => `${PHASE[n.ph]}(${n.x.toFixed(0)},${n.y.toFixed(0)} r${n.r})`;
console.log(`nodos: ${nodes.length}`);
console.log(`gap mínimo entre círculos: ${worst.toFixed(1)}px` +
  (worstPair ? `  → ${fmt(worstPair[0])} vs ${fmt(worstPair[1])}` : ""));
console.log(`solapes (gap < ${GAP_MIN}px): ${overlaps.length}`);
overlaps
  .sort((x, y) => x.gap - y.gap)
  .slice(0, 20)
  .forEach((o) =>
    console.log(`  gap ${o.gap.toFixed(1)}  ${fmt(o.a)} vs ${fmt(o.b)}`));
console.log(`fuera del viewBox: ${outside.length}`);
outside.slice(0, 20).forEach((n) => console.log(`  ${fmt(n)}`));
console.log(overlaps.length === 0 && outside.length === 0
  ? "OK ✅ sin encimes y todo dentro del viewBox"
  : "AJUSTAR ❌");
