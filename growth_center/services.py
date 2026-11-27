from calendar import monthrange
from datetime import datetime, time, timedelta

from django.core.paginator import Paginator
from django.db.models import Avg, Case, CharField, Count, Q, Value, When
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone

from .models import AnalyticsSession, PageView
from .tracking import page_title_for_path

DATE_RANGES = (
    ('today', 'Today'),
    ('yesterday', 'Yesterday'),
    ('7d', 'Last 7 Days'),
    ('30d', 'Last 30 Days'),
    ('90d', 'Last 90 Days'),
    ('this_month', 'This Month'),
    ('last_month', 'Last Month'),
    ('custom', 'Custom Date Range'),
)

GRAINS = (
    ('daily', 'Daily'),
    ('weekly', 'Weekly'),
    ('monthly', 'Monthly'),
)

SORTS = (
    ('views', 'Page Views'),
    ('visitors', 'Unique Visitors'),
    ('path', 'Path'),
    ('sessions', 'Sessions'),
    ('time', 'Avg. Time on Page'),
    ('bounce', 'Bounce Rate'),
    ('exit', 'Exit Rate'),
)

SECTIONS = (
    ('overview', 'Overview'),
    ('traffic', 'Traffic'),
    ('acquisition', 'Acquisition'),
    ('audience', 'Audience'),
    ('pages', 'Pages'),
    ('landing', 'Landing Pages'),
    ('devices', 'Devices'),
    ('geography', 'Geography'),
)

SOURCE_CATEGORIES = (
    'Organic Search',
    'Direct',
    'Social',
    'Referral',
    'Paid Search',
    'Email',
    'Campaign/UTM',
    'Other',
)

SOURCE_TONES = {
    'Organic Search': 'green',
    'Direct': 'blue',
    'Social': 'purple',
    'Referral': 'amber',
    'Paid Search': 'rose',
    'Email': 'cyan',
    'Campaign/UTM': 'rose',
    'Other': 'slate',
}

DEVICE_CATEGORIES = ('Desktop', 'Mobile', 'Tablet')
DEVICE_TONES = {'Desktop': 'blue', 'Mobile': 'purple', 'Tablet': 'amber'}
TRAFFIC_METRICS = (
    ('visitors', 'Visitors'),
    ('sessions', 'Sessions'),
    ('page_views', 'Page Views'),
)

PAGE_SIZE = 15


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _aware_midnight(day):
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


def _range_dates(request):
    today = timezone.localdate()
    range_key = request.GET.get('range', '7d')
    if range_key not in dict(DATE_RANGES):
        range_key = '7d'

    if range_key == 'today':
        start = end = today
    elif range_key == 'yesterday':
        start = end = today - timedelta(days=1)
    elif range_key == '7d':
        end = today
        start = today - timedelta(days=6)
    elif range_key == '30d':
        end = today
        start = today - timedelta(days=29)
    elif range_key == '90d':
        end = today
        start = today - timedelta(days=89)
    elif range_key == 'this_month':
        start = today.replace(day=1)
        end = today
    elif range_key == 'last_month':
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    else:
        end = _parse_date(request.GET.get('end')) or today
        start = _parse_date(request.GET.get('start')) or today - timedelta(days=6)
        if end > today:
            end = today
        if start > end:
            start, end = end, start
        if (end - start).days > 365:
            start = end - timedelta(days=365)

    span_days = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=span_days - 1)
    return {
        'key': range_key,
        'label': dict(DATE_RANGES)[range_key],
        'start': start,
        'end': end,
        'start_iso': start.isoformat(),
        'end_iso': end.isoformat(),
        'span_days': span_days,
        'start_dt': _aware_midnight(start),
        'end_dt': _aware_midnight(end + timedelta(days=1)),
        'previous_start_dt': _aware_midnight(previous_start),
        'previous_end_dt': _aware_midnight(start),
    }


