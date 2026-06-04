"""Preregistra un usuario por correo y nombre visible."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser

from pool.models import StageUser
from tournament.models import Stage

User = get_user_model()


class Command(BaseCommand):
    help = "Preregistra un usuario (inactivo) por correo y nombre."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("email", help="Correo del usuario.")
        parser.add_argument("name", help="Nombre visible del jugador.")

    def handle(self, *args, **options) -> None:
        email = options["email"]
        name = options["name"]

        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(
                f"El usuario con correo {email} ya existe; se omite."
            ))
            return

        user = User.objects.create_user(email=email, first_name=name)

        stages = Stage.objects.all()
        StageUser.objects.bulk_create(
            [StageUser(user=user, stage=stage) for stage in stages]
        )
        if not stages:
            self.stdout.write(self.style.WARNING(
                "No hay fases cargadas: corre load_stages y luego "
                "sync_stageusers para crear los StageUser."
            ))

        self.stdout.write(self.style.SUCCESS(
            f"Usuario «{name}» preregistrado con éxito ({email})."
        ))
