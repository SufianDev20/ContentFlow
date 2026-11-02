from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


# Register your models here.
@admin.register(User)
class UserAdmin(UserAdmin):
    ordering = ["email"]
    list_display = ["email", "full_name", "is_active"]
    fieldsets = UserAdmin.fieldsets + ((None, {"fields": ("full_name",)}),)