def _request_filters(request):
    source = request.GET.get('source', '')
    if source and source not in SOURCE_CATEGORIES:
        source = ''

    device = request.GET.get('device', '')
    if device not in DEVICE_CATEGORIES:
        device = ''

    landing = (request.GET.get('landing') or '').strip()
    if landing and not landing.startswith('/'):
        landing = ''
    landing = landing[:500]

    page_path = (request.GET.get('page_path') or '').strip()
    if page_path and not page_path.startswith('/'):
        page_path = ''
    page_path = page_path[:500]

    metric = request.GET.get('metric', 'visitors')
    if metric not in dict(TRAFFIC_METRICS):
        metric = 'visitors'

    section = request.GET.get('section', 'overview')
    if section not in dict(SECTIONS):
        section = 'overview'

    sort = request.GET.get('sort', 'views')
    if sort not in dict(SORTS):
        sort = 'views'

    direction = request.GET.get('dir', 'desc' if sort != 'path' else 'asc')
    if direction not in {'asc', 'desc'}:
        direction = 'desc' if sort != 'path' else 'asc'

    return {
        'source': source,
        'device': device,
        'landing': landing,
        'page_path': page_path,
        'metric': metric,
        'section': section,
        'sort': sort,
        'direction': direction,
        'query': (request.GET.get('q') or '').strip()[:120],
        'compare': request.GET.get('compare', '1') != '0',
    }


def _default_grain(range_info):
    span = range_info['span_days']
    if span > 180:
        return 'monthly'
    if span > 62:
        return 'weekly'
    return 'daily'


def _session_queryset(range_info, filters, previous=False):
    start_key = 'previous_start_dt' if previous else 'start_dt'
    end_key = 'previous_end_dt' if previous else 'end_dt'
    queryset = AnalyticsSession.objects.filter(
        started_at__gte=range_info[start_key],
        started_at__lt=range_info[end_key],
    )
    if filters['source']:
        queryset = queryset.filter(source_category=filters['source'])
    if filters['device']:
        queryset = queryset.filter(device_category=filters['device'])
    if filters['landing']:
        queryset = queryset.filter(landing_path=filters['landing'])
    return queryset


def _pageview_queryset(range_info, filters, previous=False):
    start_key = 'previous_start_dt' if previous else 'start_dt'
    end_key = 'previous_end_dt' if previous else 'end_dt'
    queryset = PageView.objects.filter(
        viewed_at__gte=range_info[start_key],
        viewed_at__lt=range_info[end_key],
    )
    if filters['source']:
        queryset = queryset.filter(session__source_category=filters['source'])
    if filters['device']:
        queryset = queryset.filter(session__device_category=filters['device'])
    if filters['landing']:
        queryset = queryset.filter(session__landing_path=filters['landing'])
    if filters['page_path']:
        queryset = queryset.filter(path=filters['page_path'])
    return queryset


def _metrics(sessions, pageviews):
    total_sessions = sessions.count()
    unique_visitors = sessions.values('visitor_id').distinct().count()
    total_views = pageviews.count()
    bounced_sessions = sessions.filter(page_view_count=1).count()
    bounce_rate = round((bounced_sessions / total_sessions) * 100, 1) if total_sessions else 0.0
    duration_data = sessions.exclude(duration_seconds__isnull=True).aggregate(
        total=Count('id'),
        average=Avg('duration_seconds'),
    )
    duration_sessions = duration_data['total'] or 0
    avg_duration = round(duration_data['average'] or 0, 1)
    return {
        'total_sessions': total_sessions,
        'unique_visitors': unique_visitors,
        'page_views': total_views,
        'bounced_sessions': bounced_sessions,
        'bounce_rate': bounce_rate,
        'duration_sessions': duration_sessions,
        'avg_duration_seconds': avg_duration,
        'new_sessions': sessions.filter(is_returning=False).count(),
        'returning_sessions': sessions.filter(is_returning=True).count(),
        'pages_per_session': round(total_views / total_sessions, 2) if total_sessions else 0.0,
    }


