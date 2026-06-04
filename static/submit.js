const savingOverlay = document.getElementById("saving-overlay");

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
        const home = match.querySelector('[data-field="home_goals"]').value;
        const away = match.querySelector('[data-field="away_goals"]').value;
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

async function savePredictions() {
    savingOverlay.hidden = false;
    try {
        await postPredictions("/save/", buildPayload());
        alert("Predicciones guardadas correctamente");
    } catch (err) {
        alert(err.message);
    } finally {
        savingOverlay.hidden = true;
    }
}

async function sendPredictions() {
    const payload = buildPayload();
    if (!isComplete(payload)) {
        alert("Tienes que llenar todos los partidos antes de enviar.");
        return;
    }
    if (!confirm(
        "Una vez enviadas tus predicciones ya no podrás editar esta fase, ¿confirmar?"
    )) {
        return;
    }

    savingOverlay.hidden = false;
    try {
        await postPredictions("/send/", payload);
        location.reload();
    } catch (err) {
        alert(err.message);
        savingOverlay.hidden = true;
    }
}

async function confirmPredictions() {
    const payload = buildPayload();
    if (!isComplete(payload)) {
        alert("Tienes que llenar todos los partidos antes de confirmar.");
        return;
    }
    if (!confirm(
        "Al confirmar ya NO podrás modificar esta fase. ¿Continuar?"
    )) {
        return;
    }

    savingOverlay.hidden = false;
    try {
        await postPredictions("/confirm/", payload);
        location.reload();
    } catch (err) {
        alert(err.message);
        savingOverlay.hidden = true;
    }
}
