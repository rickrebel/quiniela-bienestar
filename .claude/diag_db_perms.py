"""Diagnóstico desechable: privilegios de user_yeeko y estado previo."""
from django.db import connection
from pool.models import StageUser, User
from pool.services.aggregation import VIRTUAL_EMAIL

cur = connection.cursor()
cur.execute(
    "SELECT has_schema_privilege('user_yeeko', 'public', 'USAGE'), "
    "rolsuper FROM pg_roles WHERE rolname = current_user"
)
usage, is_super = cur.fetchone()
print(f"user_yeeko USAGE en public: {usage}")
print(f"current_user es superusuario: {is_super}")

virtual = User.objects.filter(email=VIRTUAL_EMAIL).first()
print(f"usuario virtual en el clon: {virtual!r}")
if virtual:
    n = StageUser.objects.filter(user=virtual).count()
    print(f"  is_virtual={virtual.is_virtual} · StageUsers: {n}")
