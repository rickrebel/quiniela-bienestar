from flask import Flask

from db.models import db, login_manager

from predictions import bp as predictions_bp
from views.groups import groups_bp as route_groups
from views.auth import auth as auth_bp

from pathlib import Path
import os

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
db_path = BASE_DIR / "db" / "app.db"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
login_manager.init_app(app)

app.register_blueprint(auth_bp)
app.register_blueprint(predictions_bp)
app.register_blueprint(route_groups)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True)