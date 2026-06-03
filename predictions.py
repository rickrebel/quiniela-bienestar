from flask import Blueprint, request
from flask_login import current_user
from datetime import datetime
from db.models import db, Prediction
# from excels import generate_excel

bp = Blueprint("predictions", __name__)

def process_prediction(preds, status):
    user_id = current_user.id

    for p in preds:
        prediction = Prediction.query.filter_by(
            user_id=user_id,
            match_id=p["match_id"],
        ).first()

        if prediction:
            if prediction.status == "submitted":
                return {
                    "error": "Ya enviaste tus predicciones y no puedes modificarlas"
                }, 403

            prediction.goals_a = p["goals_a"]
            prediction.goals_b = p["goals_b"]
            prediction.status = status
            prediction.date = datetime.utcnow()

        else:
            db.session.add(
                Prediction(
                    date=datetime.utcnow(),
                    user_id=user_id,
                    match_id=p["match_id"],
                    goals_a=p["goals_a"],
                    goals_b=p["goals_b"],
                    status=status
                )
            )

    db.session.commit()


@bp.route("/save_predictions", methods=["POST"])
def save_predictions():
    data = request.get_json()
    filtered_preds = [p for p in data["predictions"] if isinstance(p["goals_a"], int) and isinstance(p["goals_b"], int)]

    process_prediction(filtered_preds, "saved")
    return {"status": "ok"}

@bp.route("/submit_predictions", methods=["POST"])
def submit_predictions():
    # generate_excel()

    data = request.get_json()

    process_prediction(data["predictions"], "submitted")

    return {"status": "ok"}