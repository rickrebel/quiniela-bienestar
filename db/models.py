from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

login_manager = LoginManager()
login_manager.session_protection = 'basic'
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=False)
    did_pay = db.Column(db.Boolean, nullable=False, default=False)

    password_hash = db.Column(db.String(128))

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    flag = db.Column(db.String(100), unique=True)
    group_name = db.Column(db.String(1), nullable= False)
    points = db.Column(db.Integer)
    won_games = db.Column(db.Integer)
    draws = db.Column(db.Integer)
    out_goals = db.Column(db.Integer)
    in_goals = db.Column(db.Integer)
    red_cards = db.Column(db.Integer)
    yellow_cards = db.Column(db.Integer)


class Match(db.Model):
    __tablename__ = "matches"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    phase = db.Column(db.String(100), nullable=False)
    group_name = db.Column(db.String(1))
    stadium = db.Column(db.String(100))
    team_a_id = db.Column(
        db.String(100),
        db.ForeignKey('teams.id'),
        nullable=False
    )
    team_a = db.relationship('Team', foreign_keys=[team_a_id])
    team_b_id = db.Column(
        db.String(100),
        db.ForeignKey('teams.id'),
        nullable=False
    )
    team_b = db.relationship('Team', foreign_keys=[team_b_id])
    goals_a = db.Column(db.Integer)
    goals_b = db.Column(db.Integer)
    match_number = db.Column(db.Integer)


class Prediction(db.Model):
    __tablename__ = "predictions"

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "match_id",
            name="uq_prediction_user_match"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    user_id = db.Column(
        db.String(100),
        db.ForeignKey('users.id'),
        nullable=False
    )
    user = db.relationship('User', foreign_keys=[user_id])
    match_id = db.Column(
        db.Integer,
        db.ForeignKey('matches.id'),
        nullable=False
    )
    match = db.relationship('Match', foreign_keys=[match_id])
    goals_a = db.Column(db.Integer, nullable=False)
    goals_b = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(100), nullable=False)
