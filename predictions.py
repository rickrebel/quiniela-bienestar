from flask import Blueprint, request
from datetime import datetime
from quiniela import db
from models import Prediction

bp = Blueprint("predictions", __name__)

@bp.route("/submit_predictions", methods=["POST"])
def submit_predictions():
    data = request.get_json()

    user_id = "test-user"

    preds = []

    for p in data["predictions"]:
        preds.append(
            Prediction(
                date=datetime.utcnow(),
                user_id=user_id,
                match_id=p["match_id"],
                goals_a=p["goals_a"],
                goals_b=p["goals_b"],
            )
        )

    db.session.add_all(preds)
    db.session.commit()

    return {"status": "ok"}