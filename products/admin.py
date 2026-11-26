from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import ExcelDashboard, ExcelDashboardImage, WordPressTheme, WordPressThemeImage


class WordPressThemeImageInline(admin.TabularInline):
    model = WordPressThemeImage
    extra = 1
    fields = ('image', 'caption', 'display_order', 'is_active')
    verbose_name = 'Preview screenshot'
    verbose_name_plural = 'Preview screenshots'


class ExcelDashboardImageInline(admin.TabularInline):
    model = ExcelDashboardImage
    extra = 1
    fields = ('image', 'caption', 'display_order', 'is_active')
    verbose_name = 'Preview screenshot'
    verbose_name_plural = 'Preview screenshots'


@admin.register(WordPressTheme)
class WordPressThemeAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'theme_version',
        'display_price_label',
        'is_featured',
        'is_active',
        'display_order',
    )
    list_display_links = ('title',)
    list_editable = ('is_featured', 'is_active', 'display_order')
    list_filter = ('is_active', 'is_featured', 'page_builder', 'requires_license_key')
    search_fields = ('title', 'slug', 'short_description', 'description', 'theme_version')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('secure_download_link', 'preview_count', 'created_at', 'updated_at')
    inlines = (WordPressThemeImageInline,)
    fieldsets = (
        ('Theme details', {
            'fields': ('title', 'slug', 'short_description', 'description'),
        }),
        ('Theme metadata', {
            'fields': (
                'theme_version',
                'minimum_wordpress_version',
                'page_builder',
                'requires_license_key',
            ),
        }),
        ('Media', {
            'fields': ('thumbnail', 'preview_count'),
        }),
        ('Pricing', {
            'fields': ('price', 'sale_price'),
        }),
        ('Package and preview', {
            'fields': ('download_file', 'secure_download_link', 'demo_url'),
        }),
        ('Publishing', {
            'fields': ('is_active', 'is_featured', 'display_order', 'created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Package access')
    def secure_download_link(self, obj):
        if not obj or not obj.pk or not obj.download_file:
            return '—'
        url = reverse('products:download_wordpress', args=[obj.pk])
        return format_html('<a href="{}">Open guarded download</a>', url)

    @admin.display(description='Preview screenshots')
    def preview_count(self, obj):
        return obj.preview_count if obj and obj.pk else 0


@admin.register(ExcelDashboard)
class ExcelDashboardAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'workbook_version',
        'display_price_label',
        'is_featured',
        'is_active',
        'display_order',
    )
    list_display_links = ('title',)
    list_editable = ('is_featured', 'is_active', 'display_order')
    list_filter = ('is_active', 'is_featured', 'has_macros', 'excel_compatibility')
    search_fields = ('title', 'slug', 'short_description', 'description', 'workbook_version')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('secure_download_link', 'preview_count', 'created_at', 'updated_at')
    inlines = (ExcelDashboardImageInline,)
    fieldsets = (
        ('Dashboard details', {
            'fields': ('title', 'slug', 'short_description', 'description'),
        }),
        ('Workbook metadata', {
            'fields': (
                'workbook_version',
                'sheet_count',
                'excel_compatibility',
                'has_macros',
            ),
        }),
        ('Media', {
            'fields': ('thumbnail', 'preview_count'),
        }),
        ('Pricing', {
            'fields': ('price', 'sale_price'),
        }),
        ('Package and preview', {
            'fields': ('download_file', 'secure_download_link', 'demo_url'),
        }),
        ('Publishing', {
            'fields': ('is_active', 'is_featured', 'display_order', 'created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Package access')
    def secure_download_link(self, obj):
        if not obj or not obj.pk or not obj.download_file:
            return '—'
        url = reverse('products:download_excel', args=[obj.pk])
        return format_html('<a href="{}">Open guarded download</a>', url)

    @admin.display(description='Preview screenshots')
    def preview_count(self, obj):
        return obj.preview_count if obj and obj.pk else 0
