const savingOverlay = document.getElementById("saving-overlay");
const snackbar = document.getElementById("snackbar");

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + "=")) {
                cookieValue = decodeURIComponent(
                    cookie.substring(name.length + 1)
                );
                break;
            }
        }
    }
    return cookieValue;
}

const csrftoken = getCookie("csrftoken");

// Prefijo de la quiniela activa (slug del path); base.html lo inyecta.
const apiBase = "/" + (window.QUINIELA_SLUG || "");

// Estados en que la página admite llenar (borrador): edición normal y
// "upcoming" (se puede llenar aunque el envío aún no abra). Los inputs de
// partidos ya iniciados o sin equipos reales llegan deshabilitados, así que
// no disparan eventos aunque los listeners se registren.
function isFillableState(content) {
    const s = content && content.dataset.state;
    return s === "editing" || s === "upcoming";
}

function buildPayload() {
    const windowOrder = document.querySelector(".content").dataset.window;
    const predictions = [];

    document.querySelectorAll(".match").forEach(match => {
        const homeEl = match.querySelector('[data-field="home_goals"]');
        const awayEl = match.querySelector('[data-field="away_goals"]');
        // Sin inputs = equipos aún placeholder (final por definir): se omite.
        if (!homeEl || !awayEl) return;
        // Inputs deshabilitados = jornada no vigente (grupos): el envío se
        // acota a la sub-fase abierta, así que se omiten del payload.
        if (homeEl.disabled || awayEl.disabled) return;
        const home = homeEl.value;
        const away = awayEl.value;
        predictions.push({
            match_id: parseInt(match.dataset.matchId),
            home_goals: home === "" ? null : parseInt(home),
            away_goals: away === "" ? null : parseInt(away),
        });
    });

    return { window: windowOrder, predictions };
}

function isComplete(payload) {
    return !payload.predictions.some(
        p => p.home_goals === null || p.away_goals === null
    );
}

async function postPredictions(url, payload) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrftoken,
        },
        body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || "Algo salió mal, vuelve a intentar.");
    }
    return data;
}

// --- Autoguardado por partido ---
// Una predicción se guarda sola al cambiar un marcador (evento "change",
// que dispara al desenfocar). Regla del sistema: una fila Prediction solo
// existe si el partido tiene ambos marcadores, así que si falta cualquiera
// se manda null y el servidor la borra.

let snackTimer = null;
function showSnack(message, isError = false) {
    snackbar.querySelector(".snack-text").textContent = message;
    snackbar.classList.toggle("snackbar-error", isError);
    snackbar.classList.add("show");
    clearTimeout(snackTimer);
    snackTimer = setTimeout(() => snackbar.classList.remove("show"), 1600);
}

function isMatchFilled(matchEl) {
    const home = matchEl.querySelector('[data-field="home_goals"]');
    const away = matchEl.querySelector('[data-field="away_goals"]');
    // Sin inputs (equipos por definir) no cuenta como lleno.
    if (!home || !away) return false;
    return home.value !== "" && away.value !== "";
}

// Recuenta los partidos completos de la sección y actualiza su "N/total".
function updateCounter(container) {
    const matches = container.querySelectorAll(".match");
    let filled = 0;
    matches.forEach(m => { if (isMatchFilled(m)) filled += 1; });
    const counter = container.querySelector(".section-count");
    if (counter) counter.textContent = `${filled}/${matches.length}`;
}

// Subraya al ganador según un marcador: pick-win al que va arriba,
// pick-tie a ambos en empate, nada si falta algún valor (strings; ""
// = sin dato). Compartida con match_dialog.js (form de captura), por
// eso vive en window como localMatchTime.
window.applyWinnerMarks = function (homeNameEl, awayNameEl, homeVal, awayVal) {
    homeNameEl.classList.remove("pick-win", "pick-tie");
    awayNameEl.classList.remove("pick-win", "pick-tie");
    if (homeVal === "" || awayVal === "") return;

    const home = parseInt(homeVal);
    const away = parseInt(awayVal);
    if (home > away) {
        homeNameEl.classList.add("pick-win");
    } else if (away > home) {
        awayNameEl.classList.add("pick-win");
    } else {
        homeNameEl.classList.add("pick-tie");
        awayNameEl.classList.add("pick-tie");
    }
};

