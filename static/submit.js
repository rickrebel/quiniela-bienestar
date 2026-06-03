const savingOverlay = document.getElementById("saving-overlay");

function buildPredictions(){
    const matches = document.querySelectorAll(".match");

    const predictions = [];

    matches.forEach(match => {
        const match_id = match.dataset.matchId;

        const goals_a = match.querySelector('[data-field="goals_a"]').value;
        const goals_b = match.querySelector('[data-field="goals_b"]').value;

        predictions.push({
            match_id: parseInt(match_id),
            goals_a: goals_a === "" ? null : parseInt(goals_a),
            goals_b: goals_b === "" ? null : parseInt(goals_b),
        });
    });

    return predictions;
}

async function savePredictions() {
    savingOverlay.hidden = false;

    const predictions = buildPredictions();

    try {
        const response = await fetch("/save_predictions", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({predictions})
        })
            //.then(res => res.json())
        const data = await response.json()
        if (!response.ok){
            throw new Error(
                data.error || "Error al guardar. Quién sabe qué pasó, a ver vuelve a intentar"
            )
        }
        alert("Predicciones guardadas correctamente")
    } catch(err) {
        alert(err.message)
    } finally {
        savingOverlay.hidden = true
    }
}

function sendPredictions() {
    const predictions = buildPredictions();

    if (predictions.some(p => p.goals_a === null || p.goals_b === null)){
        alert('tienes que llenar todos los partidos antes de enviar');
        return;
    }

    const confirmed = confirm(
        "Recuerda que una vez enviadas las predicciones no se pueden modificar."
    );

    if (!confirmed){
        return;
    }

    fetch("/submit_predictions", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({predictions})
    })
        .then(res => res.json())
}
