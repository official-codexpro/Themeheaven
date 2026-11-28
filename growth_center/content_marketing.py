from calendar import monthrange
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone

from .content_constants import (
    CONTENT_PRIORITIES,
    CONTENT_SECTIONS,
    CONTENT_STATUSES,
    CONTENT_TYPES,
    PRIORITY_ORDER,
    SEO_CHECKLIST,
)
from .content_forms import ContentCategoryForm, ContentFilterForm, ContentTagForm, RANGE_CHOICES
from .models import AnalyticsSession, ContentBrief, ContentIdea, ContentRefreshTask, ContentTemplate, MarketingContent, PageView
from .services import _aware_midnight, _chart_series, _comparison, _metrics, _parse_date, _traffic_sources

PAGE_SIZE = 15


def _request_context(request):
    form = ContentFilterForm(request.GET)
    data = form.cleaned_data if form.is_valid() else {}
    defaults = {
        'section': 'overview',
        'status': '',
        'content_type': '',
        'category': None,
        'tag': None,
        'priority': '',
        'query': '',
        'sort': 'date',
        'direction': 'desc',
        'view': 'month',
        'date': timezone.localdate(),
        'date_range': '30d',
        'refresh_status': '',
        'idea_source': '',
    }
    for key, value in defaults.items():
        if key not in data or data[key] in (None, ''):
            data[key] = value
    data['form'] = form
    return data


def _date_range(filters):
    today = timezone.localdate()
    key = filters['date_range']
    if key not in dict(RANGE_CHOICES):
        key = '30d'
    if key == '7d':
        start = today - timedelta(days=6)
        end = today
    elif key == '90d':
        start = today - timedelta(days=89)
        end = today
    elif key == 'all':
        start = today - timedelta(days=365)
        end = today
    else:
        start = today - timedelta(days=29)
        end = today
    span = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=span - 1)
    return {
        'start': start,
        'end': end,
        'previous_start': previous_start,
        'previous_end': previous_end,
        'start_at': _aware_midnight(start),
        'end_at': _aware_midnight(end + timedelta(days=1)),
        'previous_start_at': _aware_midnight(previous_start),
        'previous_end_at': _aware_midnight(previous_end + timedelta(days=1)),
        'key': key,
        'label': dict(RANGE_CHOICES)[key],
    }


def _content_path(item):
    value = item.publication_url or item.canonical_url or ''
    path = urlsplit(value).path if value else ''
    return path.rstrip('/') or '/'


def _content_keys(queryset):
    return [item.content_key for item in queryset if item.content_key]


def _match_content_sessions(items, start_at, end_at):
    paths = sorted({_content_path(item) for item in items})
    keys = _content_keys(items)
    condition = Q()
    if paths:
        condition |= Q(landing_path__in=paths)
    if keys:
        condition |= Q(utm_content__in=keys)
    return AnalyticsSession.objects.filter(condition, started_at__gte=start_at, started_at__lt=end_at)


def _match_content_views(items, start_at, end_at):
    paths = sorted({_content_path(item) for item in items})
    if not paths:
        return PageView.objects.none()
    return PageView.objects.filter(path__in=paths, viewed_at__gte=start_at, viewed_at__lt=end_at)


def _content_query(queryset, filters):
    query = filters.get('query', '').strip()
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(content_key__icontains=query)
            | Q(description__icontains=query)
            | Q(topic__icontains=query)
            | Q(primary_keyword__icontains=query)
            | Q(secondary_keywords__icontains=query)
            | Q(slug__icontains=query)
        )
    if filters.get('status'):
        queryset = queryset.filter(status=filters['status'])
    if filters.get('content_type'):
        queryset = queryset.filter(content_type=filters['content_type'])
    if filters.get('category'):
        queryset = queryset.filter(category=filters['category'])
    if filters.get('tag'):
        queryset = queryset.filter(tags=filters['tag'])
    if filters.get('priority'):
        queryset = queryset.filter(priority=filters['priority'])
    return queryset.distinct()


def _sorted_content(queryset, filters):
    sort = filters.get('sort', 'date')
    descending = filters.get('direction', 'desc') == 'desc'
    if sort == 'created':
        field = '-created_at' if descending else 'created_at'
        return list(queryset.order_by(field, 'title'))
    if sort == 'title':
        field = '-title' if descending else 'title'
        return list(queryset.order_by(field))
    if sort == 'status':
        field = '-status' if descending else 'status'
        return list(queryset.order_by(field, '-created_at'))
    if sort == 'priority':
        items = list(queryset)
        return sorted(items, key=lambda item: PRIORITY_ORDER.get(item.priority, 0), reverse=descending)
    if sort == 'date':
        field = '-target_publication_date' if descending else 'target_publication_date'
        return list(queryset.order_by(field, '-created_at'))
    return list(queryset.order_by('-created_at'))


