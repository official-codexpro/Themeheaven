from django.apps import AppConfig

from .admin_icons import apply_admin_icons


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from django.contrib import admin
        from django.contrib.admin.sites import AdminSite
        from django.db.utils import OperationalError, ProgrammingError
        from django.urls import NoReverseMatch, path, reverse

        if getattr(admin.site, '_themehaven_system_settings', False):
            return
        admin.site._themehaven_system_settings = True

        original_each_context = AdminSite.each_context
        original_get_app_list = AdminSite.get_app_list
        original_get_urls = AdminSite.get_urls

        def settings_model_entry():
            return {
                'name': 'Settings',
                'object_name': 'systemsettings',
                'admin_url': reverse('admin:system-settings-index'),
                'add_url': None,
                'view_only': True,
            }

        def growth_center_entry():
            return {
                'name': 'Marketing Analytics',
                'object_name': 'analytics',
                'admin_url': reverse('admin:growth-center-analytics'),
                'add_url': None,
                'view_only': True,
            }

        def seo_settings_entry():
            return {
                'name': 'SEO Settings',
                'object_name': 'seosettings',
                'admin_url': reverse('admin:growth-center-seo-settings'),
                'add_url': None,
                'view_only': True,
            }

        def page_seo_entry():
            return {
                'name': 'Page SEO',
                'object_name': 'pageseo',
                'admin_url': reverse('admin:growth-center-page-seo'),
                'add_url': None,
                'view_only': True,
            }

        def add_growth_center(apps, user):
            if not getattr(user, 'is_staff', False):
                return
            try:
                entries = [growth_center_entry(), seo_settings_entry(), page_seo_entry()]
            except NoReverseMatch:
                return
            for app in apps:
                if app.get('app_label') == 'growth_center':
                    for entry in entries:
                        if not any(model['admin_url'] == entry['admin_url'] for model in app['models']):
                            app['models'].append(entry)
                    return
            apps.append({
                'name': 'GROWTH CENTER',
                'app_label': 'growth_center',
                'app_url': entries[0]['admin_url'],
                'has_module_permission': True,
                'models': entries,
            })

        def normalize_core_menu(apps):
            order = ['errorpagesettings', 'appearancesettings', 'systemsettings', 'footersettings']
            for app in apps:
                if app.get('app_label') != 'core':
                    continue
                for model in app['models']:
                    if model.get('object_name') == 'ErrorPageSettings':
                        model['name'] = 'Redirection Settings'
                    elif model.get('object_name') == 'AppearanceSettings':
                        model['name'] = 'Appearance Settings'
                app['models'].sort(
                    key=lambda model: order.index(model['object_name'].lower())
                    if model['object_name'].lower() in order else len(order)
                )

        def branded_each_context(self, request):
            context = original_each_context(self, request)
            try:
                from .system_settings import activate_locale

                site_settings = activate_locale()
                self.site_header = site_settings.admin_header or site_settings.admin_site_name
                self.site_title = site_settings.admin_browser_title or site_settings.admin_site_name
                self.index_title = site_settings.admin_site_name
                self.site_url = site_settings.site_base_url or '/'

                context.update({
                    'site_header': self.site_header,
                    'site_title': self.site_title,
                    'index_title': self.index_title,
                    'site_url': self.site_url,
                    'system_settings': site_settings,
                })

                normalize_core_menu(context.get('available_apps', []))
                add_growth_center(context.get('available_apps', []), request.user)
                apply_admin_icons(context.get('available_apps', []))

                if not getattr(request.user, 'is_superuser', False):
                    return context

                for app in context.get('available_apps', []):
                    if app.get('app_label') == 'core':
                        entry = settings_model_entry()
                        if not any(model['admin_url'] == entry['admin_url'] for model in app['models']):
                            app['models'].insert(0, entry)
                        break
                normalize_core_menu(context.get('available_apps', []))
                apply_admin_icons(context.get('available_apps', []))
            except (NoReverseMatch, OperationalError, ProgrammingError):
                pass
            return context

        def system_settings_get_app_list(self, request, app_label=None):
            apps = original_get_app_list(self, request, app_label)
            normalize_core_menu(apps)
            add_growth_center(apps, request.user)
            apply_admin_icons(apps)
            if not getattr(request.user, 'is_superuser', False):
                return apps
            try:
                entry = settings_model_entry()
                for app in apps:
                    if app.get('app_label') == 'core':
                        if not any(model['admin_url'] == entry['admin_url'] for model in app['models']):
                            app['models'].insert(0, entry)
                        break
                normalize_core_menu(apps)
                apply_admin_icons(apps)
            except NoReverseMatch:
                pass
            return apps

        def system_settings_get_urls(self):
            from growth_center.views import analytics_dashboard, page_seo_dashboard, page_seo_editor, seo_settings_dashboard

            from .settings_views import settings_category, settings_index

            custom_urls = [
                path('settings/', self.admin_view(settings_index), name='system-settings-index'),
                path('settings/<slug:slug>/', self.admin_view(settings_category), name='system-settings-category'),
                path(
                    'growth-center/analytics/',
                    self.admin_view(analytics_dashboard),
                    name='growth-center-analytics',
                ),
                    path(
                        'growth-center/seo-settings/',
                        self.admin_view(seo_settings_dashboard),
                        name='growth-center-seo-settings',
                    ),
                    path(
                        'growth-center/page-seo/',
                        self.admin_view(page_seo_dashboard),
                        name='growth-center-page-seo',
                    ),
                    path(
                        'growth-center/page-seo/<path:page_key>/',
                        self.admin_view(page_seo_editor),
                        name='growth-center-page-seo-edit',
                    ),
                ]
            return custom_urls + original_get_urls(self)

        AdminSite.each_context = branded_each_context
        AdminSite.get_app_list = system_settings_get_app_list
        AdminSite.get_urls = system_settings_get_urls

        admin.site.site_header = 'themehaven.in'
        admin.site.site_title = 'themehaven.in'
        admin.site.index_title = 'themehaven.in'
