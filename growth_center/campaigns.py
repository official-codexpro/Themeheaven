from calendar import monthrange

from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.utils import timezone

from .campaign_urls import build_campaign_url
from .forms import CampaignForm
from .models import AnalyticsSession, Campaign, PageView
from .services import (
    DATE_RANGES,
    GRAINS,
    _chart_series,
    _comparison,
    _device_breakdown,
    _duration_display,
    _kpis,
    _metrics,
    _percent,
    _range_dates,
    _traffic_sources,
)

CAMPAIGN_SECTIONS = (
    ('overview', 'Overview'),
    ('campaigns', 'Campaigns'),
    ('builder', 'URL Builder'),
)

CAMPAIGN_SORTS = (
    ('created', 'Newest'),
    ('name', 'Name'),
    ('visits', 'Visits'),
    ('visitors', 'Visitors'),
    ('status', 'Status'),
    ('start', 'Start Date'),
    ('end', 'End Date'),
)

CAMPAIGN_TEMPLATES = (
    {'key': 'google_ads', 'label': 'Google Ads', 'source': 'google', 'medium': 'cpc'},
    {'key': 'facebook_ads', 'label': 'Facebook Ads', 'source': 'facebook', 'medium': 'paid_social'},
    {'key': 'instagram', 'label': 'Instagram', 'source': 'instagram', 'medium': 'social'},
    {'key': 'newsletter', 'label': 'Email Newsletter', 'source': 'newsletter', 'medium': 'email'},
    {'key': 'whatsapp', 'label': 'WhatsApp Marketing', 'source': 'whatsapp', 'medium': 'messaging'},
    {'key': 'organic_social', 'label': 'Organic Social', 'source': 'social_platform', 'medium': 'organic_social'},
)

PAGE_SIZE = 15


def _campaign_filters(request):
    status = request.GET.get('status', 'all')
    if status not in {'all'} | {key for key, _label in Campaign.STATUS_CHOICES}:
        status = 'all'

    section = request.GET.get('section', 'overview')
    if section not in dict(CAMPAIGN_SECTIONS):
        section = 'overview'

    sort = request.GET.get('sort', 'created')
    if sort not in dict(CAMPAIGN_SORTS):
        sort = 'created'

    direction = request.GET.get('dir', 'asc' if sort in {'name', 'status'} else 'desc')
    if direction not in {'asc', 'desc'}:
        direction = 'asc' if sort in {'name', 'status'} else 'desc'

    return {
        'status': status,
        'section': section,
        'sort': sort,
        'direction': direction,
        'query': (request.GET.get('q') or '').strip()[:120],
        'compare': request.GET.get('compare', '1') != '0',
    }


def _grain_for(request, range_info):
    grain = request.GET.get('grain', '')
    if grain in dict(GRAINS):
        return grain
    span = range_info['span_days']
    if span > 180:
        return 'monthly'
    if span > 62:
        return 'weekly'
    return 'daily'


def _session_query(campaigns, range_info, previous=False):
    names = [campaign.utm_campaign for campaign in campaigns if campaign.utm_campaign]
    if not names:
        return AnalyticsSession.objects.none()
    query = Q()
    for name in names:
        query |= Q(utm_campaign=name)
    start_key = 'previous_start_dt' if previous else 'start_dt'
    end_key = 'previous_end_dt' if previous else 'end_dt'
    return AnalyticsSession.objects.filter(
        query,
        started_at__gte=range_info[start_key],
        started_at__lt=range_info[end_key],
    )


def _pageview_query(campaigns, range_info, previous=False):
    names = [campaign.utm_campaign for campaign in campaigns if campaign.utm_campaign]
    if not names:
        return PageView.objects.none()
    start_key = 'previous_start_dt' if previous else 'start_dt'
    end_key = 'previous_end_dt' if previous else 'end_dt'
    return PageView.objects.filter(
        session__utm_campaign__in=names,
        viewed_at__gte=range_info[start_key],
        viewed_at__lt=range_info[end_key],
    )


def _stats(sessions, pageviews):
    session_rows = list(
        sessions.values('utm_campaign').annotate(
            visits=Count('id'),
            visitors=Count('visitor_id', distinct=True),
            bounced=Count('id', filter=Q(page_view_count=1)),
            avg_duration=Avg('duration_seconds'),
        ).values('utm_campaign', 'visits', 'visitors', 'bounced', 'avg_duration')
    )
    view_rows = dict(
        pageviews.values('session__utm_campaign')
        .annotate(views=Count('id'))
        .values_list('session__utm_campaign', 'views')
    )
    result = {}
    for row in session_rows:
        visits = row['visits']
        result[row['utm_campaign']] = {
            'visits': visits,
            'visitors': row['visitors'],
            'views': view_rows.get(row['utm_campaign'], 0),
            'bounce_rate': _percent(row['bounced'], visits),
            'avg_duration_display': _duration_display(row['avg_duration'] or 0),
        }
    return result


def _blank_stats():
    return {
        'visits': 0,
        'visitors': 0,
        'views': 0,
        'bounce_rate': 0.0,
        'avg_duration_display': '—',
    }


def _campaign_url(campaign):
    url, _error = build_campaign_url(
        campaign.destination_url,
        campaign.utm_source,
        campaign.utm_medium,
        campaign.utm_campaign,
        campaign.utm_term,
        campaign.utm_content,
    )
    return url


def _created_this_month():
    today = timezone.localdate()
    start = today.replace(day=1)
    days = monthrange(today.year, today.month)[1]
    end = start.replace(day=days)
    return Campaign.objects.filter(created_at__date__gte=start, created_at__date__lte=end).count()


