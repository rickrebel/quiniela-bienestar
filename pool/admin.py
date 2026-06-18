from django.contrib import admin

from .models import Prediction, StageUser, User
from django.contrib.auth.admin import UserAdmin

@admin.register(StageUser)
class StageUserAdmin(admin.ModelAdmin):
    list_display = ("user", "stage", "sent_at")
    list_filter = ("stage",)


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "home_team_name",
        "away_team_name",
        "home_goals",
        "away_goals",
    )
    list_editable = ("home_goals", "away_goals")
    list_filter = ("user", "match__stage")
    search_fields = (
        "match__home_team__name_es",
        "match__away_team__name_es",
        "user__first_name",
        "user__email",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related(
            "user", "match__home_team", "match__away_team")

    @admin.display(description="Local", ordering="match__home_team__name")
    def home_team_name(self, obj: Prediction) -> str:
        return obj.match.home_team.name_es if obj.match.home_team else "—"

    @admin.display(description="Visitante", ordering="match__away_team__name")
    def away_team_name(self, obj: Prediction) -> str:
        return obj.match.away_team.name_es if obj.match.away_team else "—"


class StageUserInline(admin.StackedInline):
    model = StageUser
    extra = 0
    can_delete = False
    verbose_name_plural = "Etapas del usuario"


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    # add_fieldsets = UserAdmin.add_fieldsets + (
    #     (None, {'fields': ('phone', 'full_editor')}),
    # )
    fieldsets = (
        (None, {'fields': ('username',)}),
        ('Información personal', {'fields': (
            'first_name', 'last_name', 'email')}),
        ('Permisos de quiniela', {'fields': ('can_record_results',)}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    list_display = (
        "email",
        "username",
        "first_name",
        "is_active",
        "authorized",
        "can_record_results",
    )
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-is_active', 'email')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    inlines = [StageUserInline]
