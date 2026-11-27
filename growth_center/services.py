from datetime import datetime, time, timedelta
from calendar import monthrange

from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone

from .models import AnalyticsSession, PageView
from .tracking import page_title_for_path

DATE_RANGES = (
    ('today', 'Today'),
    ('7d', 'Last 7 Days'),
    ('30d', 'Last 30 Days'),
    ('90d', 'Last 90 Days'),
    ('this_month', 'This Month'),
    ('last_month', 'Last Month'),
    ('custom', 'Custom Range'),
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
)

SOURCE_CATEGORIES = (
    'Organic Search',
    'Direct',
    'Social',
    'Referral',
    'Campaign/UTM',
    'Other',
)

SOURCE_TONES = {
    'Organic Search': 'green',
    'Direct': 'blue',
    'Social': 'purple',
    'Referral': 'amber',
    'Campaign/UTM': 'rose',
    'Other': 'slate',
}


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


def _default_grain(range_info):
    span = range_info['span_days']
    if span > 180:
        return 'monthly'
    if span > 62:
        return 'weekly'
    return 'daily'


def _session_queryset(range_info, source, previous=False):
    start_key = 'previous_start_dt' if previous else 'start_dt'
    end_key = 'previous_end_dt' if previous else 'end_dt'
    queryset = AnalyticsSession.objects.filter(
        started_at__gte=range_info[start_key],
        started_at__lt=range_info[end_key],
    )
    if source:
        queryset = queryset.filter(source_category=source)
    return queryset


def _pageview_queryset(range_info, source, previous=False):
    start_key = 'previous_start_dt' if previous else 'start_dt'
    end_key = 'previous_end_dt' if previous else 'end_dt'
    queryset = PageView.objects.filter(
        viewed_at__gte=range_info[start_key],
        viewed_at__lt=range_info[end_key],
    )
    if source:
        queryset = queryset.filter(session__source_category=source)
    return queryset


def _metrics(sessions, pageviews):
    total_sessions = sessions.count()
    unique_visitors = sessions.values('visitor_id').distinct().count()
    total_views = pageviews.count()
    bounced_sessions = sessions.filter(page_view_count=1).count()
    bounce_rate = round((bounced_sessions / total_sessions) * 100, 1) if total_sessions else 0.0
    return {
        'total_sessions': total_sessions,
        'unique_visitors': unique_visitors,
        'page_views': total_views,
        'bounced_sessions': bounced_sessions,
        'bounce_rate': bounce_rate,
    }


def _comparison(current, previous, rate=False):
    if rate:
        delta = round(current - previous, 1)
        direction = 'up' if delta > 0 else 'down' if delta < 0 else 'flat'
        return {'value': delta, 'label': f'{delta:+.1f} pts', 'direction': direction}
    if previous:
        delta = round(((current - previous) / previous) * 100, 1)
        direction = 'up' if delta > 0 else 'down' if delta < 0 else 'flat'
        return {'value': delta, 'label': f'{delta:+.1f}%', 'direction': direction}
    if current:
        return {'value': None, 'label': 'New', 'direction': 'up'}
    return {'value': 0.0, 'label': '0%', 'direction': 'flat'}


