from flask import Blueprint, render_template
from models import Match, Prediction
from collections import defaultdict

groups_bp = Blueprint("groups", __name__)

# muévelo a un útil en cuanto tengas otro
def convert_date(date):
    meses = [
        "enero", "febrero", "marzo", "abril",
        "mayo", "junio", "julio", "agosto",
        "septiembre", "octubre", "noviembre", "diciembre"
    ]
    return f"{date.day} de {meses[date.month - 1]}, {date:%H:%M}"

@groups_bp.route("/")
def home():
    matches = Match.query.all()
    predictions = Prediction.query.filter_by(
        # tendría que ser el current user
        user_id = 1
    ).all()
    predictions_by_match = {
        p.match_id: p
        for p in predictions
    }
    groups = defaultdict(list)

    for match in matches:
        if match.phase == "groups":
            prediction = predictions_by_match.get(match.id)
            print(prediction)
            if prediction:
                match.predicted_a = prediction.goals_a
                match.predicted_b = prediction.goals_b
            match.formatted_date = convert_date(match.date)
            groups[match.group_name].append(match)

    return render_template(
        "inicio.html",
        groups=groups,
        # debería ser una bandera en el usuario
        still_submitting = (
            Prediction.query
            .join(Match)
            .filter(
                Prediction.user_id == 1,
                Match.phase == "groups",
                Prediction.status == "submitted"
            )
            .first()
            is None
        )
    )
