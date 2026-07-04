/* Dialog de detalle de partido + predicciones de todos.
 *
 * Render puro: los datos vienen pre-agrupados del servidor en el
 * json_script #match-dialog-data (ver pool/services/match_dialog.py).
 * Se construye DOM con createElement/textContent — los nombres de
 * jugador son datos de usuario y no deben interpolarse como HTML. */

(function () {
    const dialog = document.getElementById("match-dialog");
    if (!dialog) return;

    // Dos fuentes: los partidos de la página (#match-dialog-data, en
    // stage/por_fecha) y los de hoy del header (#today-dialog-data, en
    // todas). El mismo id trae los mismos datos, así que el merge es
    // idempotente; basta con que exista alguna.
    const byId = new Map();
    for (const id of ["match-dialog-data", "today-dialog-data"]) {
        const node = document.getElementById(id);
        if (!node) continue;
        const rows = JSON.parse(node.textContent);
        if (!Array.isArray(rows)) continue;
        for (const m of rows) {
            byId.set(String(m.id), m);
        }
    }
    const title = document.getElementById("match-dialog-title");
    const body = document.getElementById("match-dialog-body");

    // Alta dinámica: team_dialog.js suma los partidos del equipo traídos
    // por fetch para que sus tarjetas también abran este dialog. Por eso
    // no cortamos aunque byId venga vacío (p. ej. página sin partidos hoy).
    window.matchDialog = {
        add(rows) {
            if (!Array.isArray(rows)) return;
            for (const m of rows) byId.set(String(m.id), m);
        },
    };

    /* Espejos de constantes del server: LIVE_WINDOW (2 h) en
       pool/views/stages.py y RECORD_DELAY (105 min) en
       pool/views/results.py. Un desfase solo degrada UX: el endpoint
       revalida el timing de todos modos. */
    const LIVE_WINDOW_MS = 2 * 60 * 60 * 1000;
    const RECORD_DELAY_MS = 105 * 60 * 1000;

    /* Íconos de chips: los mismos SVG que <c-chip> en la tarjeta.
       Estáticos (sin datos de usuario), por eso innerHTML es seguro. */
    const CHIP_ICONS = {
        check: '<svg viewBox="0 0 24 24" aria-hidden="true">'
            + '<polyline points="4 13 10 19 20 6"/></svg>',
        mira: '<svg viewBox="0 0 24 24" aria-hidden="true">'
            + '<circle cx="12" cy="12" r="6"/>'
            + '<line x1="12" y1="2" x2="12" y2="7"/>'
            + '<line x1="12" y1="17" x2="12" y2="22"/>'
            + '<line x1="2" y1="12" x2="7" y2="12"/>'
            + '<line x1="17" y1="12" x2="22" y2="12"/></svg>',
    };
    const CLOSE_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true">'
        + '<line x1="5" y1="5" x2="19" y2="19"/>'
        + '<line x1="19" y1="5" x2="5" y2="19"/></svg>';

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
        teams.append(el("span", "day-goals day-goals--home",
            data.finished ? String(data.score.home) : "–"));
        teams.append(el("span"));
        teams.append(el("span", "day-goals day-goals--away",
            data.finished ? String(data.score.away) : "–"));
        wrap.append(teams);

        if (data.penalties) {
            wrap.append(el("p", "day-note",
                `Penales: ${data.penalties.home} - ${data.penalties.away}`));
        }
        wrap.append(metaSection(data));
        return wrap;
    }

    /* Mismo markup .meta de las tarjetas (reusa su CSS); fijo sin
       importar el status del partido. */
    function metaSection(data) {
        const meta = el("div", "meta");
        const local = window.localMatchTime && data.utc
            ? window.localMatchTime(data.utc) : null;
        meta.append(el("span", "meta-time",
            local ? local.time : `${data.time} hora local`));
        meta.append(el("span", "meta-date", local ? local.day : data.day));
        const place = el("span", "meta-place", data.stadium);
        if (data.stadium_flag) {
            const flag = document.createElement("img");
            flag.className = "meta-flag";
            flag.src = data.stadium_flag;
            flag.alt = "";
            place.append(flag);
        }
        meta.append(place);
        return meta;
    }

    /* Status al extremo derecho del header, mismo criterio que las
       tarjetas: FINISHED del server; "en juego" por ventana de 2 h. */
    function statusTag(data) {
        const start = Date.parse(data.utc);
        const now = Date.now();
        const live = !data.finished
            && now >= start && now < start + LIVE_WINDOW_MS;
        const label = data.finished
            ? "Finalizado" : (live ? "En juego" : "Por jugar");
        const tag = el("span", "dialog-status", label);
        if (live) tag.classList.add("live-tag");
        return tag;
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

    function predChip(chip) {
        const span = el("span", `pred-chip pred-chip--${chip.state}`);
        const icon = CHIP_ICONS[chip.icon];
        if (icon) span.innerHTML = icon;
        else span.textContent = chip.label;
        return span;
    }

    function flagImg(src) {
        const img = document.createElement("img");
        img.src = src;
        img.alt = "";
        return img;
    }

    /* Línea de puntos + chips. Reutilizada abajo de cada marcador o, cuando
       la diferencia del grupo no coincide con la final (todos los subgrupos
       puntúan igual), una sola vez centrada en el header. El texto va dorado
       si sumó y atenuado en "0 pts"; los chips agrupados aparte para separar
       ambos bloques. */
    function evalLine(points, chips) {
        const line = el("div", "pred-sub-eval");
        const pts = el("span", "pred-pts", `${points.total} pts`);
        pts.classList.add(points.total > 0 ? "pred-pts--gold"
                                           : "pred-pts--muted");
        line.append(pts);
        const chipGroup = el("div", "pred-chips");
        for (const chip of chips) chipGroup.append(predChip(chip));
        line.append(chipGroup);
        return line;
    }

    /* Un subgrupo = un marcador exacto. Arriba el marcador a la izquierda
       y los nombres en columnas a la derecha; abajo, centrada, la línea
       de puntos + chips — salvo que ``showEval`` sea falso (los puntos ya
       viven en el header porque son idénticos para todo el grupo). El
       marcador va dorado si es idéntico al real, atenuado si no acertó. */
    function subgroupRow(sub, showEval, finished, score) {
        const row = el("div", "pred-sub");

        const top = el("div", "pred-sub-top");
        const result = el("div", "pred-sub-result");
        if (finished) {
            const hit = sub.home === score.home && sub.away === score.away;
            result.classList.add(hit ? "pred-sub-result--hit"
                                     : "pred-sub-result--miss");
        }
        // Spans (no "a - b") para controlar el espaciado del guión.
        result.append(
            el("span", null, String(sub.home)),
            el("span", "pred-sub-dash", "-"),
            el("span", null, String(sub.away)),
        );
        top.append(result);

        const names = el("div", "pred-names");
        for (const person of sub.names) {
            names.append(el("span", person.is_self ? "is-self" : null,
                person.name));
        }
        top.append(names);
        row.append(top);

        if (showEval && sub.points) {
            row.append(evalLine(sub.points, sub.chips));
        }
        return row;
    }

    /* --- Captura manual de resultado (can_record del payload) --- */

    function numInput(value) {
        const input = document.createElement("input");
        input.type = "number";
        input.min = "0";
        input.step = "1";
        input.value = value;
        return input;
    }

    function recordRow(label, home, away) {
        const row = el("div", "record-row");
        row.append(home, el("span", "record-label", label), away);
        return row;
    }

    function recordSection(data) {
        const wrap = el("div", "record-form");
        const toggle = el("button", "submit-btn record-toggle",
            "Capturar resultado");
        toggle.type = "button";
        // Sin <form>: un submit dentro de <dialog> lo cerraría.
        const form = el("div", "record-body");
        form.hidden = true;
        toggle.addEventListener("click", () => {
            form.hidden = !form.hidden;
        });

        const inputs = {
            home_goals: numInput(""), away_goals: numInput(""),
            home_yellow: numInput("0"), away_yellow: numInput("0"),
            home_red: numInput("0"), away_red: numInput("0"),
            home_penalties: numInput(""), away_penalties: numInput(""),
        };
        const pensRow = recordRow("Penales",
            inputs.home_penalties, inputs.away_penalties);
        pensRow.hidden = true;
        const grid = el("div", "record-grid");
        grid.append(
            recordRow("Goles", inputs.home_goals, inputs.away_goals),
            recordRow("Amarillas", inputs.home_yellow, inputs.away_yellow),
            recordRow("Rojas", inputs.home_red, inputs.away_red),
            pensRow,
        );

        // Penales solo en eliminatoria con empate; al salir del caso se
        // vacían para que nunca viajen penales de un marcador anterior.
        // De paso, subrayado en vivo del ganador en el marcador de
        // arriba (helper compartido de submit.js).
        const names = body.querySelectorAll(".day-team-name");
        function onGoals() {
            const home = inputs.home_goals.value;
            const away = inputs.away_goals.value;
            const filled = home !== "" && away !== "";
            const tied = filled && parseInt(home) === parseInt(away);
            const needsPens = data.is_knockout && tied;
            pensRow.hidden = !needsPens;
            if (!needsPens) {
                inputs.home_penalties.value = "";
                inputs.away_penalties.value = "";
            }
            if (window.applyWinnerMarks && names.length === 2) {
                window.applyWinnerMarks(names[0], names[1], home, away);
            }
        }
        inputs.home_goals.addEventListener("input", onGoals);
        inputs.away_goals.addEventListener("input", onGoals);

        const error = el("p", "record-error", "");
        error.hidden = true;
        function showError(message) {
            error.textContent = message;
            error.hidden = false;
        }

        const confirmBox = el("div", "record-confirm");
        confirmBox.hidden = true;
        const saveBtn = el("button", "submit-btn", "Guardar resultado");
        saveBtn.type = "button";
        const actions = el("div", "record-actions");
        actions.append(saveBtn);

        function readValues() {
            const required = ["home_goals", "away_goals", "home_yellow",
                "away_yellow", "home_red", "away_red"];
            const v = {};
            for (const field of required) {
                const raw = inputs[field].value;
                const num = parseInt(raw);
                if (raw === "" || !(num >= 0)) {
                    showError("Llena todos los campos (0 si no hubo).");
                    return null;
                }
                v[field] = num;
            }
            v.home_penalties = null;
            v.away_penalties = null;
            if (!pensRow.hidden) {
                const hp = parseInt(inputs.home_penalties.value);
                const ap = parseInt(inputs.away_penalties.value);
                if (!(hp >= 0) || !(ap >= 0)) {
                    showError("Faltan los penales (hubo empate).");
                    return null;
                }
                if (hp === ap) {
                    showError("Los penales no pueden quedar empatados.");
                    return null;
                }
                v.home_penalties = hp;
                v.away_penalties = ap;
            }
            return v;
        }

        function backToForm() {
            confirmBox.hidden = true;
            grid.hidden = false;
            actions.hidden = false;
        }

        // Confirmación en el mismo dialog (no se anidan dialogs): se
        // sustituye el form por los mismos números capturados.
        function buildConfirm(v) {
            const score =
                `${data.home.name} ${v.home_goals} - ` +
                `${v.away_goals} ${data.away.name}`;
            const cards =
                `🟨 ${v.home_yellow} - ${v.away_yellow} · ` +
                `🟥 ${v.home_red} - ${v.away_red}`;
            confirmBox.replaceChildren(
                el("p", "record-summary", score),
                el("p", "record-summary", cards),
            );
            if (v.home_penalties !== null) {
                confirmBox.append(el("p", "record-summary",
                    `Penales: ${v.home_penalties} - ${v.away_penalties}`));
            }
            confirmBox.append(el("p", "day-note",
                "El resultado no se podrá cambiar después."));
            const fix = el("button", "submit-btn", "Corregir");
            fix.type = "button";
            fix.addEventListener("click", backToForm);
            const send = el("button", "submit-btn", "Confirmar");
            send.type = "button";
            send.addEventListener("click", () => submitResult(v, send));
            const btns = el("div", "record-actions");
            btns.append(fix, send);
            confirmBox.append(btns);
        }

        async function submitResult(v, btn) {
            // El POST dispara recompute_all (varios segundos): feedback
            // de espera y bloqueo del botón hasta el reload.
            btn.disabled = true;
            btn.classList.add("is-loading");
            const label = btn.textContent;
            btn.textContent = "Guardando…";
            try {
                const slug = window.QUINIELA_SLUG || "";
                const response = await fetch(
                    `/${slug}/match/${data.id}/result/`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        // csrftoken: global de submit.js; submit.js carga
                        // después de este archivo, pero esto corre al clic.
                        "X-CSRFToken": csrftoken,
                    },
                    body: JSON.stringify(v),
                });
                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.error || "Algo salió mal.");
                }
                // El resultado afecta tarjetas, standings y puntos:
                // recargar es lo único honesto.
                location.reload();
            } catch (err) {
                btn.disabled = false;
                btn.classList.remove("is-loading");
                btn.textContent = label;
                backToForm();
                showError(err.message);
            }
        }

        saveBtn.addEventListener("click", () => {
            error.hidden = true;
            const v = readValues();
            if (!v) return;
            buildConfirm(v);
            grid.hidden = true;
            actions.hidden = true;
            confirmBox.hidden = false;
        });

        form.append(grid, error, confirmBox, actions);
        wrap.append(toggle, form);
        return wrap;
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
        // Diferencia real (para decidir dónde van los puntos): si no coincide
        // con la del grupo, todos sus subgrupos puntúan igual y el desglose
        // se muestra una vez, centrado en el header.
        const finalDiff = data.finished
            ? data.score.home - data.score.away : null;

        for (const group of data.groups) {
            const head = el("h6", "pred-group-head");
            const gtitle = el("span", "pred-group-title");
            if (group.advancing_side) {
                // Empate repartido por equipo que avanza: "Empate pasa 🏴 COD"
                // (la bandera va en medio, no al inicio).
                gtitle.append(el("span", null, "Empate pasa"));
                const f = group.advancing_side === "home"
                    ? data.home.flag : data.away.flag;
                if (f) gtitle.append(flagImg(f));
                gtitle.append(el("span", null, group.advancing_code));
            } else if (group.diff === 0) {
                // Empate: solo banderas (local · "Empate" · visitante), sin
                // códigos.
                if (data.home.flag) gtitle.append(flagImg(data.home.flag));
                gtitle.append(el("span", null, group.label));
                if (data.away.flag) gtitle.append(flagImg(data.away.flag));
            } else {
                // Ventaja local: "🏴 COD  +N goles"; visitante, invertido:
                // "+N goles  COD 🏴" (bandera siempre pegada al código).
                const winner = group.diff > 0 ? data.home : data.away;
                const team = el("span", "pred-group-team");
                const flag = winner.flag ? flagImg(winner.flag) : null;
                const code = el("span", null, winner.fifa_code);
                const diff = el("span", null, group.label);
                if (group.diff > 0) {
                    if (flag) team.append(flag);
                    team.append(code);
                    gtitle.append(team, diff);
                } else {
                    team.append(code);
                    if (flag) team.append(flag);
                    gtitle.append(diff, team);
                }
            }
            // La diferencia coincide con la real (o empate vs empate): quien
            // atinó la diferencia se resalta con el título en dorado.
            if (data.finished && finalDiff === group.diff) {
                gtitle.classList.add("pred-group-title--hit");
            }
            head.append(gtitle);

            const first = group.subgroups[0];
            const headerEval = data.finished && finalDiff !== group.diff;
            if (headerEval && first && first.points) {
                head.append(evalLine(first.points, first.chips));
            }
            wrap.append(head);
            for (const sub of group.subgroups) {
                wrap.append(subgroupRow(
                    sub, !headerEval, data.finished, data.score));
            }
        }
        return wrap;
    }

    /* Bandera del equipo en el header (o su código/placeholder si aún no
       hay bandera, p. ej. cruce sin definir). */
    function headerFlag(team) {
        if (team.flag) {
            const img = document.createElement("img");
            img.src = team.flag;
            img.alt = team.name;
            return img;
        }
        return el("span", "dialog-flag-ph", team.name);
    }

    /* Header: banderas a la izquierda, status al centro, cerrar a la
       derecha (sustituye al botón "Cerrar" del footer). */
    function dialogHeader(data) {
        const flags = el("div", "dialog-flags");
        flags.append(headerFlag(data.home), headerFlag(data.away));
        const close = el("button", "dialog-close");
        close.type = "button";
        close.setAttribute("data-dialog-close", "");
        close.setAttribute("aria-label", "Cerrar");
        close.innerHTML = CLOSE_ICON;
        return [flags, statusTag(data), close];
    }

    function open(data) {
        title.replaceChildren(...dialogHeader(data));
        body.replaceChildren(detailsSection(data));
        if (data.finished) body.append(finishedSection(data));
        if (data.can_record
                && Date.now() >= Date.parse(data.utc) + RECORD_DELAY_MS) {
            body.append(recordSection(data));
        }
        body.append(predictionsSection(data));
        dialog.showModal();
    }

    function maybeOpen(target) {
        // La tarjeta entera es trigger, pero capturar marcador manda:
        // un tap en los inputs no debe abrir el dialog. El resumen de
        // envío clona .match-card, así que ahí tampoco aplica.
        if (target.closest("input, #send-dialog")) return false;
        // Un clic en un nombre/bandera de equipo abre el dialog de equipo
        // (team_dialog.js), no el de partido, aun dentro de una tarjeta.
        if (target.closest("[data-dialog-team]")) return false;
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