def _comparison(current, previous, rate=False, enabled=True, positive_when_down=False):
    def result(value, label, direction, positive):
        tone = 'ga-positive' if positive else 'ga-negative' if positive is False else ''
        return {
            'value': value,
            'label': label,
            'direction': direction,
            'positive': positive,
            'tone': tone,
        }

    if not enabled:
        return result(None, 'Comparison off', 'flat', None)
    if rate:
        delta = round(current - previous, 1)
        direction = 'up' if delta > 0 else 'down' if delta < 0 else 'flat'
        positive = delta < 0 if positive_when_down else delta > 0 if delta > 0 else None
        return result(delta, f'{delta:+.1f} pts', direction, positive)
    if previous:
        delta = round(((current - previous) / previous) * 100, 1)
        direction = 'up' if delta > 0 else 'down' if delta < 0 else 'flat'
        positive = delta < 0 if positive_when_down else delta > 0 if delta > 0 else None
        return result(delta, f'{delta:+.1f}%', direction, positive)
    if current:
        return result(None, 'New', 'up', True)
    return result(0.0, '0%', 'flat', None)


def _duration_display(value):
    seconds = int(value or 0)
    if seconds <= 0:
        return '—'
    minutes, remainder = divmod(seconds, 60)
    if minutes < 60:
        return f'{minutes}m {remainder:02d}s'
    hours, minutes = divmod(minutes, 60)
    return f'{hours}h {minutes:02d}m'


def _kpis(current, previous, compare=True):
    def item(key, label, value, display, comparison, help_text, direction_label='vs previous period'):
        return {
            'key': key,
            'label': label,
            'value': value,
            'display': display,
            'comparison': comparison,
            'help': help_text,
            'direction_label': direction_label,
        }

    new_returning = f"{current['new_sessions']:,} / {current['returning_sessions']:,}"
    return {
        'visitors': item(
            'visitors',
            'Total Visitors',
            current['total_sessions'],
            f"{current['total_sessions']:,}",
            _comparison(current['total_sessions'], previous['total_sessions'], enabled=compare),
            'Count of visitor sessions that loaded at least one tracked public page.',
        ),
        'unique_visitors': item(
            'unique_visitors',
            'Unique Visitors',
            current['unique_visitors'],
            f"{current['unique_visitors']:,}",
            _comparison(current['unique_visitors'], previous['unique_visitors'], enabled=compare),
            'Distinct privacy-safe visitor identifiers active in the selected period.',
        ),
        'page_views': item(
            'page_views',
            'Page Views',
            current['page_views'],
            f"{current['page_views']:,}",
            _comparison(current['page_views'], previous['page_views'], enabled=compare),
            'Tracked views of public HTML pages, excluding repeat views within 90 seconds.',
        ),
        'sessions': item(
            'sessions',
            'Sessions',
            current['total_sessions'],
            f"{current['total_sessions']:,}",
            _comparison(current['total_sessions'], previous['total_sessions'], enabled=compare),
            'A session groups pages viewed by one visitor during a single day.',
        ),
        'bounce_rate': item(
            'bounce_rate',
            'Bounce Rate',
            current['bounce_rate'],
            f"{current['bounce_rate']:.1f}%",
            _comparison(current['bounce_rate'], previous['bounce_rate'], rate=True, enabled=compare, positive_when_down=True),
            'Percentage of sessions that viewed only one page. Lower is usually better.',
        ),
        'avg_session_duration': item(
            'avg_session_duration',
            'Average Session Duration',
            current['avg_duration_seconds'],
            _duration_display(current['avg_duration_seconds']),
            _comparison(current['avg_duration_seconds'], previous['avg_duration_seconds'], enabled=compare),
            'Average time from session start to the exit beacon, when available.',
        ),
        'pages_per_session': item(
            'pages_per_session',
            'Pages Per Session',
            current['pages_per_session'],
            f"{current['pages_per_session']:.2f}",
            _comparison(current['pages_per_session'], previous['pages_per_session'], enabled=compare),
            'Average number of tracked page views divided by sessions.',
        ),
        'new_returning': item(
            'new_returning',
            'New vs Returning',
            current['new_sessions'],
            new_returning,
            _comparison(current['new_sessions'], previous['new_sessions'], enabled=compare),
            'New sessions compared with sessions from previously seen visitor identifiers.',
        ),
    }