// Subraya el nombre del país que ganaría según el marcador previsto en
// una tarjeta de partido. Equipos por definir: sin estilo.
function markWinner(matchEl) {
    const homeEl = matchEl.querySelector('[data-field="home_goals"]');
    const awayEl = matchEl.querySelector('[data-field="away_goals"]');
    if (!homeEl || !awayEl) return;
    const teams = matchEl.querySelectorAll(".team");
    const homeName = teams[0]?.querySelector("span:not(.team-placeholder)");
    const awayName = teams[1]?.querySelector("span:not(.team-placeholder)");
    if (!homeName || !awayName) return;
    window.applyWinnerMarks(homeName, awayName, homeEl.value, awayEl.value);
}

// Pinta el subrayado al cargar (refleja predicciones ya guardadas en
// cualquier estado) y, si se está editando, lo actualiza en vivo al teclear.
function initWinnerMarks() {
    const content = document.querySelector(".content");
    const editing = isFillableState(content);
    document.querySelectorAll(".match").forEach(matchEl => {
        markWinner(matchEl);
        if (!editing) return;
        matchEl.querySelectorAll('input[type="number"]').forEach(input => {
            input.addEventListener("input", () => markWinner(matchEl));
        });
    });
}

document.addEventListener("DOMContentLoaded", initWinnerMarks);

// --- Selector de avance por penales (eliminatoria + empate previsto) ---
// El bloque .advancing-pick solo se renderiza en knockouts editables. Se
// muestra (clase .show) cuando el marcador previsto es empate; el equipo
// elegido (.is-picked) viaja como advancing_team_id en el autoguardado.

function advancingPick(matchEl) {
    return matchEl.closest(".match-card")?.querySelector(".advancing-pick");
}

function selectedAdvancing(matchEl) {
    const picked = advancingPick(matchEl)?.querySelector(
        ".advancing-opt.is-picked");
    return picked ? parseInt(picked.dataset.advancing) : null;
}

// Muestra el selector solo en empate (ambos marcadores iguales y llenos);
// fuera de empate lo oculta y limpia la selección.
function syncAdvancing(matchEl) {
    const pick = advancingPick(matchEl);
    if (!pick) return;
    const home = matchEl.querySelector('[data-field="home_goals"]').value;
    const away = matchEl.querySelector('[data-field="away_goals"]').value;
    const isDraw = home !== "" && away !== "" && home === away;
    pick.classList.toggle("show", isDraw);
    if (!isDraw) {
        pick.querySelectorAll(".advancing-opt").forEach(
            o => o.classList.remove("is-picked"));
    }
}

// Refresco en vivo de la tabla de un grupo tras guardar. Pide el
// fragmento recalculado al servidor (única fuente de verdad) y cambia
// banderas + tablas del <details> vivo. El contador por grupo descarta
// respuestas que lleguen fuera de orden (no pisan datos más nuevos).
const standingsSeq = {};

async function refreshGroupStandings(group) {
    const seq = (standingsSeq[group] = (standingsSeq[group] || 0) + 1);
    const url = `${apiBase}/grupos/standings/?group=${group}`;
    const res = await fetch(url);
    if (!res.ok || seq !== standingsSeq[group]) return;
    const html = await res.text();
    const frag = document.createRange().createContextualFragment(html);
    const live = document.querySelector(`.group[data-group="${group}"]`);
    if (!live) return;
    live.querySelector(".group-flags")
        .replaceWith(frag.querySelector(".group-flags"));
    live.querySelector("[data-standings-block]")
        .replaceWith(frag.querySelector("[data-standings-block]"));
    // standings.js reordena lo recién insertado según la variante vigente.
    document.dispatchEvent(new Event("standings:refresh"));
}

async function saveMatch(matchEl) {
    const home = matchEl.querySelector('[data-field="home_goals"]').value;
    const away = matchEl.querySelector('[data-field="away_goals"]').value;
    const payload = {
        home_goals: home === "" ? null : parseInt(home),
        away_goals: away === "" ? null : parseInt(away),
        advancing_team_id: selectedAdvancing(matchEl),
    };
    try {
        const data = await postPredictions(
            `${apiBase}/prediction/${matchEl.dataset.matchId}/`, payload
        );
        // Solo se avisa cuando el partido quedó completo (guardado real);
        // un input suelto al salir del campo no debe gritar "Guardado".
        if (data.complete) showSnack("Guardado");
        // Solo en grupos: las eliminatorias viven en .knockout y no tocan
        // tablas de grupo, así que el ?. corta y no se refresca nada.
        const group = matchEl.closest(".group[data-group]")?.dataset.group;
        if (group) void refreshGroupStandings(group);
    } catch (err) {
        showSnack(err.message, true);
    }
}

