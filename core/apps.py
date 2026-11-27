from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from django.contrib import admin

        admin.site.site_header = 'themehaven.in'
        admin.site.site_title = 'themehaven.in'
        admin.site.index_title = 'themehaven.in'
