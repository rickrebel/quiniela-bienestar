from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_user, logout_user
from db.models import db, User
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, ValidationError
from wtforms.validators import DataRequired, Email, EqualTo

auth = Blueprint('auth', __name__)

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired('El email es requerido'), Email('Ingresa un correo válido')])
    password = PasswordField('Contraseña', validators=[DataRequired('La contraseña es requerida')])
    submit = SubmitField('Acceder')

    def validate_email(self, field):
        if User.query.filter_by(email=field.data).first() is None:
            raise ValidationError('Email no registrado.')


class RegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired('El email es requerido'), Email('Ingresa un correo válido')])
    password = PasswordField('Crear Contraseña', validators=[DataRequired('Porfa crea una contraseña')])
    password2 = PasswordField('Confirmar contraseña', validators=[DataRequired('Porfa confirma la contraseña'), EqualTo('password', 'Las contraseñas deben coincidir')])
    submit = SubmitField('Completar registro')

    def validate_email(self, field):
        user = User.query.filter_by(email=field.data).first()

        if user is None:
            raise ValidationError('Es necesario preregistrar el email')
        if user.is_active:
            raise ValidationError('El usuario ya está registrado')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            if user.verify_password(form.password.data):
                login_user(user, True)
                # next_page = request.args.get("next")
                # if next_page and next_page.startswith("/"):
                    # return redirect(next_page)
                return redirect(url_for('groups.grupos'))
            else:
                form.password.errors.append("Contraseña incorrecta")

    return render_template('auth/login.html', form=form)

@auth.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is not None and not user.is_active:
            user.password = form.password.data
            user.is_active = True
            db.session.commit()
            return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)

@auth.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))