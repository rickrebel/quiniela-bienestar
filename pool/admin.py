from django.contrib import admin

from .models import Prediction, StageUser, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Admin simple de usuarios.

    No usa el ``UserAdmin`` clásico de Django para evitar el manejo del
    campo ``password`` inusable de los usuarios preregistrados.
    """

    list_display = (
        "email",
        "username",
        "first_name",
        "is_active",
        "did_pay",
    )
    search_fields = ("email",)


@admin.register(StageUser)
class StageUserAdmin(admin.ModelAdmin):
    list_display = ("user", "stage", "sent_at", "closed_at")
    list_filter = ("stage",)


admin.site.register(Prediction)
