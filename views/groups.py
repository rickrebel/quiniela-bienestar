from flask import Blueprint, render_template
from flask_login import login_required, current_user

from db.models import Match, Prediction
from collections import defaultdict

groups_bp = Blueprint("groups", __name__)

# muévelo a un util en cuanto tengas otro
def convert_date(date):
    meses = [
        "enero", "febrero", "marzo", "abril",
        "mayo", "junio", "julio", "agosto",
        "septiembre", "octubre", "noviembre", "diciembre"
    ]
    return f"{date.day} de {meses[date.month - 1]}, {date:%H:%M}"

@groups_bp.route("/grupos")
@login_required
def grupos():
    matches = Match.query.all()
    predictions = Prediction.query.filter_by(
        user_id=current_user.id
    ).all()
    predictions_by_match = {
        p.match_id: p
        for p in predictions
    }
    groups = defaultdict(list)

    for match in matches:
        if match.phase == "groups":
            prediction = predictions_by_match.get(match.id)
            if prediction:
                match.predicted_a = prediction.goals_a
                match.predicted_b = prediction.goals_b
            match.formatted_date = convert_date(match.date)
            groups[match.group_name].append(match)

    return render_template(
        "grupos.html",
        groups=groups,
        user=current_user,
        still_submitting = (
            Prediction.query
            .join(Match)
            .filter(
                Prediction.user_id == current_user.id,
                Match.phase == "groups",
                Prediction.status == "submitted"
            )
            .first()
            is None
        )
    )
