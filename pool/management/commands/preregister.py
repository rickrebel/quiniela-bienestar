"""Preregistra un usuario por correo y nombre, inscrito a una quiniela."""

from django.contrib.auth import get_user_model
from django.core.management.base import (
    BaseCommand, CommandError, CommandParser)

from pool.models import Quiniela, UserQuiniela

User = get_user_model()


class Command(BaseCommand):
    help = "Preregistra un usuario (inactivo) e inscríbelo a una quiniela."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("email", help="Correo del usuario.")
        parser.add_argument("name", help="Nombre visible del jugador.")
        parser.add_argument(
            "quiniela", help="Slug de la quiniela a la que se inscribe.")

    def handle(self, *args, **options) -> None:
        email = options["email"]
        name = options["name"]
        quiniela = Quiniela.objects.filter(slug=options["quiniela"]).first()
        if quiniela is None:
            raise CommandError(
                f"No existe la quiniela «{options['quiniela']}».")

        # Alta del usuario (idempotente). El WindowUser lo materializa el
        # signal de UserQuiniela más abajo. Un usuario ya existente puede
        # sumarse a otra quiniela, así que no se aborta si ya está.
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(email=email, first_name=name)

        # La membresía dispara create_window_users (signal): un WindowUser
        # por ventana de la quiniela. get_or_create la hace idempotente.
        _, created = UserQuiniela.objects.get_or_create(
            user=user, quiniela=quiniela)
        if not created:
            self.stdout.write(self.style.WARNING(
                f"{email} ya estaba inscrito en «{quiniela.slug}»; "
                f"se omite."
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Usuario «{name}» inscrito en «{quiniela.slug}» ({email})."
        ))