def _paginate(request, items):
    paginator = Paginator(items, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return {
        'page': page,
        'paginator': paginator,
        'querystring': params.urlencode(),
    }


def _calendar_entries(items, anchor, view):
    if view == 'week':
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
    elif view == 'day':
        start = end = anchor
    else:
        start = anchor.replace(day=1)
        last_day = monthrange(anchor.year, anchor.month)[1]
        end = anchor.replace(day=last_day)

    by_day = {}
    for item in items:
        day = item.published_at.date() if item.status == 'Published' and item.published_at else item.target_publication_date
        if not day:
            continue
        by_day.setdefault(day, []).append(item)

    if view == 'list':
        entries = []
        for day in sorted(by_day):
            for item in by_day[day]:
                entries.append({'day': day, 'item': item})
    else:
        entries = [
            {'day': day, 'items': by_day.get(day, [])}
            for day in (start + timedelta(days=offset) for offset in range((end - start).days + 1))
        ]

    if view == 'month':
        grid_start = start - timedelta(days=start.weekday())
        grid_end = end + timedelta(days=(6 - end.weekday()) % 7)
        weeks = []
        current = grid_start
        while current <= grid_end:
            week = []
            for offset in range(7):
                day = current + timedelta(days=offset)
                week.append({
                    'date': day,
                    'in_month': day.month == anchor.month and day.year == anchor.year,
                    'is_today': day == timezone.localdate(),
                    'items': by_day.get(day, []),
                })
            weeks.append(week)
            current += timedelta(days=7)
    else:
        weeks = []

    if view == 'week':
        previous = anchor - timedelta(days=7)
        next_date = anchor + timedelta(days=7)
    elif view == 'day':
        previous = anchor - timedelta(days=1)
        next_date = anchor + timedelta(days=1)
    elif view == 'list':
        previous = anchor - timedelta(days=30)
        next_date = anchor + timedelta(days=30)
    else:
        previous = (start - timedelta(days=1)).replace(day=1)
        next_date = (end + timedelta(days=1)).replace(day=1)

    return {
        'view': view,
        'anchor': anchor,
        'start': start,
        'end': end,
        'entries': entries,
        'weeks': weeks,
        'previous': previous.isoformat(),
        'next': next_date.isoformat(),
        'labels': [day.strftime('%a') for day in (start + timedelta(days=offset) for offset in range(7))],
    }


def _row_for_content(item, current):
    current_sessions = _match_content_sessions([item], current['start_at'], current['end_at']).count()
    current_views = _match_content_views([item], current['start_at'], current['end_at']).count()
    previous_sessions = _match_content_sessions([item], current['previous_start_at'], current['previous_end_at']).count()
    organic = _match_content_sessions([item], current['start_at'], current['end_at']).filter(source_category='Organic Search').count()
    campaign = _match_content_sessions([item], current['start_at'], current['end_at']).exclude(utm_campaign='').count()
    return {
        'id': item.pk,
        'key': item.content_key,
        'title': item.title,
        'content_type': item.content_type,
        'status': item.status,
        'priority': item.priority,
        'author': item.author or item.assigned_to or 'Unassigned',
        'category': item.category.name if item.category_id else 'Uncategorized',
        'target_date': item.target_publication_date,
        'published_at': item.published_at,
        'publication_url': item.publication_url,
        'path': _content_path(item) if item.publication_url or item.canonical_url else '',
        'visits': current_sessions,
        'views': current_views,
        'organic_visits': organic,
        'campaign_visits': campaign,
        'change': _comparison(current_sessions, previous_sessions),
        'overdue': item.is_overdue,
        'word_count': item.word_count,
        'seo_score': _seo_score(item),
    }


def _seo_score(item):
    checks = item.seo_checklist()
    passed = sum(1 for value in checks.values() if value)
    return round((passed / len(checks)) * 100) if checks else 0


def _seo_overview(items):
    published = [item for item in items if item.status == 'Published']
    scored = [(_seo_score(item), item) for item in published]
    missing = {key: 0 for key, _ in SEO_CHECKLIST}
    for item in published:
        checks = item.seo_checklist()
        for key, passed in checks.items():
            if not passed:
                missing[key] += 1
    rows = []
    for key, label in SEO_CHECKLIST:
        rows.append({
            'key': key,
            'label': label,
            'missing': missing.get(key, 0),
            'status': 'ok' if missing.get(key, 0) == 0 else 'attention',
        })
    score = round(sum(value for value, _ in scored) / len(scored)) if scored else 0
    return {
        'score': score,
        'rows': rows,
        'published_count': len(published),
        'needs_review': [item for _, item in sorted(scored)[:5]],
    }


def _attention_rows(items, refresh_tasks):
    rows = []
    today = timezone.localdate()
    for item in items:
        if item.is_overdue:
            rows.append({
                'kind': 'Overdue content',
                'title': item.title,
                'detail': f'Target date was {item.target_publication_date:%b %d}',
                'tone': 'rose',
                'content_id': item.pk,
                'date': item.target_publication_date,
            })
        elif item.status == 'In Review':
            rows.append({
                'kind': 'Review needed',
                'title': item.title,
                'detail': f'{item.content_type} is waiting for review',
                'tone': 'amber',
                'content_id': item.pk,
                'date': item.updated_at.date(),
            })
    for task in refresh_tasks:
        if task.status in {'Pending', 'In Progress'} and task.due_date:
            rows.append({
                'kind': 'Refresh due',
                'title': task.content.title,
                'detail': f'Due {task.due_date:%b %d}',
                'tone': 'purple' if task.due_date >= today else 'rose',
                'content_id': task.content_id,
                'date': task.due_date,
            })
    return sorted(rows, key=lambda row: row['date'] or today)[:12]


def _performance(items, current, previous, request):
    published = [item for item in items if item.status == 'Published']
    current_sessions = _match_content_sessions(published, current['start_at'], current['end_at'])
    previous_sessions = _match_content_sessions(published, current['previous_start_at'], current['previous_end_at'])
    current_views = _match_content_views(published, current['start_at'], current['end_at'])
    previous_views = _match_content_views(published, current['previous_start_at'], current['previous_end_at'])
    metrics = _metrics(current_sessions, current_views)
    previous_metrics = _metrics(previous_sessions, previous_views)

    kpis = [
        {
            'label': 'Content visits',
            'value': metrics['total_sessions'],
            'comparison': _comparison(metrics['total_sessions'], previous_metrics['total_sessions']),
        },
        {
            'label': 'Content page views',
            'value': metrics['page_views'],
            'comparison': _comparison(metrics['page_views'], previous_metrics['page_views']),
        },
        {
            'label': 'Organic visits',
            'value': current_sessions.filter(source_category='Organic Search').count(),
            'comparison': None,
        },
        {
            'label': 'Campaign visits',
            'value': current_sessions.exclude(utm_campaign='').count(),
            'comparison': None,
        },
    ]

    grain = 'daily' if current['key'] == '7d' else 'weekly' if current['key'] == '30d' else 'monthly'
    chart = _chart_series(current_sessions, current_views, current, grain)

    top_rows = []
    declining_rows = []
    for item in published:
        row = _row_for_content(item, current)
        top_rows.append(row)
        if row['change']['value'] is not None and row['change']['value'] < 0 and row['visits'] > 0:
            declining_rows.append(row)
    top_rows.sort(key=lambda row: (-row['visits'], row['title']))
    declining_rows.sort(key=lambda row: (row['change']['value'] or 0, row['visits']))

    campaign_counts = dict(
        current_sessions.exclude(utm_campaign='')
        .values('utm_campaign')
        .annotate(total=Count('id'))
        .values_list('utm_campaign', 'total')
    )
    campaigns = [
        {'name': name, 'visits': total}
        for name, total in sorted(campaign_counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]

    return {
        'kpis': kpis,
        'metrics': metrics,
        'chart': chart,
        'sources': _traffic_sources(current_sessions, metrics['total_sessions']),
        'top': top_rows[:10],
        'declining': declining_rows[:10],
        'campaigns': campaigns[:8],
        'search_console_connected': False,
        'attribution_note': 'Traffic is matched from real Analytics landing paths and UTM content values. Search Console is not connected.',
    }


def _pipeline(items):
    counts = {label: 0 for label, _ in CONTENT_STATUSES}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    rows = []
    for label, _ in CONTENT_STATUSES:
        total = counts.get(label, 0)
        rows.append({
            'label': label,
            'count': total,
            'percent': round((total / len(items)) * 100) if items else 0,
        })
    return rows


def _library_rows(items, current, request):
    rows = [_row_for_content(item, current) for item in items]
    return _paginate(request, rows)


def build_content_context(request, category_form=None, tag_form=None):
    filters = _request_context(request)
    date_range = _date_range(filters)
    anchor = filters['date'] or timezone.localdate()
    section = filters['section']

    items = _content_query(MarketingContent.objects.select_related('category', 'campaign').prefetch_related('tags', 'social_posts'), filters)
    all_items = list(MarketingContent.objects.select_related('category').all())
    ideas_qs = ContentIdea.objects.select_related('category', 'converted_content')
    if filters['query']:
        ideas_qs = ideas_qs.filter(
            Q(title__icontains=filters['query'])
            | Q(description__icontains=filters['query'])
            | Q(topic__icontains=filters['query'])
            | Q(potential_keywords__icontains=filters['query'])
        )
    if filters['idea_source']:
        ideas_qs = ideas_qs.filter(source=filters['idea_source'])
    ideas = list(ideas_qs.order_by('-created_at'))

    briefs_qs = ContentBrief.objects.select_related('content')
    if filters['query']:
        briefs_qs = briefs_qs.filter(
            Q(working_title__icontains=filters['query'])
            | Q(objective__icontains=filters['query'])
            | Q(primary_keyword__icontains=filters['query'])
        )
    briefs = list(briefs_qs.order_by('-created_at'))

    templates = list(ContentTemplate.objects.all())
    refresh_qs = ContentRefreshTask.objects.select_related('content').all()
    if section == 'refresh' and not filters['refresh_status']:
        refresh_qs = refresh_qs.filter(status__in=['Pending', 'In Progress'])
    if filters['refresh_status']:
        refresh_qs = refresh_qs.filter(status=filters['refresh_status'])
    refresh_tasks = list(refresh_qs.order_by('due_date', '-created_at'))

    sorted_items = _sorted_content(items, filters)
    calendar_items = [item for item in all_items if item.target_publication_date or (item.published_at and item.status == 'Published')]
    performance = _performance(all_items, date_range, date_range, request)
    library = _library_rows(sorted_items, date_range, request)

    kpis = [
        {'label': 'Content pieces', 'value': len(all_items), 'detail': f'{sum(1 for item in all_items if item.status == "Published")} published'},
        {'label': 'In production', 'value': sum(1 for item in all_items if item.status in {'Brief Created', 'In Progress', 'Draft'}), 'detail': 'Brief to draft'},
        {'label': 'Ideas captured', 'value': len(ideas), 'detail': f'{sum(1 for idea in ideas if not idea.is_used)} unused'},
        {'label': 'Refresh queue', 'value': sum(1 for task in refresh_tasks if task.status in {'Pending', 'In Progress'}), 'detail': 'Open tasks'},
    ]

    context = {
        'sections': CONTENT_SECTIONS,
        'active_section': section,
        'filter_form': filters['form'],
        'filters': {key: value for key, value in filters.items() if key != 'form'},
        'status_choices': CONTENT_STATUSES,
        'type_choices': CONTENT_TYPES,
        'priority_choices': CONTENT_PRIORITIES,
        'range_choices': RANGE_CHOICES,
        'page_size': PAGE_SIZE,
        'date_range': date_range,
        'kpis': kpis,
        'pipeline': _pipeline(all_items),
        'attention': _attention_rows(all_items, refresh_tasks),
        'seo': _seo_overview(all_items),
        'calendar': _calendar_entries(calendar_items, anchor, filters['view']),
        'library': library,
        'ideas': _paginate(request, ideas),
        'briefs': _paginate(request, briefs),
        'templates': templates,
        'refresh_tasks': refresh_tasks,
        'performance': performance,
        'published_content_count': sum(1 for item in all_items if item.status == 'Published'),
        'querystring': request.GET.urlencode(),
        'category_form': category_form or ContentCategoryForm(),
        'tag_form': tag_form or ContentTagForm(),
    }
    return context


def build_content_detail_context(item, request=None):
    current = _date_range(_request_context(request)) if request else {
        'start_at': _aware_midnight(timezone.localdate() - timedelta(days=29)),
        'end_at': _aware_midnight(timezone.localdate() + timedelta(days=1)),
        'previous_start_at': _aware_midnight(timezone.localdate() - timedelta(days=59)),
        'previous_end_at': _aware_midnight(timezone.localdate() - timedelta(days=29)),
        'key': '30d',
    }
    checklist = [
        {'key': key, 'label': label, 'done': item.seo_checklist().get(key, False)}
        for key, label in SEO_CHECKLIST
    ]
    sessions = _match_content_sessions([item], current['start_at'], current['end_at'])
    views = _match_content_views([item], current['start_at'], current['end_at'])
    return {
        'item': item,
        'checklist': checklist,
        'seo_score': _seo_score(item),
        'word_count': item.word_count,
        'reading_time': item.reading_time,
        'metrics': _metrics(sessions, views),
        'sources': _traffic_sources(sessions, sessions.count()),
        'briefs': list(item.briefs.all()),
        'refresh_tasks': list(item.refresh_tasks.all()),
        'social_posts': list(item.social_posts.all()),
        'related_ideas': list(item.source_ideas.all()),
        'attribution_note': 'Traffic is matched from real Analytics landing paths and UTM content values.',
    }