def _trunc_expression(field, grain):
    if grain == 'weekly':
        return TruncWeek(field)
    if grain == 'monthly':
        return TruncMonth(field)
    return TruncDate(field)


def _bucket_key(value):
    if isinstance(value, datetime):
        return value.date()
    return value


def _bucket_keys(start_date, end_date, grain):
    keys = []
    if grain == 'daily':
        cursor = start_date
        while cursor <= end_date:
            keys.append(cursor)
            cursor += timedelta(days=1)
    elif grain == 'weekly':
        cursor = start_date - timedelta(days=start_date.weekday())
        while cursor <= end_date:
            keys.append(cursor)
            cursor += timedelta(days=7)
    else:
        cursor = start_date.replace(day=1)
        while cursor <= end_date:
            keys.append(cursor)
            days_in_month = monthrange(cursor.year, cursor.month)[1]
            cursor = (cursor + timedelta(days=days_in_month)).replace(day=1)
    return keys


def _bucket_label(bucket, grain):
    if grain == 'monthly':
        return bucket.strftime('%b %Y')
    if grain == 'weekly':
        return f'Week of {bucket.strftime("%b %d")}'
    return bucket.strftime('%b %d')


def _chart_series(sessions, pageviews, range_info, grain):
    keys = _bucket_keys(range_info['start'], range_info['end'], grain)
    session_expression = _trunc_expression('started_at', grain)
    view_expression = _trunc_expression('viewed_at', grain)

    session_rows = (
        sessions.annotate(bucket=session_expression)
        .values('bucket')
        .annotate(
            sessions=Count('id'),
            visitors=Count('visitor_id', distinct=True),
            new=Count('id', filter=Q(is_returning=False)),
            returning=Count('id', filter=Q(is_returning=True)),
        )
    )
    view_rows = (
        pageviews.annotate(bucket=view_expression)
        .values('bucket')
        .annotate(total=Count('id'))
    )

    session_map = {_bucket_key(row['bucket']): row for row in session_rows}
    view_map = {_bucket_key(row['bucket']): row['total'] for row in view_rows}

    labels = [_bucket_label(key, grain) for key in keys]
    return {
        'traffic': {
            'labels': labels,
            'visitors': [session_map.get(key, {}).get('visitors', 0) for key in keys],
            'sessions': [session_map.get(key, {}).get('sessions', 0) for key in keys],
            'page_views': [view_map.get(key, 0) for key in keys],
        },
        'growth': {
            'labels': labels,
            'new': [session_map.get(key, {}).get('new', 0) for key in keys],
            'returning': [session_map.get(key, {}).get('returning', 0) for key in keys],
        },
    }


def _percent(count, total):
    return round((count / total) * 100, 1) if total else 0.0


def _traffic_sources(sessions, total_sessions):
    counts = dict(
        sessions.values('source_category')
        .annotate(total=Count('id'))
        .values_list('source_category', 'total')
    )
    rows = []
    for category in SOURCE_CATEGORIES:
        count = counts.get(category, 0)
        rows.append({
            'category': category,
            'count': count,
            'percent': _percent(count, total_sessions),
            'tone': SOURCE_TONES[category],
        })
    return sorted(rows, key=lambda row: (-row['count'], row['category']))


def _device_breakdown(sessions, total_sessions):
    counts = dict(
        sessions.values('device_category')
        .annotate(total=Count('id'))
        .values_list('device_category', 'total')
    )
    rows = []
    for device in DEVICE_CATEGORIES:
        count = counts.get(device, 0)
        rows.append({
            'category': device,
            'count': count,
            'percent': _percent(count, total_sessions),
            'tone': DEVICE_TONES[device],
        })
    return sorted(rows, key=lambda row: (-row['count'], row['category']))


def _geography(sessions, total_sessions):
    rows = list(
        sessions.exclude(country_code='')
        .values('country_code')
        .annotate(
            sessions=Count('id'),
            visitors=Count('visitor_id', distinct=True),
        )
        .values('country_code', 'sessions', 'visitors')
        .order_by('-sessions')[:15]
    )
    for row in rows:
        row['label'] = row['country_code']
        row['percent'] = _percent(row['sessions'], total_sessions)
    return rows


