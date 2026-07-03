// Llaves (bracket) del Mundial: óvalo vertical dibujado en SVG con vanilla JS
// (sin React). Cada partido es un par de círculos cuyo PUNTO MEDIO va sobre una
// elipse vertical (curva limpia) y cuyos 2 círculos se separan ± (L/2)·tangente,
// de modo que la línea del partido mide EXACTAMENTE L en toda su fase (16avos
// todos iguales, octavos todos iguales, etc.), mientras el conjunto se alarga en
// vertical para aprovechar el móvil. Los tallos a la fase siguiente varían. Los
// partidos se reparten por longitud de arco con simetría → costuras parejas.
// Colores desde los tokens del tema (var(--color-*)). Datos: build_bracket() ->
// #bracket-data. Ver pool/services/llaves.py.
(function () {
  "use strict";

  let SVGNS = "http://www.w3.org/2000/svg";

  // Geometría (verificada: separadores Δ=0 por fase, costuras parejas,
  // h/w≈1.6, sin encimes). Elipses verticales concéntricas por fase.
  let CX = 192, CY = 345;       // centro
  let AX = 170, AY = 280;       // semiejes de la elipse exterior (16avos)
  let K = [1.0, 0.74, 0.49, 0.20]; // escala por fase: 16avos, oct, cuartos, semis
  let L = [34, 40, 46, 50, 76]; // separador del partido por fase (+ final):
                                // crece con RAD para que los 2 círculos de un
                                // mismo partido no se fundan.
  let RAD = [14, 16, 18, 20, 23]; // radio del círculo por fase: crece suave;
                                  // el área (∝r²) sube sin saltos bruscos.
  let SEAMR = 1.18;             // costura = SEAMR · separación entre partidos
  // Separaciones al nivel de 16avos, calibradas al objetivo (en unidades de la
  // separación entre las 2 banderas de un partido): partidos 2.5, grupos-de-4
  // 5, izq/der 7.5, arriba/abajo 10.
  let CLUSTER = 0.103;          // gap dentro del par que comparte octavos
                                // (compacto): hueco = da·(1-CLUSTER)
  let INTER = 1.072;            // gap (en unidades da) entre los 2 pares de
                                // octavos de un ala (división "diagonal")
  let DV = 4.5;                 // "explode": corrimiento vertical de cada ala
                                // (sube arriba/abajo a 10u)
  let DH = -2.5;                // "explode": corrimiento horizontal (<0 comprime
                                // izq/der al centro, a 7.5u)
  let FIN_DX = 0;               // corrimiento de la final respecto al centro

  function el(tag, attrs) {
    let node = document.createElementNS(SVGNS, tag);
    if (attrs) {
      for (let k in attrs) {
        if (k === "style") node.setAttribute("style", attrs[k]);
        else node.setAttribute(k, attrs[k]);
      }
    }
    return node;
  }

  function computeLayout(data) {
    let matches = data.matches || [];
    let tree = data.tree || null; // avances de cuartos→final (real/estimado)
    let nodes = [], links = [];

    function ept(scale, th) {
      let r = (th * Math.PI) / 180;
      return [CX + AX * scale * Math.cos(r), CY + AY * scale * Math.sin(r)];
    }
    function tang(scale, th) {
      let r = (th * Math.PI) / 180;
      let vx = -AX * scale * Math.sin(r), vy = AY * scale * Math.cos(r);
      let m = Math.hypot(vx, vy) || 1;
      return [vx / m, vy / m];
    }
    // pareja de círculos de un partido: medio ± (Lp/2)·tangente.
    function pair(scale, th, Lp) {
      let M = ept(scale, th), t = tang(scale, th);
      return {
        a: [M[0] + (Lp / 2) * t[0], M[1] + (Lp / 2) * t[1]],
        b: [M[0] - (Lp / 2) * t[0], M[1] - (Lp / 2) * t[1]],
        mid: M,
      };
    }
    // g1/g2 = grupo de "explode" de cada extremo (para correrlo luego).
    function sep(p, g, played) { links.push({ x1: p.a[0], y1: p.a[1], x2: p.b[0], y2: p.b[1], strong: true, played: played, g1: g, g2: g }); }
    function stem(from, to, g1, g2, played) { links.push({ x1: from[0], y1: from[1], x2: to[0], y2: to[1], strong: false, played: played, g1: g1, g2: g2 }); }

    // C = intersección más cercana (a los padres) de la mediatriz de P0P1 con
    // la elipse `scale`. P0, P1 = centros (sobre la elipse externa) de los 2
    // partidos padres. Devuelve [x,y] o null si no hay intersección.
    function apex(scale, P0in, P1in) {
      // La elipse de `ept` está centrada en (CX,CY); para intersecarla con la
      // mediatriz hay que trabajar en coordenadas centradas (restar CX,CY).
      // El resultado se devuelve centrado, y `thOf` lo interpreta igual.
      let P0 = [P0in[0] - CX, P0in[1] - CY], P1 = [P1in[0] - CX, P1in[1] - CY];
      let a = P1[0] - P0[0], b = P1[1] - P0[1];
      let c = ((P1[0] * P1[0] + P1[1] * P1[1]) - (P0[0] * P0[0] + P0[1] * P0[1])) / 2;
      let rx = AX * scale, ry = AY * scale;
      let Mx = (P0[0] + P1[0]) / 2, My = (P0[1] + P1[1]) / 2;
      let sols = [];
      if (Math.abs(b) >= Math.abs(a)) {
        let A = 1 / (rx * rx) + (a * a) / (b * b * ry * ry);
        let B = -2 * a * c / (b * b * ry * ry);
        let C = c * c / (b * b * ry * ry) - 1;
        let d = B * B - 4 * A * C;
        if (d < 0) return null;
        let sd = Math.sqrt(d);
        [(-B + sd) / (2 * A), (-B - sd) / (2 * A)].forEach(function (x) {
          sols.push([x, (c - a * x) / b]);
        });
      } else {
        let A2 = 1 / (ry * ry) + (b * b) / (a * a * rx * rx);
        let B2 = -2 * b * c / (a * a * rx * rx);
        let C2 = c * c / (a * a * rx * rx) - 1;
        let d2 = B2 * B2 - 4 * A2 * C2;
        if (d2 < 0) return null;
        let sd2 = Math.sqrt(d2);
        [(-B2 + sd2) / (2 * A2), (-B2 - sd2) / (2 * A2)].forEach(function (y) {
          sols.push([(c - b * y) / a, y]);
        });
      }
      sols.sort(function (p, q) {
        return Math.hypot(p[0] - Mx, p[1] - My) - Math.hypot(q[0] - Mx, q[1] - My);
      });
      return sols[0];
    }
    function thOf(scale, pt) {
      return (Math.atan2(pt[1] / (AY * scale), pt[0] / (AX * scale)) * 180) / Math.PI;
    }
    // Recorre por la elipse (aleja del polo) a los octavos cercanos a un polo
    // (arriba=270, abajo=90) para que no queden tan juntos; los centrales no.
    let NUDGE_OCT = 20, NUDGE_QTR = 10, POLE_THRESH = 40;
    function arcPerDeg(scale, th) {
      let r = (th * Math.PI) / 180;
      return Math.hypot(AX * scale * Math.sin(r), AY * scale * Math.cos(r)) * Math.PI / 180;
    }
    function nudgePole(scale, th, px) {
      let poles = [270, 90];
      for (let i = 0; i < 2; i++) {
        let dd = ((th - poles[i] + 540) % 360) - 180; // dif. con signo al polo
        if (Math.abs(dd) < POLE_THRESH) {
          return th + Math.sign(dd) * (px / arcPerDeg(scale, th));
        }
      }
      return th;
    }


    // Tabla longitud-de-arco -> ángulo en la elipse exterior.
    let Ns = 1440, ths = [], cum = [0];
    for (let i = 0; i <= Ns; i++) ths.push((360 * i) / Ns);
    let prev = ept(1, ths[0]);
    for (let i = 1; i <= Ns; i++) {
      let p = ept(1, ths[i]);
      cum.push(cum[i - 1] + Math.hypot(p[0] - prev[0], p[1] - prev[1]));
      prev = p;
    }
    let P = cum[Ns];
    function arc2th(s) {
      s = ((s % P) + P) % P;
      let lo = 0, hi = Ns;
      while (lo < hi) { let mid = (lo + hi) >> 1; if (cum[mid] < s) lo = mid + 1; else hi = mid; }
      if (lo <= 0) return 0;
      let f = (s - cum[lo - 1]) / (cum[lo] - cum[lo - 1]);
      return ths[lo - 1] + f * (ths[lo] - ths[lo - 1]);
    }
    function arc0(qs) { return cum[Math.round(((qs % 360) / 360) * Ns)]; }

    let da = (P / 4) / (3 + SEAMR);

    // 4 cuadrantes (inicio cardinal, partidos del ala). Las 2 alas de arriba
    // (topL,topR) alimentan la semifinal de arriba; las de abajo, la de abajo.
    // El índice (0-3) es el grupo de "explode" (ver SHIFT abajo).
    // `gi` = grupo-de-4 del árbol (rebanada de `matches`) que alimenta el ala;
    // indexa tree.cuartos[] para las fases sin marcador. Difiere del índice de
    // ala porque la geometría cruza abajo (ala 2↔G3, ala 3↔G2).
    let wings = [
      { start: 180, ms: matches.slice(0, 4), gi: 0 },   // topL  ala 0
      { start: 270, ms: matches.slice(4, 8), gi: 1 },   // topR  ala 1
      { start: 0, ms: matches.slice(12, 16), gi: 3 },   // botR  ala 2
      { start: 90, ms: matches.slice(8, 12), gi: 2 },   // botL  ala 3
    ];

    // Huecos dentro de un ala: el par que comparte octavos va compacto
    // (da·(1-CLUSTER)); la división entre los 2 pares de octavos es da·INTER.
    // El resto del cuadrante (P/4 − span) es la costura entre alas.
    let gIntra = da * (1 - CLUSTER);
    let gInter = da * INTER;
    let off = [0, gIntra, gIntra + gInter, 2 * gIntra + gInter];
    let seam = (P / 4) - (2 * gIntra + gInter);

    // Por ala: coloca 16avos, octavos y el cuarto; guarda el medio del cuarto.
    wings.forEach(function (w, wi) {
      let ang = [];
      for (let j = 0; j < 4; j++) ang.push(arc2th(arc0(w.start) + seam / 2 + off[j]));

      // Grupo-de-4 del árbol: avances y marcadores (real/estimado) de las fases
      // sin par de 16avos; alimenta octavos, cuarto y —vía la semi— la final.
      let grp = tree && tree.cuartos ? tree.cuartos[w.gi] : null;

      // 16avos: 4 partidos (8 hojas) sobre la elipse exterior.
      let mid16 = [];
      for (let j = 0; j < 4; j++) {
        let m = w.ms[j], pp = pair(1, ang[j], L[0]);
        mid16.push(pp.mid);
        // Marcador del partido: real si se jugó, si no el pronosticado.
        let sc = m.played
          ? { home: m.home_goals, away: m.away_goals, played: true }
          : (m.pred
              ? { home: m.pred.home_goals, away: m.pred.away_goals, played: false }
              : null);
        // home en lado -tan (b), away en lado +tan (a).
        nodes.push({ x: pp.b[0], y: pp.b[1], r: RAD[0], team: m.home, match: m, g: wi, mid: pp.mid, score: sc, side: "home" });
        nodes.push({ x: pp.a[0], y: pp.a[1], r: RAD[0], team: m.away, match: m, g: wi, mid: pp.mid, score: sc, side: "away" });
        sep(pp, wi, m.played);
      }

      // octavos: 2 partidos; cada círculo = ganador de un 16avos. El centro va
      // equidistante de sus 2 padres (distancia real), no en el ángulo medio.
      let midOct = [];
      for (let g = 0; g < 2; g++) {
        // C = ápice de la mediatriz de los 2 centros padres de 16avos con la
        // elipse de octavos; ahí va el octavos (a la mitad de sus padres).
        let ap = apex(K[1], mid16[2 * g], mid16[2 * g + 1]);
        let th = ap ? thOf(K[1], ap) : (ang[2 * g] + ang[2 * g + 1]) / 2;
        th = nudgePole(K[1], th, NUDGE_OCT); // separa los octavos cercanos a los polos
        let po = pair(K[1], th, L[1]);
        midOct.push(po.mid);
        let mLo = w.ms[2 * g], mHi = w.ms[2 * g + 1];
        // Los 2 círculos = participantes del octavos (avance real/estimado de
        // mLo y mHi). predWinner = avance pronosticado (difuminado hasta que
        // haya ganador real). El marcador del octavos (grp.octavos[g].score) va
        // sobre su par: home = mLo (círculo b), away = mHi (círculo a).
        let osc = grp ? grp.octavos[g].score : null;
        nodes.push({ x: po.b[0], y: po.b[1], r: RAD[1], winner: mLo.winner || null, predWinner: (mLo.pred && mLo.pred.winner) || null, mid: po.mid, score: osc, side: "home", g: wi });
        nodes.push({ x: po.a[0], y: po.a[1], r: RAD[1], winner: mHi.winner || null, predWinner: (mHi.pred && mHi.pred.winner) || null, mid: po.mid, score: osc, side: "away", g: wi });
        sep(po, wi);
        stem(mid16[2 * g], po.b, wi, wi, mLo.played);
        stem(mid16[2 * g + 1], po.a, wi, wi, mHi.played);
      }

      // cuarto: C = ápice de la mediatriz de los 2 centros de octavos padres
      // con la elipse de cuartos. Slots vacíos (sin resultados).
      let apq = apex(K[2], midOct[0], midOct[1]);
      let thq = apq ? thOf(K[2], apq) : (ang[0] + ang[1] + ang[2] + ang[3]) / 4;
      thq = nudgePole(K[2], thq, NUDGE_QTR); // corre los cuartos hacia el ecuador
      let pq = pair(K[2], thq, L[2]);
      // Círculos del cuarto = avance de los 2 partidos de octavos del grupo
      // (b ↔ octavos g0, a ↔ octavos g1); real si ya se jugó, si no estimado.
      // El marcador del cuarto (grp.cuarto.score) va sobre su par.
      let o0 = grp ? grp.octavos[0] : null, o1 = grp ? grp.octavos[1] : null;
      let qsc = grp ? grp.cuarto.score : null;
      nodes.push({ x: pq.b[0], y: pq.b[1], r: RAD[2], winner: o0 && o0.real, predWinner: o0 && o0.pred, mid: pq.mid, score: qsc, side: "home", g: wi });
      nodes.push({ x: pq.a[0], y: pq.a[1], r: RAD[2], winner: o1 && o1.real, predWinner: o1 && o1.pred, mid: pq.mid, score: qsc, side: "away", g: wi });
      sep(pq, wi);
      stem(midOct[0], pq.b, wi, wi);
      stem(midOct[1], pq.a, wi, wi);
      w.quarterMid = pq.mid;
      w.g = wi;
    });

    // semifinales: arriba (alas 0,1) en θ=270; abajo (alas 3,2) en θ=90.
    // final: 2 círculos HORIZONTALES (uno al lado del otro) centrados (grupo 6).
    let finMid = [CX + FIN_DX, CY];
    let fin = [[finMid[0] - L[4] / 2, CY], [finMid[0] + L[4] / 2, CY]];
    // Círculos de la final = avance de cada semifinal (izq ↔ semi de arriba,
    // der ↔ semi de abajo); los 2 finalistas real/estimado.
    let sem = tree && tree.semis ? tree.semis : null;
    let s0 = sem ? sem[0] : null, s1 = sem ? sem[1] : null;
    let fsc = tree ? tree.final : null; // marcador de la final (real/estimado)
    nodes.push({ x: fin[0][0], y: fin[0][1], r: RAD[4], winner: s0 && s0.real, predWinner: s0 && s0.pred, mid: finMid, score: fsc, side: "home", g: 6 });
    nodes.push({ x: fin[1][0], y: fin[1][1], r: RAD[4], winner: s1 && s1.real, predWinner: s1 && s1.pred, mid: finMid, score: fsc, side: "away", g: 6 });
    links.push({ x1: fin[0][0], y1: fin[0][1], x2: fin[1][0], y2: fin[1][1], strong: true, g1: 6, g2: 6 });

    [
      // arriba → círculo izq. de la final; abajo → círculo der.
      { th: 270, left: wings[0], right: wings[1], g: 4, finTo: fin[0], si: 0 },
      { th: 90, left: wings[3], right: wings[2], g: 5, finTo: fin[1], si: 1 },
    ].forEach(function (s) {
      let ps = pair(K[3], s.th, L[3]);
      // círculo izquierdo (menor x) = ala izquierda; derecho = ala derecha.
      let lft = ps.a[0] <= ps.b[0] ? ps.a : ps.b;
      let rgt = ps.a[0] <= ps.b[0] ? ps.b : ps.a;
      // Cada círculo de la semi = avance del cuarto de esa ala (real/estimado).
      // El marcador de la semi (tree.semis[si].score) va sobre su par: home =
      // ala izquierda (lft), away = derecha (rgt).
      let lc = tree && tree.cuartos ? tree.cuartos[s.left.gi] : null;
      let rc = tree && tree.cuartos ? tree.cuartos[s.right.gi] : null;
      let lq = lc ? lc.cuarto : null, rq = rc ? rc.cuarto : null;
      let ssc = tree && tree.semis ? tree.semis[s.si].score : null;
      nodes.push({ x: lft[0], y: lft[1], r: RAD[3], winner: lq && lq.real, predWinner: lq && lq.pred, mid: ps.mid, score: ssc, side: "home", g: s.g });
      nodes.push({ x: rgt[0], y: rgt[1], r: RAD[3], winner: rq && rq.real, predWinner: rq && rq.pred, mid: ps.mid, score: ssc, side: "away", g: s.g });
      sep(ps, s.g);
      stem(s.left.quarterMid, lft, s.left.g, s.g);
      stem(s.right.quarterMid, rgt, s.right.g, s.g);
      // cada semifinal se une a su propio círculo de la final (no al medio).
      stem(ps.mid, s.finTo, s.g, 6);
    });

    // "Explode": corre cada grupo hacia afuera desde el centro. Alas en
    // diagonal (DH,DV); semis sólo vertical (para no partirlas); final quieta.
    // Abre un canal horizontal (arriba/abajo) y uno vertical (izq/der).
    let SHIFT = [
      { dx: -DH, dy: -DV }, { dx: DH, dy: -DV },   // alas 0,1 (arriba)
      { dx: DH, dy: DV }, { dx: -DH, dy: DV },     // alas 2,3 (abajo)
      { dx: 0, dy: -DV }, { dx: 0, dy: DV },        // semis arriba/abajo
      { dx: 0, dy: 0 },                             // final
    ];
    nodes.forEach(function (n) {
      let s = SHIFT[n.g]; n.x += s.dx; n.y += s.dy;
      if (n.mid) n.mid = [n.mid[0] + s.dx, n.mid[1] + s.dy];
    });
    links.forEach(function (l) {
      let s1 = SHIFT[l.g1], s2 = SHIFT[l.g2];
      l.x1 += s1.dx; l.y1 += s1.dy; l.x2 += s2.dx; l.y2 += s2.dy;
    });

    return { nodes: nodes, links: links };
  }

  function render(root, data) {
    let geo = computeLayout(data);

    let svg = el("svg", {
      viewBox: "4 45 376 601",
      width: "100%",
      style: "display:block;overflow:visible",
    });

    // Filtro de brillo (halo) para el contorno del ganador.
    let defs = el("defs");
    let glow = el("filter", {
      id: "win-glow", x: "-90%", y: "-90%", width: "280%", height: "280%",
    });
    glow.appendChild(el("feGaussianBlur", {
      in: "SourceAlpha", stdDeviation: "1.6", result: "b",
    }));
    glow.appendChild(el("feFlood", {
      style: "flood-color:var(--color-primary);flood-opacity:1", result: "f",
    }));
    // "in" recorta el flood a la silueta difuminada → sale SOLO el halo (sin
    // redibujar el trazo fuente encima).
    glow.appendChild(el("feComposite", { in: "f", in2: "b", operator: "in" }));
    defs.appendChild(glow);
    svg.appendChild(defs);

    let nodeEls = [];

    function paint() {
      nodeEls.forEach(function (e) {
        let hot = e.winner; // resaltado del ganador real: glow + contorno dorado
        e.bg.style.stroke =
          "color-mix(in oklch, var(--color-base-content) 28%, transparent)";
        e.bg.style.strokeWidth = "1";
        // El glow es un círculo aparte (detrás de la bandera): se enciende con
        // el filtro y se apaga bajando su opacidad a 0.
        if (e.glow) {
          e.glow.style.filter = hot ? "url(#win-glow)" : "none";
          e.glow.style.opacity = hot ? "1" : "0";
        }
        if (!e.ring) return;
        e.ring.style.stroke = hot
          ? "var(--color-primary)"
          : "color-mix(in oklch, var(--color-base-content) 45%, transparent)";
        e.ring.style.strokeWidth = hot ? "0.9" : "1";
      });
    }

    geo.links.forEach(function (l) {
      // Partido ya jugado → línea sólida (opacity 1); pendiente → tenue.
      let stroke = l.played
        ? "var(--color-base-content)"
        : (l.strong
            ? "color-mix(in oklch, var(--color-base-content) 38%, transparent)"
            : "color-mix(in oklch, var(--color-base-content) 18%, transparent)");
      svg.appendChild(
        el("line", {
          x1: l.x1, y1: l.y1, x2: l.x2, y2: l.y2,
          style: "stroke:" + stroke + ";stroke-width:" + (l.strong ? "1.5" : "1"),
        })
      );
    });

    geo.nodes.forEach(function (n) {
      // real = equipo confirmado (16avos: el matchup ya es real; octavos: el
      // ganador ya resuelto). Si aún no hay resultado, cae al avance
      // PRONOSTICADO (predWinner) → se pinta difuminado como estimación.
      let real = n.team || n.winner || null;
      let team = real || n.predWinner || null;
      let isEstimate = !real && !!team;
      let g = el("g", {
        style: "cursor:" + (team && team.id ? "pointer" : "default"),
      });
      // Bandera de equipo (real o estimada) → abre el team-dialog (delegación
      // global en team_dialog.js). Única interacción de la vista.
      if (team && team.id) g.setAttribute("data-dialog-team", team.id);
      let bg = el("circle", {
        cx: n.x, cy: n.y, r: n.r, style: "fill:var(--color-base-300)",
      });
      g.appendChild(bg);
      // Contorno de ganador SOLO en el equipo que ganó su partido jugado
      // (16avos). El círculo de octavos muestra quién avanzó, pero su propio
      // partido aún no se juega → sin contorno.
      let isWinner = !!(n.team && n.match && n.match.played &&
        n.match.winner && n.match.winner.code &&
        n.team.code && n.match.winner.code === n.team.code);
      let entry = { bg: bg, ring: null, glow: null, winner: isWinner };

      if (team && team.flag_url) {
        // Detrás de la bandera, en orden: 1) fuente del glow (radio un poco
        // mayor para que el halo asome POR FUERA del borde y no lo tape la
        // bandera); 2) contorno fino nítido. La bandera va encima de ambos.
        let glowSrc = el("circle", {
          cx: n.x, cy: n.y, r: n.r + 1,
          style: "fill:none;stroke:#000;stroke-width:2;opacity:0",
        });
        g.appendChild(glowSrc);
        entry.glow = glowSrc;
        let ring = el("circle", { cx: n.x, cy: n.y, r: n.r, style: "fill:none" });
        g.appendChild(ring);
        entry.ring = ring;
        let img = el("image", {
          x: n.x - n.r, y: n.y - n.r, width: n.r * 2, height: n.r * 2,
          preserveAspectRatio: "xMidYMid slice",
          // Estimación (avance pronosticado, aún sin ganador real) → mucho más
          // transparente que una bandera real (que va a opacidad plena).
          style: "clip-path:circle(50%)" + (isEstimate ? ";opacity:0.28" : ""),
        });
        img.setAttribute("href", team.flag_url);
        img.setAttributeNS("http://www.w3.org/1999/xlink", "href", team.flag_url);
        g.appendChild(img);
      }

      // Marcador del partido junto a su par de círculos, en TODAS las fases con
      // par y marcador (16avos→final): el real si ya se jugó (blanco pleno, el
      // lado ganador en primary), o el PRONOSTICADO si no (blanco "diluido").
      // El número de este círculo sale de su lado (home = b/izq, away = a/der).
      // Geometría: de M (medio del par) sale la PERPENDICULAR a AB hacia afuera
      // del óvalo (OUT px) y el número se corre ALONG px hacia su propio
      // círculo. Par horizontal (final, M≈centro): la normal apunta hacia abajo.
      if (team && team.flag_url && n.mid && n.score) {
        let goals = n.side === "home" ? n.score.home : n.score.away;
        if (goals !== null && goals !== undefined) {
          let played = n.score.played;
          // Resalta el número del lado ganador (solo jugado y sin empate).
          let hot = played && n.score.home !== n.score.away &&
            ((n.side === "home") === (n.score.home > n.score.away));
          let tx = n.x - n.mid[0], ty = n.y - n.mid[1];
          let td = Math.hypot(tx, ty) || 1;
          let ux = tx / td, uy = ty / td;
          let px = -uy, py = ux;
          let dot = px * (n.mid[0] - CX) + py * (n.mid[1] - CY);
          if (Math.abs(dot) < 0.001) { px = 0; py = 1; }
          else if (dot < 0) { px = -px; py = -py; }
          let ALONG = 6, OUT = 16;
          let num = el("text", {
            x: n.mid[0] + px * OUT + ux * ALONG,
            y: n.mid[1] + py * OUT + uy * ALONG,
            "text-anchor": "middle", "dominant-baseline": "central",
            style: "font-size:10px;font-weight:600;fill:" + (played
              ? (hot
                  ? "var(--color-primary)"
                  : "var(--color-base-content)")
              : "color-mix(in oklch, var(--color-base-content) 45%, transparent)"),
          });
          num.textContent = goals;
          g.appendChild(num);
        }
      }

      nodeEls.push(entry);
      svg.appendChild(g);
    });

    // Copa entre los 2 círculos de la final (decorativa; escala con el viewBox).
    let copaUrl = root.getAttribute("data-copa");
    if (copaUrl) {
      let th = 54, tw = (th * 427) / 854; // copa.png 427×854 → mantiene proporción
      let copa = el("image", {
        x: CX + FIN_DX - tw / 2, y: CY - 5 - th / 2,
        width: tw, height: th, preserveAspectRatio: "xMidYMid meet",
      });
      copa.setAttribute("href", copaUrl);
      copa.setAttributeNS("http://www.w3.org/1999/xlink", "href", copaUrl);
      svg.appendChild(copa);
    }

    root.innerHTML = "";
    root.appendChild(svg);
    paint();
  }

  document.addEventListener("DOMContentLoaded", function () {
    let dataEl = document.getElementById("bracket-data");
    let root = document.getElementById("bracket-svg");
    if (!dataEl || !root) return;
    let data;
    try {
      data = JSON.parse(dataEl.textContent);
    } catch (e) {
      return;
    }
    render(root, data);
  });
})();
