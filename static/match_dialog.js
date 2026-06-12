/* Dialog de detalle de partido + predicciones de todos.
 *
 * Render puro: los datos vienen pre-agrupados del servidor en el
 * json_script #match-dialog-data (ver pool/services/match_dialog.py).
 * Se construye DOM con createElement/textContent — los nombres de
 * jugador son datos de usuario y no deben interpolarse como HTML. */

(function () {
    const dataEl = document.getElementById("match-dialog-data");
    const dialog = document.getElementById("match-dialog");
    if (!dataEl || !dialog) return;

    const byId = new Map(
        JSON.parse(dataEl.textContent).map(m => [String(m.id), m])
    );
    const title = document.getElementById("match-dialog-title");
    const body = document.getElementById("match-dialog-body");

    /* el(tag, className, text): atajo para nodos hoja y contenedores. */
    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function teamLine(team, side) {
        const line = el("span", "day-team-line" +
            (side === "home" ? " day-team-line--home" : ""));
        const name = el("span",
            team.placeholder ? "team-placeholder" : "day-team-name",
            team.name);
        const flag = team.flag ? document.createElement("img") : null;
        if (flag) {
            flag.src = team.flag;
            flag.alt = team.name;
        }
        // En home la bandera va pegada al centro; en away al revés.
        if (side === "home") {
            line.append(name);
            if (flag) line.append(flag);
        } else {
            if (flag) line.append(flag);
            line.append(name);
        }
        return line;
    }

    function detailsSection(data) {
        const wrap = el("div", "match-dialog-details");
        wrap.append(el("span", "day-phase", data.phase));

        const teams = el("div", "day-teams");
        teams.append(teamLine(data.home, "home"));
        teams.append(el("span", "day-vs", "vs"));
        teams.append(teamLine(data.away, "away"));
        teams.append(el("span", "day-goals",
            data.finished ? String(data.score.home) : "–"));
        teams.append(el("span"));
        teams.append(el("span", "day-goals",
            data.finished ? String(data.score.away) : "–"));
        wrap.append(teams);

        if (data.penalties) {
            wrap.append(el("p", "day-note",
                `Penales: ${data.penalties.home} - ${data.penalties.away}`));
        }
        const local = window.localMatchTime && data.utc
            ? window.localMatchTime(data.utc) : null;
        const when = local
            ? `${local.day} · ${local.time} · ${data.stadium}`
            : `${data.day} · ${data.time} hora local · ${data.stadium}`;
        wrap.append(el("p", "match-dialog-meta", when));
        return wrap;
    }

    function finishedSection(data) {
        const cols = el("div", "day-cols");
        for (const side of ["home", "away"]) {
            const col = el("div", "day-col");
            const cards = data.cards[side];
            col.append(el("span", "day-cards",
                `🟨 ${cards.yellow}   🟥 ${cards.red}`));
            const list = el("ul", "day-scorers");
            for (const scorer of data.scorers[side]) {
                list.append(el("li", null, scorer));
            }
            col.append(list);
            cols.append(col);
        }
        return cols;
    }

    function predictionRow(pred) {
        const li = el("li", pred.is_self ? "is-self" : null);
        li.append(el("span", "rivals-name", pred.name));
        li.append(el("span", "rivals-score",
            `${pred.home} - ${pred.away}`));
        const pts = el("span", "rivals-pts");
        if (pred.points) {
            const value = el("b", `day-points-val--${pred.points.kind}`,
                `${pred.points.base} pts`);
            pts.append(value);
            if (pred.points.bonus) {
                pts.append(el("span", "diff-badge", "+1"));
            }
        } else {
            pts.textContent = "—";
        }
        li.append(pts);
        return li;
    }

    function predictionsSection(data) {
        const wrap = el("div", "match-dialog-preds");
        if (!data.revealed) {
            wrap.append(el("p", "day-note",
                "Las predicciones se revelan al cierre de la fase."));
            return wrap;
        }
        if (!data.groups.length) {
            wrap.append(el("p", "day-note",
                "Nadie guardó predicción para este partido."));
            return wrap;
        }
        for (const group of data.groups) {
            wrap.append(el("h6", "pred-group-head", group.label));
            const list = el("ul", "rivals-list");
            for (const pred of group.predictions) {
                list.append(predictionRow(pred));
            }
            wrap.append(list);
        }
        return wrap;
    }

    function open(data) {
        title.textContent =
            `${data.home.name} vs ${data.away.name}`;
        body.replaceChildren(detailsSection(data));
        if (data.finished) body.append(finishedSection(data));
        body.append(predictionsSection(data));
        dialog.showModal();
    }

    function maybeOpen(target) {
        // La tarjeta entera es trigger, pero capturar marcador manda:
        // un tap en los inputs no debe abrir el dialog. El resumen de
        // envío clona .match-card, así que ahí tampoco aplica.
        if (target.closest("input, #send-dialog")) return false;
        const trigger = target.closest("[data-dialog-match]");
        if (!trigger) return false;
        const data = byId.get(trigger.dataset.dialogMatch);
        if (data) open(data);
        return true;
    }

    document.addEventListener("click", e => {
        if (e.target.closest("[data-dialog-close]")) {
            dialog.close();
            return;
        }
        // Clic en el backdrop: el target es el propio dialog.
        if (e.target === dialog) {
            dialog.close();
            return;
        }
        maybeOpen(e.target);
    });

})();
