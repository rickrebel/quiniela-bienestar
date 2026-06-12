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

function buildPayload() {
    const stage = document.querySelector(".content").dataset.stage;
    const predictions = [];

    document.querySelectorAll(".match").forEach(match => {
        const homeEl = match.querySelector('[data-field="home_goals"]');
        const awayEl = match.querySelector('[data-field="away_goals"]');
        // Sin inputs = equipos aún placeholder (final por definir): se omite.
        if (!homeEl || !awayEl) return;
        const home = homeEl.value;
        const away = awayEl.value;
        predictions.push({
            match_id: parseInt(match.dataset.matchId),
            home_goals: home === "" ? null : parseInt(home),
            away_goals: away === "" ? null : parseInt(away),
        });
    });

    return { stage, predictions };
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
    const editing = content && content.dataset.state === "editing";
    document.querySelectorAll(".match").forEach(matchEl => {
        markWinner(matchEl);
        if (!editing) return;
        matchEl.querySelectorAll('input[type="number"]').forEach(input => {
            input.addEventListener("input", () => markWinner(matchEl));
        });
    });
}

document.addEventListener("DOMContentLoaded", initWinnerMarks);

async function saveMatch(matchEl) {
    const home = matchEl.querySelector('[data-field="home_goals"]').value;
    const away = matchEl.querySelector('[data-field="away_goals"]').value;
    const payload = {
        home_goals: home === "" ? null : parseInt(home),
        away_goals: away === "" ? null : parseInt(away),
    };
    try {
        const data = await postPredictions(
            `/prediction/${matchEl.dataset.matchId}/`, payload
        );
        // Solo se avisa cuando el partido quedó completo (guardado real);
        // un input suelto al salir del campo no debe gritar "Guardado".
        if (data.complete) showSnack("Guardado");
    } catch (err) {
        showSnack(err.message, true);
    }
}

function initAutosave() {
    const content = document.querySelector(".content");
    if (!content || content.dataset.state !== "editing") return;

    document.querySelectorAll(".match").forEach(matchEl => {
        const container = matchEl.closest(".group, .knockout");
        matchEl.querySelectorAll('input[type="number"]').forEach(input => {
            input.addEventListener("change", () => {
                updateCounter(container);
                void saveMatch(matchEl);
            });
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
        block.querySelectorAll(".match-card").forEach(card => {
            body.appendChild(freezeCard(card));
        });
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
    return clone;
}

async function confirmSend() {
    savingOverlay.hidden = false;
    try {
        await postPredictions("/send/", buildPayload());
        location.reload();
    } catch (err) {
        alert(err.message);
        savingOverlay.hidden = true;
    }
}
