from django.contrib import admin

from .models import (
    Prediction, Quiniela, QuinielaRule, Rule, User,
    UserQuiniela, Window, WindowUser)
from django.contrib.auth.admin import UserAdmin


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "short_name", "icon", "order")
    ordering = ("order",)
    search_fields = ("code", "name", "short_name")


class QuinielaRuleInline(admin.TabularInline):
    model = QuinielaRule
    extra = 0
    autocomplete_fields = ("rule",)


@admin.register(Quiniela)
class QuinielaAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "theme", "registration_deadline")
    list_editable = ("theme", "registration_deadline")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")
    inlines = [QuinielaRuleInline]


@admin.register(Window)
class WindowAdmin(admin.ModelAdmin):
    list_display = (
        "quiniela", "order", "window_name", "multiplier",
        "third_place_multiplier", "opens_at", "send_deadline")
    list_filter = ("quiniela",)
    ordering = ("quiniela", "order")
    filter_horizontal = ("stages",)

    @admin.display(description="Nombre")
    def window_name(self, obj: Window) -> str:
        return obj.resolved_name()


@admin.register(UserQuiniela)
class UserQuinielaAdmin(admin.ModelAdmin):
    list_display = ("user", "quiniela", "authorized", "joined_at")
    list_editable = ("authorized",)
    list_filter = ("quiniela", "authorized")
    search_fields = ("user__email", "user__first_name")


@admin.register(WindowUser)
class WindowUserAdmin(admin.ModelAdmin):
    list_display = ("user", "window", "sent_at")
    list_filter = ("window__quiniela", "window__stages")


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


class UserQuinielaInline(admin.TabularInline):
    model = UserQuiniela
    extra = 0
    verbose_name_plural = "Quinielas del usuario"


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
        "can_record_results",
    )
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-is_active', 'email')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    inlines = [UserQuinielaInline]