function initAutosave() {
    const content = document.querySelector(".content");
    if (!isFillableState(content)) return;

    document.querySelectorAll(".match").forEach(matchEl => {
        const container = matchEl.closest(".group, .knockout");
        syncAdvancing(matchEl);  // estado inicial según lo ya guardado
        matchEl.querySelectorAll('input[type="number"]').forEach(input => {
            input.addEventListener("input", () => syncAdvancing(matchEl));
            input.addEventListener("change", () => {
                updateCounter(container);
                void saveMatch(matchEl);
            });
        });
    });

    document.querySelectorAll(".advancing-opt").forEach(opt => {
        opt.addEventListener("click", () => {
            const pick = opt.closest(".advancing-pick");
            pick.querySelectorAll(".advancing-opt").forEach(
                o => o.classList.remove("is-picked"));
            opt.classList.add("is-picked");
            const matchEl = opt.closest(".match-card").querySelector(".match");
            void saveMatch(matchEl);
        });
    });
}

document.addEventListener("DOMContentLoaded", initAutosave);

const sendDialog = document.getElementById("send-dialog");

function sendPredictions() {
    if (!isComplete(buildPayload())) {
        alert("Tienes que llenar todos los partidos antes de enviar.");
        return;
    }
    buildSummary();
    sendDialog.showModal();
}

function closeSendDialog() {
    sendDialog.close();
}

// Llena el diálogo clonando las .match-card ya pintadas (mismo componente):
// congela los marcadores actuales, los deshabilita y quita la meta de
// fecha/sede. Los grupos van como encabezado plano (sin desplegable).
function buildSummary() {
    const body = document.getElementById("send-dialog-body");
    body.innerHTML = "";
    // .group cubre ambas vistas: details (por grupo) y section (fecha).
    const blocks = document.querySelectorAll(
        ".content > .group, .content > .knockout"
    );
    blocks.forEach(block => {
        // Bloques sin partidos (p. ej. "Mejores terceros") no aportan al
        // resumen: ni encabezado huérfano ni su switch "Simular cruces".
        // En grupos cada bloque trae las 3 jornadas pero solo se envía la
        // vigente: se filtran las tarjetas deshabilitadas (jornada no viva).
        const cards = [...block.querySelectorAll(".match-card")].filter(
            card => {
                const input = card.querySelector(".score input");
                return !input || !input.disabled;
            }
        );
        if (!cards.length) return;
        // Grupos: el título es .group-summary ("Grupo A"). Finales: no hay
        // summary, así que se usa el .chip-title de la sección (p. ej.
        // "OCTAVOS"). Se clona el que exista.
        const header =
            block.querySelector(".group-summary") ||
            block.querySelector(".chip-title");
        if (header) {
            const head = header.cloneNode(true);
            head.querySelector(".chevron")?.remove();
            body.appendChild(head);
        }
        cards.forEach(card => body.appendChild(freezeCard(card)));
    });
}

function freezeCard(card) {
    const clone = card.cloneNode(true);
    clone.querySelector(".meta")?.remove();
    // cloneNode no copia el value en vivo de los inputs; lo sincronizo.
    const liveInputs = card.querySelectorAll(".score input");
    clone.querySelectorAll(".score input").forEach((input, i) => {
        input.value = liveInputs[i].value;
        input.disabled = true;
    });
    summarizeAdvancing(clone);
    return clone;
}

// En el resumen del envío el selector de avance se colapsa a una línea de
// solo lectura: "Pasa: › <bandera> <equipo>". Si no se eligió (o no era
// empate) se quita el bloque.
function summarizeAdvancing(clone) {
    const pick = clone.querySelector(".advancing-pick");
    if (!pick) return;
    const picked = pick.querySelector(".advancing-opt.is-picked");
    if (!pick.classList.contains("show") || !picked) {
        pick.remove();
        return;
    }
    const flag = picked.querySelector("img");
    const name = picked.querySelector("span")?.textContent ?? "";
    pick.classList.add("advancing-summary");
    pick.innerHTML = "";

    const label = document.createElement("span");
    label.className = "advancing-summary-text";
    label.textContent = "Pasa:";
    const icon = document.createElement("span");
    icon.className = "material-symbols-outlined advancing-summary-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "chevron_right";
    pick.append(label, icon);
    if (flag) pick.append(flag.cloneNode(true));
    const teamName = document.createElement("span");
    teamName.className = "advancing-summary-text";
    teamName.textContent = name;
    pick.append(teamName);
}

async function confirmSend() {
    savingOverlay.hidden = false;
    try {
        await postPredictions(`${apiBase}/send/`, buildPayload());
        location.reload();
    } catch (err) {
        alert(err.message);
        savingOverlay.hidden = true;
    }
}
