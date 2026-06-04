from django.contrib import admin

from .models import Prediction, StageUser, User
from django.contrib.auth.admin import UserAdmin

@admin.register(StageUser)
class StageUserAdmin(admin.ModelAdmin):
    list_display = ("user", "stage", "sent_at")
    list_filter = ("stage",)


admin.site.register(Prediction)


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
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    list_display = (
        "email",
        "username",
        "first_name",
        "is_active",
        "authorized",
    )
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-is_active', 'email')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    inlines = [StageUserInline]