def build_campaign_context(request, form=None):
    range_info = _range_dates(request)
    filters = _campaign_filters(request)
    grain = _grain_for(request, range_info)
    campaigns = list(Campaign.objects.all())
    sessions = _session_query(campaigns, range_info)
    pageviews = _pageview_query(campaigns, range_info)
    stats = _stats(sessions, pageviews)

    query = filters['query'].lower()
    filtered = []
    for campaign in campaigns:
        if filters['status'] != 'all' and campaign.status != filters['status']:
            continue
        if query and query not in f'{campaign.name} {campaign.utm_source} {campaign.utm_medium} {campaign.utm_campaign}'.lower():
            continue
        values = stats.get(campaign.utm_campaign, _blank_stats())
        filtered.append({
            'campaign': campaign,
            'url': _campaign_url(campaign),
            'visits': values['visits'],
            'visitors': values['visitors'],
            'views': values['views'],
            'bounce_rate': values['bounce_rate'],
            'avg_duration_display': values['avg_duration_display'],
        })

    sort_key = {
        'created': 'created_sort',
        'name': 'name_sort',
        'visits': 'visits',
        'visitors': 'visitors',
        'status': 'status_sort',
        'start': 'start_sort',
        'end': 'end_sort',
    }[filters['sort']]
    for row in filtered:
        campaign = row['campaign']
        row['created_sort'] = campaign.created_at.timestamp()
        row['name_sort'] = campaign.name.lower()
        row['status_sort'] = campaign.status.lower()
        row['start_sort'] = campaign.start_date.isoformat() if campaign.start_date else '9999-12-31'
        row['end_sort'] = campaign.end_date.isoformat() if campaign.end_date else '9999-12-31'
    filtered.sort(key=lambda row: row[sort_key], reverse=filters['direction'] == 'desc')
    paginator = Paginator(filtered, PAGE_SIZE)
    campaign_page = paginator.get_page(request.GET.get('page'))

    top = max(filtered, key=lambda row: (row['visits'], row['visitors'], row['campaign'].name), default=None)
    active_count = sum(1 for campaign in campaigns if campaign.status == 'Active')
    total_visitors = sessions.values('visitor_id').distinct().count()

    query_params = request.GET.copy()
    query_params.pop('page', None)

    return {
        'title': 'Campaigns / UTM Manager',
        'range': range_info,
        'range_choices': DATE_RANGES,
        'grain': grain,
        'grain_choices': GRAINS,
        'sections': CAMPAIGN_SECTIONS,
        'section': filters['section'],
        'statuses': Campaign.STATUS_CHOICES,
        'status': filters['status'],
        'sorts': CAMPAIGN_SORTS,
        'sort': filters['sort'],
        'sort_direction': filters['direction'],
        'query': filters['query'],
        'compare': filters['compare'],
        'query_params': query_params.urlencode(),
        'templates': CAMPAIGN_TEMPLATES,
        'form': form or CampaignForm(),
        'campaigns': campaign_page,
        'campaign_count': len(campaigns),
        'active_count': active_count,
        'visits_count': sessions.count(),
        'visitors_count': total_visitors,
        'created_this_month': _created_this_month(),
        'top_campaign': top,
        'chart': _chart_series(sessions, pageviews, range_info, grain),
        'has_data': bool(sessions.exists() or pageviews.exists()),
        'summary_text': (
            f"Campaign traffic from {range_info['start']:%b %d, %Y} to {range_info['end']:%b %d, %Y}. "
            f"{'Compared with the previous equivalent period.' if filters['compare'] else 'Period comparison is off.'}"
        ),
    }


def build_campaign_detail_context(request, campaign):
    range_info = _range_dates(request)
    filters = _campaign_filters(request)
    grain = _grain_for(request, range_info)

    sessions = _session_query([campaign], range_info)
    pageviews = _pageview_query([campaign], range_info)
    previous_sessions = _session_query([campaign], range_info, previous=True)
    previous_pageviews = _pageview_query([campaign], range_info, previous=True)

    current_metrics = _metrics(sessions, pageviews)
    previous_metrics = _metrics(previous_sessions, previous_pageviews)
    landings = list(
        sessions.exclude(landing_path='')
        .values('landing_path')
        .annotate(visits=Count('id'), visitors=Count('visitor_id', distinct=True))
        .values('landing_path', 'visits', 'visitors')
        .order_by('-visits')[:10]
    )
    content_rows = list(
        sessions.exclude(utm_content='')
        .values('utm_content')
        .annotate(visits=Count('id'))
        .order_by('-visits')[:10]
    )
    term_rows = list(
        sessions.exclude(utm_term='')
        .values('utm_term')
        .annotate(visits=Count('id'))
        .order_by('-visits')[:10]
    )

    return {
        'title': campaign.name,
        'campaign': campaign,
        'campaign_url': _campaign_url(campaign),
        'range': range_info,
        'range_choices': DATE_RANGES,
        'grain': grain,
        'grain_choices': GRAINS,
        'compare': filters['compare'],
        'kpis': _kpis(current_metrics, previous_metrics, filters['compare']),
        'charts': _chart_series(sessions, pageviews, range_info, grain),
        'devices': _device_breakdown(sessions, current_metrics['total_sessions']),
        'sources': _traffic_sources(sessions, current_metrics['total_sessions']),
        'landings': landings,
        'content_rows': content_rows,
        'term_rows': term_rows,
        'has_data': bool(current_metrics['total_sessions'] or current_metrics['page_views']),
        'summary_text': (
            f"Real campaign analytics from {range_info['start']:%b %d, %Y} to {range_info['end']:%b %d, %Y}. "
            f"{'Compared with the previous equivalent period.' if filters['compare'] else 'Period comparison is off.'}"
        ),
    }
