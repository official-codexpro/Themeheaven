from django.utils.safestring import mark_safe

FALLBACK_ICON_NAME = 'layout-grid'

APP_ICON_NAMES = {
    'auth': 'shield',
    'core': 'settings',
    'products': 'package',
    'growth_center': 'trending-up',
}

MODEL_ICON_NAMES = {
    ('auth', 'group'): 'users',
    ('auth', 'user'): 'user',
    ('core', 'errorpagesettings'): 'route',
    ('core', 'appearancesettings'): 'palette',
    ('core', 'systemsettings'): 'sliders',
    ('core', 'footersettings'): 'panel-bottom',
    ('products', 'exceldashboard'): 'excel',
    ('products', 'wordpresstheme'): 'wordpress',
    ('growth_center', 'analytics'): 'bar-chart',
    ('growth_center', 'seosettings'): 'search',
}

_LUCIDE_PATHS = {
    'settings': (
        '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    'shield': '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    'package': (
        '<path d="m7.5 4.27 9 5.15"/>'
        '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>'
        '<path d="m3.3 7 8.7 5 8.7-5"/>'
        '<path d="M12 22V12"/>'
    ),
    'trending-up': '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    'route': (
        '<circle cx="6" cy="19" r="3"/>'
        '<path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/>'
        '<circle cx="18" cy="5" r="3"/>'
    ),
    'palette': (
        '<path d="M12 22a10 10 0 1 1 10-10c0 4-3 6-6 6h-1a2 2 0 0 1 0-4h1a2 2 0 0 0 0-4h-2a2 2 0 0 0-2 2c0 2-2 4-5 4H6a4 4 0 0 1-4-4 8 8 0 0 1 8-8h2a8 8 0 0 1 8 8"/>'
        '<circle cx="7.5" cy="10.5" r=".6" fill="currentColor" stroke="none"/>'
        '<circle cx="10.5" cy="7.5" r=".6" fill="currentColor" stroke="none"/>'
        '<circle cx="15.5" cy="8.5" r=".6" fill="currentColor" stroke="none"/>'
    ),
    'sliders': (
        '<path d="M21 4h-7M10 4H3M21 12H9M6 12H3M21 20h-9M8 20H3"/>'
        '<path d="M14 2v4M9 10v4M12 18v4"/>'
    ),
    'panel-bottom': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 15h18"/>',
    'bar-chart': (
        '<path d="M3 3v18h18"/>'
        '<rect x="7" y="10" width="3" height="5" rx="1"/>'
        '<rect x="12" y="6" width="3" height="9" rx="1"/>'
        '<rect x="17" y="8" width="3" height="7" rx="1"/>'
    ),
    'search': '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    'users': (
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
        '<circle cx="9" cy="7" r="4"/>'
        '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
        '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
    ),
    'user': '<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v2"/>',
    'layout-grid': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
}

_ICONS = {
    name: mark_safe(
        '<svg class="admin-menu-icon" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">' + path + '</svg>'
    )
    for name, path in _LUCIDE_PATHS.items()
}

_ICONS['excel'] = mark_safe(
    '<svg class="admin-menu-icon admin-menu-icon-brand admin-menu-icon-excel" '
    'viewBox="0 0 24 24" aria-hidden="true">'
    '<rect x="3" y="2.5" width="18" height="19" rx="2.5" fill="#217346"/>'
    '<path d="M6.8 7h4.1l1.1 3 1.1-3h4.1v2l-2.4 5 2.4 5h-4.1l-1.1-3-1.1 3H6.8v-2l2.4-5-2.4-5V7Z" fill="#fff"/>'
    '<path d="M11.4 7h1.2v10h-1.2z" fill="#fff" opacity=".8"/>'
    '</svg>'
)

_ICONS['wordpress'] = mark_safe(
    '<svg class="admin-menu-icon admin-menu-icon-brand admin-menu-icon-wordpress" '
    'viewBox="0 0 24 24" aria-hidden="true">'
    '<path fill="#21759b" d="M21.469 6.825c.84 1.537 1.318 3.3 1.318 5.175 0 3.979-2.156 7.456-5.363 9.325l3.295-9.527c.615-1.54.82-2.771.82-3.864 0-.405-.026-.78-.07-1.11m-7.981.105c.647-.03 1.232-.105 1.232-.105.582-.075.514-.93-.067-.899 0 0-1.755.135-2.88.135-1.064 0-2.85-.15-2.85-.15-.585-.03-.661.855-.075.885 0 0 .54.061 1.125.09l1.68 4.605-2.37 7.08L5.354 6.9c.649-.03 1.234-.1 1.234-.1.585-.075.516-.93-.065-.896 0 0-1.746.138-2.874.138-.2 0-.438-.008-.69-.015C4.911 3.15 8.235 1.215 12 1.215c2.809 0 5.365 1.072 7.286 2.833-.046-.003-.091-.009-.141-.009-1.06 0-1.812.923-1.812 1.914 0 .89.513 1.643 1.06 2.531.411.72.89 1.643.89 2.977 0 .915-.354 1.994-.821 3.479l-1.075 3.585-3.9-11.61.001.014zM12 22.784c-1.059 0-2.081-.153-3.048-.437l3.237-9.406 3.315 9.087c.024.053.05.101.078.149-1.12.393-2.325.609-3.582.609M1.211 12c0-1.564.336-3.05.935-4.39L7.29 21.709C3.694 19.96 1.212 16.271 1.211 12M12 0C5.385 0 0 5.385 0 12s5.385 12 12 12 12-5.385 12-12S18.615 0 12 0"/>'
    '</svg>'
)


def icon_svg(name):
    return _ICONS.get(name, _ICONS[FALLBACK_ICON_NAME])


def apply_admin_icons(apps):
    for app in apps or []:
        app_label = app.get('app_label')
        app_icon_name = APP_ICON_NAMES.get(app_label, FALLBACK_ICON_NAME)
        app['icon_name'] = app_icon_name
        app['icon_svg'] = icon_svg(app_icon_name)

        for model in app.get('models', []):
            model_key = (app_label, str(model.get('object_name', '')).lower())
            model_icon_name = MODEL_ICON_NAMES.get(model_key, FALLBACK_ICON_NAME)
            model['icon_name'] = model_icon_name
            model['icon_svg'] = icon_svg(model_icon_name)
    return apps