def _referrers(sessions, total_sessions):
    rows = list(
        sessions.exclude(source_label='')
        .values('source_label')
        .annotate(total=Count('id'))
        .values('source_label', 'total')
        .order_by('-total')[:12]
    )
    return [
        {
            'label': row['source_label'],
            'count': row['total'],
            'percent': _percent(row['total'], total_sessions),
        }
        for row in rows
    ]


def _campaigns(sessions, total_sessions):
    rows = list(
        sessions.filter(
            Q(utm_source__gt='') | Q(utm_medium__gt='') | Q(utm_campaign__gt='')
        )
        .values('utm_source', 'utm_medium', 'utm_campaign')
        .annotate(total=Count('id'))
        .order_by('-total')[:12]
    )
    result = []
    for row in rows:
        parts = [row['utm_source'], row['utm_medium'], row['utm_campaign']]
        label = ' · '.join(part for part in parts if part) or 'Campaign'
        result.append({
            'label': label,
            'count': row['total'],
            'percent': _percent(row['total'], total_sessions),
            'utm_campaign': row['utm_campaign'],
        })
    return result


def _duration_bands(sessions):
    bands = [
        ('Under 10s', Q(duration_seconds__lt=10)),
        ('10–30s', Q(duration_seconds__gte=10, duration_seconds__lt=30)),
        ('30–60s', Q(duration_seconds__gte=30, duration_seconds__lt=60)),
        ('1–3m', Q(duration_seconds__gte=60, duration_seconds__lt=180)),
        ('3m+', Q(duration_seconds__gte=180)),
    ]
    counts = dict(
        sessions.exclude(duration_seconds__isnull=True)
        .annotate(band=Case(
            *[When(condition, then=Value(label)) for label, condition in bands],
            default=Value('Other'),
            output_field=CharField(),
        ))
        .values('band')
        .annotate(total=Count('id'))
        .values_list('band', 'total')
    )
    return [{'label': label, 'count': counts.get(label, 0)} for label, _ in bands]


def _pages_per_session_bands(sessions):
    bands = [('1 page', Q(page_view_count=1)), ('2 pages', Q(page_view_count=2))]
    counts = dict(
        sessions.annotate(band=Case(
            When(page_view_count=1, then=Value('1 page')),
            When(page_view_count=2, then=Value('2 pages')),
            When(page_view_count__gte=3, page_view_count__lte=4, then=Value('3–4 pages')),
            default=Value('5+ pages'),
            output_field=CharField(),
        ))
        .values('band')
        .annotate(total=Count('id'))
        .values_list('band', 'total')
    )
    return [
        {'label': '1 page', 'count': counts.get('1 page', 0)},
        {'label': '2 pages', 'count': counts.get('2 pages', 0)},
        {'label': '3–4 pages', 'count': counts.get('3–4 pages', 0)},
        {'label': '5+ pages', 'count': counts.get('5+ pages', 0)},
    ]


def _paginate(request, rows, param, sort, direction):
    reverse_order = direction == 'desc'
    rows.sort(key=lambda row: str(row.get('sort_key', '')).lower(), reverse=reverse_order)
    paginator = Paginator(rows, PAGE_SIZE)
    return paginator.get_page(request.GET.get(param))


