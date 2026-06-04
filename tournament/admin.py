from django.contrib import admin

from .models import Match, Stadium, Stage, Team


@admin.register(Stadium)
class StadiumAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "country", "utc_offset", "capacity")
    list_filter = ("country",)
    search_fields = ("name", "city")


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "key",
        "name",
        "short_name",
        "color",
        "opens_at",
        "send_deadline",
    )
    list_editable = ("opens_at", "send_deadline")
    ordering = ("order",)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = (
        "name_es",
        "name",
        "fifa_code",
        "group_name",
        "confederation",
    )
    list_filter = ("group_name", "confederation")
    search_fields = ("name", "name_es", "fifa_code")


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        "of_number",
        "datetime",
        "stage",
        "home_team",
        "away_team",
        "status",
    )
    list_filter = ("stage", "status", "stadium")
    search_fields = ("home_placeholder", "away_placeholder")
    ordering = ("of_number",)
