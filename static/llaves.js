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

  var SVGNS = "http://www.w3.org/2000/svg";

  // Geometría (verificada: separadores Δ=0 por fase, costuras parejas,
  // h/w≈1.6, sin encimes). Elipses verticales concéntricas por fase.
  var CX = 192, CY = 345;       // centro
  var AX = 170, AY = 330;       // semiejes de la elipse exterior (16avos)
  var K = [1.0, 0.74, 0.46, 0.20]; // escala por fase: 16avos, oct, cuartos, semis
  var L = [34, 32, 30, 26, 30]; // separador del partido por fase (+ final)
  var RAD = [13, 13, 12, 12, 13]; // radio del círculo por fase
  var SEAMR = 1.18;             // costura = SEAMR · separación entre partidos

  function el(tag, attrs) {
    var node = document.createElementNS(SVGNS, tag);
    if (attrs) {
      for (var k in attrs) {
        if (k === "style") node.setAttribute("style", attrs[k]);
        else node.setAttribute(k, attrs[k]);
      }
    }
    return node;
  }

  function computeLayout(matches) {
    var nodes = [], links = [];

    function ept(scale, th) {
      var r = (th * Math.PI) / 180;
      return [CX + AX * scale * Math.cos(r), CY + AY * scale * Math.sin(r)];
    }
    function tang(scale, th) {
      var r = (th * Math.PI) / 180;
      var vx = -AX * scale * Math.sin(r), vy = AY * scale * Math.cos(r);
      var m = Math.hypot(vx, vy) || 1;
      return [vx / m, vy / m];
    }
    // pareja de círculos de un partido: medio ± (Lp/2)·tangente.
    function pair(scale, th, Lp) {
      var M = ept(scale, th), t = tang(scale, th);
      return {
        a: [M[0] + (Lp / 2) * t[0], M[1] + (Lp / 2) * t[1]],
        b: [M[0] - (Lp / 2) * t[0], M[1] - (Lp / 2) * t[1]],
        mid: M,
      };
    }
    function sep(p) { links.push({ x1: p.a[0], y1: p.a[1], x2: p.b[0], y2: p.b[1], strong: true }); }
    function stem(from, to) { links.push({ x1: from[0], y1: from[1], x2: to[0], y2: to[1], strong: false }); }

    // C = intersección más cercana (a los padres) de la mediatriz de P0P1 con
    // la elipse `scale`. P0, P1 = centros (sobre la elipse externa) de los 2
    // partidos padres. Devuelve [x,y] o null si no hay intersección.
    function apex(scale, P0in, P1in) {
      // La elipse de `ept` está centrada en (CX,CY); para intersecarla con la
      // mediatriz hay que trabajar en coordenadas centradas (restar CX,CY).
      // El resultado se devuelve centrado, y `thOf` lo interpreta igual.
      var P0 = [P0in[0] - CX, P0in[1] - CY], P1 = [P1in[0] - CX, P1in[1] - CY];
      var a = P1[0] - P0[0], b = P1[1] - P0[1];
      var c = ((P1[0] * P1[0] + P1[1] * P1[1]) - (P0[0] * P0[0] + P0[1] * P0[1])) / 2;
      var rx = AX * scale, ry = AY * scale;
      var Mx = (P0[0] + P1[0]) / 2, My = (P0[1] + P1[1]) / 2;
      var sols = [];
      if (Math.abs(b) >= Math.abs(a)) {
        var A = 1 / (rx * rx) + (a * a) / (b * b * ry * ry);
        var B = -2 * a * c / (b * b * ry * ry);
        var C = c * c / (b * b * ry * ry) - 1;
        var d = B * B - 4 * A * C;
        if (d < 0) return null;
        var sd = Math.sqrt(d);
        [(-B + sd) / (2 * A), (-B - sd) / (2 * A)].forEach(function (x) {
          sols.push([x, (c - a * x) / b]);
        });
      } else {
        var A2 = 1 / (ry * ry) + (b * b) / (a * a * rx * rx);
        var B2 = -2 * b * c / (a * a * rx * rx);
        var C2 = c * c / (a * a * rx * rx) - 1;
        var d2 = B2 * B2 - 4 * A2 * C2;
        if (d2 < 0) return null;
        var sd2 = Math.sqrt(d2);
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
    var NUDGE_OCT = 20, NUDGE_QTR = 10, POLE_THRESH = 40;
    function arcPerDeg(scale, th) {
      var r = (th * Math.PI) / 180;
      return Math.hypot(AX * scale * Math.sin(r), AY * scale * Math.cos(r)) * Math.PI / 180;
    }
    function nudgePole(scale, th, px) {
      var poles = [270, 90];
      for (var i = 0; i < 2; i++) {
        var dd = ((th - poles[i] + 540) % 360) - 180; // dif. con signo al polo
        if (Math.abs(dd) < POLE_THRESH) {
          return th + Math.sign(dd) * (px / arcPerDeg(scale, th));
        }
      }
      return th;
    }


    // Tabla longitud-de-arco -> ángulo en la elipse exterior.
    var Ns = 1440, ths = [], cum = [0];
    for (var i = 0; i <= Ns; i++) ths.push((360 * i) / Ns);
    var prev = ept(1, ths[0]);
    for (i = 1; i <= Ns; i++) {
      var p = ept(1, ths[i]);
      cum.push(cum[i - 1] + Math.hypot(p[0] - prev[0], p[1] - prev[1]));
      prev = p;
    }
    var P = cum[Ns];
    function arc2th(s) {
      s = ((s % P) + P) % P;
      var lo = 0, hi = Ns;
      while (lo < hi) { var mid = (lo + hi) >> 1; if (cum[mid] < s) lo = mid + 1; else hi = mid; }
      if (lo <= 0) return 0;
      var f = (s - cum[lo - 1]) / (cum[lo] - cum[lo - 1]);
      return ths[lo - 1] + f * (ths[lo] - ths[lo - 1]);
    }
    function arc0(qs) { return cum[Math.round(((qs % 360) / 360) * Ns)]; }

    var da = (P / 4) / (3 + SEAMR), dg = SEAMR * da;

    // 4 cuadrantes (inicio cardinal, partidos del ala). Las 2 alas de arriba
    // (topL,topR) alimentan la semifinal de arriba; las de abajo, la de abajo.
    var wings = [
      { start: 180, ms: matches.slice(0, 4) },   // topL  (arriba-izq)
      { start: 270, ms: matches.slice(4, 8) },   // topR  (arriba-der)
      { start: 0, ms: matches.slice(12, 16) },   // botR  (abajo-der)
      { start: 90, ms: matches.slice(8, 12) },   // botL  (abajo-izq)
    ];

    // Por ala: coloca 16avos, octavos y el cuarto; guarda el medio del cuarto.
    wings.forEach(function (w) {
      var ang = [];
      for (var j = 0; j < 4; j++) ang.push(arc2th(arc0(w.start) + dg / 2 + j * da));

      // 16avos: 4 partidos (8 hojas) sobre la elipse exterior.
      var mid16 = [];
      for (j = 0; j < 4; j++) {
        var m = w.ms[j], pp = pair(1, ang[j], L[0]);
        mid16.push(pp.mid);
        // home en lado -tan (b), away en lado +tan (a).
        nodes.push({ x: pp.b[0], y: pp.b[1], r: RAD[0], team: m.home, match: m });
        nodes.push({ x: pp.a[0], y: pp.a[1], r: RAD[0], team: m.away, match: m });
        sep(pp);
      }

      // octavos: 2 partidos; cada círculo = ganador de un 16avos. El centro va
      // equidistante de sus 2 padres (distancia real), no en el ángulo medio.
      var midOct = [];
      for (var g = 0; g < 2; g++) {
        // C = ápice de la mediatriz de los 2 centros padres de 16avos con la
        // elipse de octavos; ahí va el octavos (a la mitad de sus padres).
        var ap = apex(K[1], mid16[2 * g], mid16[2 * g + 1]);
        var th = ap ? thOf(K[1], ap) : (ang[2 * g] + ang[2 * g + 1]) / 2;
        th = nudgePole(K[1], th, NUDGE_OCT); // separa los octavos cercanos a los polos
        var po = pair(K[1], th, L[1]);
        midOct.push(po.mid);
        var mLo = w.ms[2 * g], mHi = w.ms[2 * g + 1];
        // círculo b (-tan, ángulo menor) = ganador de mLo; a (+tan) = ganador de mHi.
        nodes.push({ x: po.b[0], y: po.b[1], r: RAD[1], winner: mLo.winner || null, match: mLo });
        nodes.push({ x: po.a[0], y: po.a[1], r: RAD[1], winner: mHi.winner || null, match: mHi });
        sep(po);
        stem(mid16[2 * g], po.b);
        stem(mid16[2 * g + 1], po.a);
      }

      // cuarto: C = ápice de la mediatriz de los 2 centros de octavos padres
      // con la elipse de cuartos. Slots vacíos (sin resultados).
      var apq = apex(K[2], midOct[0], midOct[1]);
      var thq = apq ? thOf(K[2], apq) : (ang[0] + ang[1] + ang[2] + ang[3]) / 4;
      thq = nudgePole(K[2], thq, NUDGE_QTR); // corre los cuartos hacia el ecuador
      var pq = pair(K[2], thq, L[2]);
      nodes.push({ x: pq.b[0], y: pq.b[1], r: RAD[2] });
      nodes.push({ x: pq.a[0], y: pq.a[1], r: RAD[2] });
      sep(pq);
      stem(midOct[0], pq.b);
      stem(midOct[1], pq.a);
      w.quarterMid = pq.mid;
    });

    // semifinales: arriba (alas 0,1) en θ=270; abajo (alas 3,2) en θ=90.
    // final: 2 círculos verticales al centro.
    var fin = [[CX, CY - L[4] / 2], [CX, CY + L[4] / 2]];
    nodes.push({ x: fin[0][0], y: fin[0][1], r: RAD[4] });
    nodes.push({ x: fin[1][0], y: fin[1][1], r: RAD[4] });
    links.push({ x1: fin[0][0], y1: fin[0][1], x2: fin[1][0], y2: fin[1][1], strong: true });

    [
      { th: 270, left: wings[0], right: wings[1], finC: fin[0] },
      { th: 90, left: wings[3], right: wings[2], finC: fin[1] },
    ].forEach(function (s) {
      var ps = pair(K[3], s.th, L[3]);
      // círculo izquierdo (menor x) = ala izquierda; derecho = ala derecha.
      var lft = ps.a[0] <= ps.b[0] ? ps.a : ps.b;
      var rgt = ps.a[0] <= ps.b[0] ? ps.b : ps.a;
      nodes.push({ x: lft[0], y: lft[1], r: RAD[3] });
      nodes.push({ x: rgt[0], y: rgt[1], r: RAD[3] });
      sep(ps);
      stem(s.left.quarterMid, lft);
      stem(s.right.quarterMid, rgt);
      stem(ps.mid, s.finC);
    });

    return { nodes: nodes, links: links };
  }

  function render(root, panel, data) {
    var geo = computeLayout(data.matches || []);

    var svg = el("svg", {
      viewBox: "0 0 384 691",
      width: "100%",
      style: "display:block;overflow:visible",
    });

    var selected = { match: null };
    var nodeEls = [];

    function paint() {
      nodeEls.forEach(function (e) {
        var isSel = e.match && selected.match && e.match === selected.match;
        e.bg.style.stroke = isSel
          ? "var(--color-primary)"
          : "color-mix(in oklch, var(--color-base-content) 28%, transparent)";
        e.bg.style.strokeWidth = isSel ? "2.5" : "1";
        if (e.ring) {
          e.ring.style.stroke = isSel
            ? "var(--color-primary)"
            : "color-mix(in oklch, var(--color-base-content) 45%, transparent)";
          e.ring.style.strokeWidth = isSel ? "2.5" : "1";
        }
      });
    }

    function selectMatch(m) {
      selected.match = m;
      paint();
      renderPanel(panel, m);
    }

    geo.links.forEach(function (l) {
      svg.appendChild(
        el("line", {
          x1: l.x1, y1: l.y1, x2: l.x2, y2: l.y2,
          style:
            "stroke:" +
            (l.strong
              ? "color-mix(in oklch, var(--color-base-content) 38%, transparent)"
              : "color-mix(in oklch, var(--color-base-content) 18%, transparent)") +
            ";stroke-width:" + (l.strong ? "1.5" : "1"),
        })
      );
    });

    geo.nodes.forEach(function (n) {
      var team = n.team || n.winner || null;
      var g = el("g", { style: "cursor:" + (n.match ? "pointer" : "default") });
      var bg = el("circle", {
        cx: n.x, cy: n.y, r: n.r, style: "fill:var(--color-base-300)",
      });
      g.appendChild(bg);
      var entry = { match: n.match || null, bg: bg, ring: null };

      if (team && team.flag_url) {
        var img = el("image", {
          x: n.x - n.r, y: n.y - n.r, width: n.r * 2, height: n.r * 2,
          preserveAspectRatio: "xMidYMid slice", style: "clip-path:circle(50%)",
        });
        img.setAttribute("href", team.flag_url);
        img.setAttributeNS("http://www.w3.org/1999/xlink", "href", team.flag_url);
        g.appendChild(img);
        var ring = el("circle", { cx: n.x, cy: n.y, r: n.r, style: "fill:none" });
        g.appendChild(ring);
        entry.ring = ring;
      }

      if (n.match) {
        (function (m) {
          g.addEventListener("click", function () { selectMatch(m); });
        })(n.match);
      }

      nodeEls.push(entry);
      svg.appendChild(g);
    });

    root.innerHTML = "";
    root.appendChild(svg);
    paint();
    renderPanel(panel, null);
  }

  function flagImg(url) {
    return (
      '<img src="' + url +
      '" alt="" style="width:36px;height:36px;border-radius:50%;' +
      "object-fit:cover;flex:none;border:1px solid " +
      "color-mix(in oklch, var(--color-base-content) 45%, transparent)\">"
    );
  }

  function renderPanel(panel, m) {
    var muted = "color-mix(in oklch, var(--color-base-content) 60%, transparent)";
    if (!m) {
      panel.innerHTML =
        '<div style="text-align:center;font-size:12px;letter-spacing:0.04em;' +
        "color:" + muted + '">Toca una bandera para ver el partido</div>';
      return;
    }
    var played = m.played;
    var score = played ? m.home_goals + " — " + m.away_goals : "VS";
    var scoreColor = played ? "var(--color-primary)" : muted;
    var status = played
      ? "Finalizado · " + (m.venue || "")
      : "Por jugar · " + (m.date || "") + (m.venue ? " · " + m.venue : "");

    panel.innerHTML =
      '<div style="text-align:center;font-size:9px;letter-spacing:0.22em;' +
      "color:" + muted +
      ';text-transform:uppercase;margin-bottom:12px">16avos de final</div>' +
      '<div style="display:flex;align-items:center;justify-content:center;gap:12px">' +
      '<div style="display:flex;align-items:center;gap:9px;flex:1;justify-content:flex-end">' +
      '<span style="font-size:15px;color:var(--color-base-content);text-align:right">' +
      m.home.name + "</span>" + flagImg(m.home.flag_url) + "</div>" +
      '<div style="font-weight:600;font-size:19px;color:' + scoreColor +
      ';min-width:56px;text-align:center;white-space:nowrap">' + score + "</div>" +
      '<div style="display:flex;align-items:center;gap:9px;flex:1">' +
      flagImg(m.away.flag_url) +
      '<span style="font-size:15px;color:var(--color-base-content)">' +
      m.away.name + "</span></div></div>" +
      '<div style="text-align:center;font-size:10px;letter-spacing:0.05em;' +
      "color:" + muted + ';margin-top:12px">' + status + "</div>";
  }

  document.addEventListener("DOMContentLoaded", function () {
    var dataEl = document.getElementById("bracket-data");
    var root = document.getElementById("bracket-svg");
    var panel = document.getElementById("bracket-panel");
    if (!dataEl || !root || !panel) return;
    var data;
    try {
      data = JSON.parse(dataEl.textContent);
    } catch (e) {
      return;
    }
    render(root, panel, data);
  });
})();
