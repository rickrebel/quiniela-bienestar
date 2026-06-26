"""Importa la quiniela original (sanginiela) desde su BD pre-fork.

Esta BD es el fork "bienestar"; sus datos ya cuelgan de la quiniela
``bienestar``. La BD original vive aparte (``POSTGRES_DB_ORIGINAL``) con el
esquema **pre-fork**: tiene ``GROUP_STAGE`` y carece de ``Window``,
``Prediction.quiniela``/``advancing_team``/``base_points``/``points``. No se
puede leer con el ORM actual, así que se consulta con **SQL crudo** vía
psycopg2 (mismas credenciales ``POSTGRES_*``).

Qué hace, enganchado a la quiniela slug ``sanginiela`` (ya creada por
``load_rules``; sus ``Window`` ya existen por ``seed_windows``):

- **Usuarios = merge por email.** Si el email ya existe local, no se duplica:
  solo se le añade ``UserQuiniela(sanginiela)``; el usuario local manda en
  nombre/contraseña/is_active. Si no existe, se crea con el hash de
  contraseña, ``first_name`` e ``is_active`` del original.
- **Pronósticos crudos.** Se remapea cada predicción por ``Match.of_number``
  (clave canónica 1..104 estable en ambas BD; las PK de ``Match`` no
  coinciden). ``advancing_team`` queda nulo (no existe en el original) y no se
  traen puntos congelados: corre ``recompute_scores`` al final.
- **Envíos.** Cada ``StageUser`` original se mapea a su ``Window`` de
  sanginiela; ``GROUP_STAGE`` colapsa en la ventana "Grupos".

Idempotente y re-ejecutable. Con ``--dry-run`` solo reporta (conteos y solape
de emails) sin escribir nada.
"""

import os

import psycopg2
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from pool.models import (
    Prediction, Quiniela, User, UserQuiniela, Window, WindowUser,
)
from tournament.models import Match

QUINIELA_SLUG = "sanginiela"
# Clave de la fase de grupos en la BD original (pre-fork). En el esquema
# actual desaparece y su envío único se mapea a la ventana "Grupos".
ORIGINAL_GROUP_KEY = "GROUP_STAGE"


