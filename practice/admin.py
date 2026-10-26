from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Audit, Profile, Question


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fields = ['must_change_password']


admin.site.unregister(User)


@admin.register(User)
class ManagedUserAdmin(UserAdmin):
    inlines = [ProfileInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        profile, _ = Profile.objects.get_or_create(user=obj)
        profile.session_version += 1
        profile.save()


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['source_number', 'category', 'subcategory', 'kind', 'stem_preview', 'enabled', 'source_page']
    list_filter = ['category', 'kind', 'enabled', 'subcategory']
    search_fields = ['stem', 'source_number', 'source_file']
    readonly_fields = ['uid', 'raw_text', 'source_file', 'source_number', 'source_page', 'updated_at']
    list_per_page = 30

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        # New records enter through the validated source importer.
        return False

    def has_delete_permission(self, request, obj=None):
        # Disabling retains references and all existing practice snapshots.
        return False

    @admin.display(description='题干')
    def stem_preview(self, obj):
        return obj.stem[:70]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        Audit.objects.create(actor=request.user, action='修改题库', target=obj.uid)


@admin.register(Audit)
class AuditAdmin(admin.ModelAdmin):
    list_display = ['at', 'actor', 'action', 'target']
    readonly_fields = ['at', 'actor', 'action', 'target']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.site_header = '长江财险 · 题库管理'
admin.site.site_title = '十五周年题库'
admin.site.index_title = '题目维护与复核'