def _kpis(current, previous):
    return {
        'visitors': {
            'value': current['total_sessions'],
            'display': f"{current['total_sessions']:,}",
            'comparison': _comparison(current['total_sessions'], previous['total_sessions']),
        },
        'unique_visitors': {
            'value': current['unique_visitors'],
            'display': f"{current['unique_visitors']:,}",
            'comparison': _comparison(current['unique_visitors'], previous['unique_visitors']),
        },
        'page_views': {
            'value': current['page_views'],
            'display': f"{current['page_views']:,}",
            'comparison': _comparison(current['page_views'], previous['page_views']),
        },
        'bounce_rate': {
            'value': current['bounce_rate'],
            'display': f"{current['bounce_rate']:.1f}%",
            'comparison': _comparison(current['bounce_rate'], previous['bounce_rate'], rate=True),
        },
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
    visitor_expression = _trunc_expression('started_at', grain)
    view_expression = _trunc_expression('viewed_at', grain)

    session_rows = (
        sessions.annotate(bucket=visitor_expression)
        .values('bucket')
        .annotate(
            total=Count('id'),
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
    visitors = [session_map.get(key, {}).get('total', 0) for key in keys]
    views = [view_map.get(key, 0) for key in keys]
    new_visitors = [session_map.get(key, {}).get('new', 0) for key in keys]
    returning_visitors = [session_map.get(key, {}).get('returning', 0) for key in keys]

    return {
        'traffic': {
            'labels': labels,
            'visitors': visitors,
            'page_views': views,
        },
        'growth': {
            'labels': labels,
            'new': new_visitors,
            'returning': returning_visitors,
        },
    }


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
            'percent': round((count / total_sessions) * 100, 1) if total_sessions else 0.0,
            'tone': SOURCE_TONES[category],
        })
    return sorted(rows, key=lambda row: (-row['count'], row['category']))


def _top_pages(pageviews, total_views, sort):
    rows = list(
        pageviews.values('path')
        .annotate(
            views=Count('id'),
            visitors=Count('session__visitor_id', distinct=True),
        )
        .values('path', 'views', 'visitors')
    )
    if sort == 'visitors':
        rows.sort(key=lambda row: (row['visitors'], row['views']), reverse=True)
    elif sort == 'path':
        rows.sort(key=lambda row: row['path'])
    else:
        rows.sort(key=lambda row: (row['views'], row['visitors']), reverse=True)

    result = []
    for row in rows[:10]:
        result.append({
            'path': row['path'],
            'title': page_title_for_path(row['path']),
            'views': row['views'],
            'visitors': row['visitors'],
            'percent': round((row['views'] / total_views) * 100, 1) if total_views else 0.0,
        })
    return result


def build_analytics_context(request):
    range_info = _range_dates(request)
    source = request.GET.get('source', '')
    if source and source not in SOURCE_CATEGORIES:
        source = ''
    grain = request.GET.get('grain', '')
    if grain not in dict(GRAINS):
        grain = _default_grain(range_info)
    sort = request.GET.get('sort', 'views')
    if sort not in dict(SORTS):
        sort = 'views'

    sessions = _session_queryset(range_info, source)
    pageviews = _pageview_queryset(range_info, source)
    previous_sessions = _session_queryset(range_info, source, previous=True)
    previous_pageviews = _pageview_queryset(range_info, source, previous=True)

    current_metrics = _metrics(sessions, pageviews)
    previous_metrics = _metrics(previous_sessions, previous_pageviews)
    charts = _chart_series(sessions, pageviews, range_info, grain)

    return {
        'title': 'Marketing Analytics',
        'site_title': 'Marketing Analytics',
        'range': range_info,
        'range_choices': DATE_RANGES,
        'grain': grain,
        'grain_choices': GRAINS,
        'sort': sort,
        'sort_choices': SORTS,
        'source': source,
        'source_choices': SOURCE_CATEGORIES,
        'kpis': _kpis(current_metrics, previous_metrics),
        'charts': charts,
        'traffic_sources': _traffic_sources(sessions, current_metrics['total_sessions']),
        'top_pages': _top_pages(pageviews, current_metrics['page_views'], sort),
        'bounce': {
            'rate': current_metrics['bounce_rate'],
            'bounced_sessions': current_metrics['bounced_sessions'],
            'total_sessions': current_metrics['total_sessions'],
        },
        'has_data': bool(current_metrics['total_sessions'] or current_metrics['page_views']),
        'summary_text': f"Live analytics from {range_info['start']:%b %d, %Y} to {range_info['end']:%b %d, %Y} compared with the previous {range_info['span_days']} days.",
    }