class Command(BaseCommand):
    help = "Importa usuarios, pronósticos y envíos de la BD original."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Solo reporta conteos y solape de emails; no escribe.")

    def handle(self, *args, **options) -> None:
        dry = options["dry_run"]
        quiniela = self._get_quiniela()
        window_by_key = self._window_by_stage_key(quiniela)
        users, stage_users, predictions = self._read_original()

        local_emails = set(
            User.objects.values_list("email", flat=True))
        match_by_ofn = dict(
            Match.objects.values_list("of_number", "id"))

        new = [u for u in users if u["email"] not in local_emails]
        merged = [u for u in users if u["email"] in local_emails]
        missing_ofn = sorted({
            p["of_number"] for p in predictions
            if p["of_number"] not in match_by_ofn})

        self._report(
            users, new, merged, predictions, stage_users, missing_ofn)
        if dry:
            self.stdout.write(self.style.WARNING(
                "\n--dry-run: no se escribió nada."))
            return

        with transaction.atomic():
            user_by_orig_id = self._import_users(users, local_emails)
            self._enroll(users, user_by_orig_id, quiniela)
            n_pred = self._import_predictions(
                predictions, user_by_orig_id, match_by_ofn, quiniela)
            n_wu = self._import_window_users(
                stage_users, user_by_orig_id, window_by_key)

        self._verify(quiniela, users)
        self.stdout.write(self.style.SUCCESS(
            f"\nImportado: {len(new)} usuarios nuevos, {len(merged)} "
            f"merge, {n_pred} predicciones, {n_wu} WindowUser."))
        self.stdout.write(
            "Corre ahora: manage.py recompute_scores")

    # --- lectura ---------------------------------------------------------

    def _get_quiniela(self) -> Quiniela:
        try:
            return Quiniela.objects.get(slug=QUINIELA_SLUG)
        except Quiniela.DoesNotExist:
            raise CommandError(
                f"Quiniela '{QUINIELA_SLUG}' no existe; corre load_rules.")

    def _window_by_stage_key(self, quiniela: Quiniela) -> dict[str, Window]:
        """Mapa clave de fase → ``Window`` de la quiniela.

        Añade la clave pre-fork ``GROUP_STAGE`` apuntando a la misma
        ventana que envuelve ``SUBGROUP_1`` (la "Grupos" concentrada).
        """
        by_key: dict[str, Window] = {}
        for window in quiniela.windows.prefetch_related("stages"):
            for stage in window.stages.all():
                by_key[stage.key] = window
        group = by_key.get("SUBGROUP_1")
        if group is None:
            raise CommandError(
                f"La quiniela '{QUINIELA_SLUG}' no tiene ventana de grupos; "
                f"corre seed_windows.")
        by_key[ORIGINAL_GROUP_KEY] = group
        return by_key

    def _read_original(self) -> tuple[list, list, list]:
        """Lee usuarios, estados de fase y pronósticos del original.

        Une ``pool_prediction``/``pool_stageuser`` con ``tournament_match``/
        ``tournament_stage`` para devolver ya la ``of_number`` y la ``key``
        (las PK de Match/Stage no coinciden entre BD).
        """
        name = os.environ.get("POSTGRES_DB_ORIGINAL")
        if not name:
            raise CommandError("Falta POSTGRES_DB_ORIGINAL en el entorno.")
        conn = psycopg2.connect(
            dbname=name,
            user=os.environ.get("POSTGRES_USER"),
            password=os.environ.get("POSTGRES_PASSWORD"),
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=os.environ.get("POSTGRES_PORT", "5432"),
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, email, password, first_name, is_active, "
                    "authorized FROM pool_user")
                users = [
                    {"id": r[0], "email": r[1], "password": r[2],
                     "first_name": r[3], "is_active": r[4],
                     "authorized": r[5]}
                    for r in cur.fetchall()
                ]
                cur.execute(
                    "SELECT su.user_id, s.key, su.sent_at "
                    "FROM pool_stageuser su "
                    "JOIN tournament_stage s ON s.id = su.stage_id")
                stage_users = [
                    {"user_id": r[0], "key": r[1], "sent_at": r[2]}
                    for r in cur.fetchall()
                ]
                cur.execute(
                    "SELECT p.user_id, m.of_number, p.home_goals, "
                    "p.away_goals, p.date FROM pool_prediction p "
                    "JOIN tournament_match m ON m.id = p.match_id")
                predictions = [
                    {"user_id": r[0], "of_number": r[1], "home_goals": r[2],
                     "away_goals": r[3], "date": r[4]}
                    for r in cur.fetchall()
                ]
        finally:
            conn.close()
        return users, stage_users, predictions

    # --- escritura -------------------------------------------------------

    def _import_users(
        self, users: list, local_emails: set
    ) -> dict[int, User]:
        """Crea los usuarios nuevos y mapea cada id original → User local.

        El email ya presente local no se toca (manda lo local); el nuevo se
        crea con el hash de contraseña tal cual para que entre con su
        contraseña actual.
        """
        local_by_email = {
            u.email: u for u in User.objects.filter(
                email__in=[u["email"] for u in users])}
        by_orig_id: dict[int, User] = {}
        for u in users:
            existing = local_by_email.get(u["email"])
            if existing is None:
                existing = User(
                    email=u["email"], first_name=u["first_name"],
                    is_active=u["is_active"], password=u["password"])
                existing.save()
                local_by_email[u["email"]] = existing
            by_orig_id[u["id"]] = existing
        return by_orig_id

    def _enroll(
        self, users: list, by_orig_id: dict[int, User], quiniela: Quiniela
    ) -> None:
        """Crea ``UserQuiniela(sanginiela)`` por cada usuario (idempotente).

        ``authorized`` se copia del original solo al crear la membresía; un
        ajuste manual local posterior no se pisa en re-ejecuciones.
        """
        authorized_by_orig = {u["id"]: u["authorized"] for u in users}
        for orig_id, user in by_orig_id.items():
            UserQuiniela.objects.get_or_create(
                user=user, quiniela=quiniela,
                defaults={"authorized": authorized_by_orig[orig_id]})

    def _import_predictions(
        self, predictions: list, by_orig_id: dict[int, User],
        match_by_ofn: dict[int, int], quiniela: Quiniela
    ) -> int:
        """Importa pronósticos crudos remapeados por ``of_number``."""
        count = 0
        for p in predictions:
            match_id = match_by_ofn.get(p["of_number"])
            if match_id is None:
                continue
            Prediction.objects.update_or_create(
                user=by_orig_id[p["user_id"]], match_id=match_id,
                quiniela=quiniela,
                defaults={
                    "home_goals": p["home_goals"],
                    "away_goals": p["away_goals"],
                    "date": p["date"],
                    "advancing_team": None,
                },
            )
            count += 1
        return count

    def _import_window_users(
        self, stage_users: list, by_orig_id: dict[int, User],
        window_by_key: dict[str, Window]
    ) -> int:
        """Crea ``WindowUser`` desde los ``StageUser`` del original.

        Varias fases en una misma ventana (la "Grupos" concentrada) se
        colapsan conservando el ``sent_at`` más reciente.
        """
        count = 0
        for su in stage_users:
            window = window_by_key.get(su["key"])
            if window is None:
                continue
            obj, created = WindowUser.objects.get_or_create(
                user=by_orig_id[su["user_id"]], window=window,
                defaults={"sent_at": su["sent_at"]})
            count += created
            sent = su["sent_at"]
            if (not created and sent is not None
                    and (obj.sent_at is None or sent > obj.sent_at)):
                obj.sent_at = sent
                obj.save(update_fields=["sent_at"])
        return count

    # --- reporte / verificación -----------------------------------------

    def _report(
        self, users, new, merged, predictions, stage_users, missing_ofn
    ) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(
            "Plan de importación (original → sanginiela):"))
        self.stdout.write(f"  Usuarios originales: {len(users)}")
        self.stdout.write(f"    nuevos (crear):    {len(new)}")
        self.stdout.write(f"    merge por email:   {len(merged)}")
        self.stdout.write(f"  Pronósticos:         {len(predictions)}")
        self.stdout.write(f"  StageUser (envíos):  {len(stage_users)}")
        self.stdout.write(
            f"  of_number sin match local: {len(missing_ofn)} "
            f"{missing_ofn if missing_ofn else ''}")
        if merged:
            self.stdout.write("  Emails en merge:")
            for u in sorted(m["email"] for m in merged):
                self.stdout.write(f"    · {u}")

    def _verify(self, quiniela: Quiniela, users: list) -> None:
        """Verifica las dos invariantes del enganche tras escribir."""
        orphan = Prediction.objects.filter(
            quiniela=quiniela, match__isnull=True).count()
        member_emails = set(
            UserQuiniela.objects.filter(quiniela=quiniela).values_list(
                "user__email", flat=True))
        missing = {u["email"] for u in users} - member_emails
        self.stdout.write(self.style.MIGRATE_HEADING("\nVerificación:"))
        self.stdout.write(
            f"  Prediction sanginiela sin match: {orphan} "
            f"{'OK' if orphan == 0 else 'FALLA'}")
        self.stdout.write(
            f"  Emails del original sin UserQuiniela: {len(missing)} "
            f"{'OK' if not missing else sorted(missing)}")