def _pages_report(request, pageviews, sessions, filters):
    exit_counts = dict(
        sessions.exclude(exit_path='')
        .values('exit_path')
        .annotate(total=Count('id'))
        .values_list('exit_path', 'total')
    )
    rows = list(
        pageviews.values('path')
        .annotate(
            views=Count('id'),
            visitors=Count('session__visitor_id', distinct=True),
            sessions=Count('session_id', distinct=True),
            bounced=Count('id', filter=Q(session__page_view_count=1)),
            avg_time=Avg('duration_seconds', filter=Q(duration_seconds__isnull=False)),
        )
        .values('path', 'views', 'visitors', 'sessions', 'bounced', 'avg_time')
    )

    result = []
    query = filters['query'].lower()
    for row in rows:
        title = page_title_for_path(row['path'])
        if query and query not in f'{title} {row["path"]}'.lower():
            continue
        exits = exit_counts.get(row['path'], 0)
        result.append({
            'path': row['path'],
            'title': title,
            'views': row['views'],
            'visitors': row['visitors'],
            'sessions': row['sessions'],
            'avg_time_seconds': round(row['avg_time'] or 0, 1),
            'avg_time_display': _duration_display(row['avg_time'] or 0),
            'bounce_rate': _percent(row['bounced'], row['views']),
            'exit_rate': _percent(exits, row['sessions']),
            'exits': exits,
        })

    sort_key_map = {
        'views': 'views',
        'visitors': 'visitors',
        'sessions': 'sessions',
        'time': 'avg_time_seconds',
        'bounce': 'bounce_rate',
        'exit': 'exit_rate',
        'path': 'path',
    }
    for row in result:
        row['sort_key'] = row[sort_key_map.get(filters['sort'], 'views')]
    return _paginate(request, result, 'page', filters['sort'], filters['direction'])


def _landing_report(request, sessions, filters):
    rows = list(
        sessions.exclude(landing_path='')
        .values('landing_path')
        .annotate(
            sessions=Count('id'),
            visitors=Count('visitor_id', distinct=True),
            bounced=Count('id', filter=Q(page_view_count=1)),
            avg_duration=Avg('duration_seconds', filter=Q(duration_seconds__isnull=False)),
        )
        .values('landing_path', 'sessions', 'visitors', 'bounced', 'avg_duration')
    )

    result = []
    query = filters['query'].lower()
    for row in rows:
        title = page_title_for_path(row['landing_path'])
        if query and query not in f'{title} {row["landing_path"]}'.lower():
            continue
        result.append({
            'path': row['landing_path'],
            'title': title,
            'sessions': row['sessions'],
            'visitors': row['visitors'],
            'bounce_rate': _percent(row['bounced'], row['sessions']),
            'avg_duration_seconds': round(row['avg_duration'] or 0, 1),
            'avg_duration_display': _duration_display(row['avg_duration'] or 0),
            'conversion_rate': None,
        })

    sort_key_map = {
        'views': 'sessions',
        'visitors': 'visitors',
        'sessions': 'sessions',
        'time': 'avg_duration_seconds',
        'bounce': 'bounce_rate',
        'exit': 'bounce_rate',
        'path': 'path',
    }
    for row in result:
        row['sort_key'] = row[sort_key_map.get(filters['sort'], 'sessions')]
    return _paginate(request, result, 'landing_page', filters['sort'], filters['direction'])


def _entry_exit_pages(sessions):
    entries = list(
        sessions.exclude(landing_path='')
        .values('landing_path')
        .annotate(total=Count('id'))
        .values('landing_path', 'total')
        .order_by('-total')[:10]
    )
    exits = list(
        sessions.exclude(exit_path='')
        .values('exit_path')
        .annotate(total=Count('id'))
        .values('exit_path', 'total')
        .order_by('-total')[:10]
    )
    return {
        'entries': [
            {'path': row['landing_path'], 'title': page_title_for_path(row['landing_path']), 'count': row['total']}
            for row in entries
        ],
        'exits': [
            {'path': row['exit_path'], 'title': page_title_for_path(row['exit_path']), 'count': row['total']}
            for row in exits
        ],
    }


def _navigation(pageviews):
    rows = list(
        pageviews.exclude(from_path='')
        .values('from_path', 'path')
        .annotate(total=Count('id'))
        .values('from_path', 'path', 'total')
        .order_by('-total')[:12]
    )
    return [
        {
            'from_path': row['from_path'],
            'from_title': page_title_for_path(row['from_path']),
            'to_path': row['path'],
            'to_title': page_title_for_path(row['path']),
            'count': row['total'],
        }
        for row in rows
    ]


