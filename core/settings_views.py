from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import CATEGORIES
from .system_settings import (
    activate_locale,
    get_system_settings,
    log_settings_change,
    restart_notice,
    security_warnings,
)


def _require_superuser(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied


def _context(request, title):
    context = admin.site.each_context(request)
    context['title'] = title
    return context


def settings_index(request):
    _require_superuser(request)
    instance = activate_locale()
    context = _context(request, 'Settings')
    context['categories'] = [
        {'slug': slug, 'name': item['name'], 'description': item['description']}
        for slug, item in CATEGORIES.items()
    ]
    context['warnings'] = security_warnings(instance)
    return render(request, 'admin/settings/index.html', context)


def settings_category(request, slug):
    _require_superuser(request)
    category = CATEGORIES.get(slug)
    if category is None:
        raise Http404('Unknown settings category.')

    instance = activate_locale()
    form_class = category['form']
    if request.method == 'POST' and form_class is not None:
        form = form_class(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            before = {name: getattr(instance, name) for name in form.cleaned_data}
            form.save()
            changes = [
                f"{name}: {before.get(name)!r} → {form.cleaned_data[name]!r}"
                for name in form.changed_data
            ]
            if changes:
                log_settings_change(request, category['name'], changes)
            messages.success(request, f'{category["name"]} saved successfully.')
            return redirect(reverse('admin:system-settings-category', args=[slug]))
    else:
        form = form_class(instance=instance) if form_class is not None else None

    context = _context(request, category['name'])
    context['category'] = {'slug': slug, 'name': category['name'], 'description': category['description']}
    context['form'] = form
    context['info_rows'] = category['info'](instance) if category['info'] else []
    context['warnings'] = security_warnings(instance) if slug in {'general', 'security'} else []
    context['restart_issues'] = restart_notice(instance) if slug in {'general', 'security', 'sessions'} else []
    context['index_url'] = reverse('admin:system-settings-index')
    return render(request, 'admin/settings/category.html', context)