def _page_detail(sessions, pageviews, range_info, grain, filters):
    path = filters['page_path']
    if not path:
        return None
    detail_views = pageviews.filter(path=path)
    detail_sessions = sessions.filter(page_views__path=path).distinct()
    metrics = _metrics(detail_sessions, detail_views)
    sources = _traffic_sources(detail_sessions, metrics['total_sessions'])
    return {
        'path': path,
        'title': page_title_for_path(path),
        'metrics': metrics,
        'charts': _chart_series(detail_sessions, detail_views, range_info, grain),
        'sources': sources,
        'avg_time_display': _duration_display(metrics['avg_duration_seconds']),
    }


def build_analytics_context(request):
    range_info = _range_dates(request)
    filters = _request_filters(request)
    grain = request.GET.get('grain', '')
    if grain not in dict(GRAINS):
        grain = _default_grain(range_info)

    sessions = _session_queryset(range_info, filters)
    pageviews = _pageview_queryset(range_info, filters)
    previous_sessions = _session_queryset(range_info, filters, previous=True)
    previous_pageviews = _pageview_queryset(range_info, filters, previous=True)

    current_metrics = _metrics(sessions, pageviews)
    previous_metrics = _metrics(previous_sessions, previous_pageviews)
    charts = _chart_series(sessions, pageviews, range_info, grain)
    source_rows = _traffic_sources(sessions, current_metrics['total_sessions'])
    device_rows = _device_breakdown(sessions, current_metrics['total_sessions'])
    pages = _pages_report(request, pageviews, sessions, filters)
    landing_pages = _landing_report(request, sessions, filters)
    entry_exit = _entry_exit_pages(sessions)
    compare = filters['compare']

    return {
        'title': 'Marketing Analytics',
        'site_title': 'Marketing Analytics',
        'range': range_info,
        'range_choices': DATE_RANGES,
        'grain': grain,
        'grain_choices': GRAINS,
        'sort': filters['sort'],
        'sort_choices': SORTS,
        'sort_direction': filters['direction'],
        'source': filters['source'],
        'source_choices': SOURCE_CATEGORIES,
        'device': filters['device'],
        'device_choices': DEVICE_CATEGORIES,
        'landing': filters['landing'],
        'landing_choices': [
            row['landing_path']
            for row in sessions.exclude(landing_path='').values('landing_path').distinct().order_by('landing_path')[:25]
        ],
        'metric': filters['metric'],
        'metric_choices': TRAFFIC_METRICS,
        'section': filters['section'],
        'sections': SECTIONS,
        'compare': compare,
        'query': filters['query'],
        'filters': filters,
        'kpis': _kpis(current_metrics, previous_metrics, compare),
        'charts': charts,
        'traffic_sources': source_rows,
        'device_breakdown': device_rows,
        'geography': _geography(sessions, current_metrics['total_sessions']),
        'acquisition': {
            'sources': source_rows,
            'referrers': _referrers(sessions, current_metrics['total_sessions']),
            'campaigns': _campaigns(sessions, current_metrics['total_sessions']),
        },
        'audience': {
            'new_sessions': current_metrics['new_sessions'],
            'returning_sessions': current_metrics['returning_sessions'],
            'duration_bands': _duration_bands(sessions),
            'pages_bands': _pages_per_session_bands(sessions),
        },
        'top_pages': pages,
        'pages_page': pages,
        'landing_pages': landing_pages,
        'landing_page': landing_pages,
        'behavior': {
            'entry_pages': entry_exit['entries'],
            'exit_pages': entry_exit['exits'],
            'navigation': _navigation(pageviews),
            'referrers': _referrers(sessions, current_metrics['total_sessions']),
        },
        'page_detail': _page_detail(sessions, pageviews, range_info, grain, filters),
        'bounce': {
            'rate': current_metrics['bounce_rate'],
            'bounced_sessions': current_metrics['bounced_sessions'],
            'total_sessions': current_metrics['total_sessions'],
        },
        'has_data': bool(current_metrics['total_sessions'] or current_metrics['page_views']),
        'summary_text': (
            f"Live analytics from {range_info['start']:%b %d, %Y} to {range_info['end']:%b %d, %Y}. "
            f"{'Compared with the previous equivalent period.' if compare else 'Period comparison is off.'}"
        ),
    }
