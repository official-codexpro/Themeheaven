from datetime import datetime, timedelta
from decimal import Decimal

from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Min, Q
from django.utils import timezone

from .conversion_constants import (
    CONVERSION_SECTIONS,
    PRIVACY_NOTE,
    REVENUE_NOTE,
)
from .conversion_forms import ConversionFilterForm
from .conversion_validators import clean_event_name, clean_path, is_safe_event_name
from .models import (
    AnalyticsSession,
    Campaign,
    CampaignCost,
    ConversionEvent,
    ConversionFunnel,
    ConversionGoal,
    PageView,
    TrackingRule,
)
from .services import (
    _aware_midnight,
    _bucket_keys,
    _bucket_label,
    _comparison,
    _parse_date,
    _percent,
    _trunc_expression,
)
from .tracking import (
    decode_tracking_token,
    get_session_key,
    get_visitor_key,
    is_bot_request,
    is_excluded_path,
)

PAGE_SIZE = 15
RATE_LIMIT_COUNT = 30
RATE_LIMIT_SECONDS = 60


def is_trackable_conversion_request(request):
    if is_excluded_path(request.path_info):
        return False
    if request.headers.get('DNT') == '1':
        return False
    if getattr(request.user, 'is_authenticated', False):
        return False
    if is_bot_request(request):
        return False
    return True


def _request_filters(request):
    form = ConversionFilterForm(request.GET)
    data = form.cleaned_data if form.is_valid() else {}
    defaults = {
        'section': 'overview',
        'report': 'events',
        'range': '30d',
        'start_date': None,
        'end_date': None,
        'compare': True,
        'event': '',
        'goal': None,
        'page': '',
        'source': '',
        'medium': '',
        'campaign': '',
        'device': '',
        'query': '',
        'event_type': '',
        'goal_status': '',
        'funnel_status': '',
        'rule_status': '',
        'sort': 'events',
        'direction': 'desc',
    }
    for key, value in defaults.items():
        if key not in data or data[key] in (None, ''):
            data[key] = value
    data['form'] = form
    return data


def _range_info(filters):
    today = timezone.localdate()
    key = filters['range']
    if key == 'today':
        start = end = today
    elif key == 'yesterday':
        start = end = today - timedelta(days=1)
    elif key == '7d':
        start, end = today - timedelta(days=6), today
    elif key == '90d':
        start, end = today - timedelta(days=89), today
    elif key == 'this_month':
        start, end = today.replace(day=1), today
    elif key == 'last_month':
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    elif key == 'custom':
        start = filters.get('start_date') or today - timedelta(days=29)
        end = filters.get('end_date') or today
        if end < start:
            start, end = end, start
        if (end - start).days > 365:
            start = end - timedelta(days=365)
    else:
        start, end = today - timedelta(days=29), today

    span = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=span - 1)
    return {
        'key': key,
        'start': start,
        'end': end,
        'previous_start': previous_start,
        'previous_end': previous_end,
        'span_days': span,
        'start_dt': _aware_midnight(start),
        'end_dt': _aware_midnight(end + timedelta(days=1)),
        'previous_start_dt': _aware_midnight(previous_start),
        'previous_end_dt': _aware_midnight(previous_end + timedelta(days=1)),
    }


def _apply_common_filters(queryset, filters, prefix=''):
    event_field = lambda name: f'{prefix}{name}'
    if filters.get('event'):
        queryset = queryset.filter(**{event_field('name'): filters['event']})
    if filters.get('event_type'):
        queryset = queryset.filter(**{event_field('event_type'): filters['event_type']})
    if filters.get('goal'):
        queryset = queryset.filter(**{event_field('goal'): filters['goal']})
    if filters.get('page'):
        queryset = queryset.filter(Q(**{event_field('path'): filters['page']}) | Q(**{event_field('landing_path'): filters['page']}))
    if filters.get('source'):
        queryset = queryset.filter(**{event_field('source_category'): filters['source']})
    if filters.get('medium'):
        queryset = queryset.filter(**{event_field('utm_medium'): filters['medium']})
    if filters.get('campaign'):
        queryset = queryset.filter(**{event_field('utm_campaign'): filters['campaign']})
    if filters.get('device'):
        queryset = queryset.filter(**{event_field('device_category'): filters['device']})
    if filters.get('query'):
        query = filters['query']
        queryset = queryset.filter(
            Q(**{f'{event_field("name")}__icontains': query})
            | Q(**{f'{event_field("description")}__icontains': query})
            | Q(**{f'{event_field("category")}__icontains': query})
            | Q(**{f'{event_field("path")}__icontains': query})
            | Q(**{f'{event_field("utm_campaign")}__icontains': query})
        )
    return queryset


def _event_queryset(range_info, filters, previous=False):
    start_key = 'previous_start_dt' if previous else 'start_dt'
    end_key = 'previous_end_dt' if previous else 'end_dt'
    queryset = ConversionEvent.objects.filter(
        occurred_at__gte=range_info[start_key],
        occurred_at__lt=range_info[end_key],
    )
    return _apply_common_filters(queryset, filters)


def _session_queryset(range_info, filters, previous=False):
    start_key = 'previous_start_dt' if previous else 'start_dt'
    end_key = 'previous_end_dt' if previous else 'end_dt'
    queryset = AnalyticsSession.objects.filter(
        started_at__gte=range_info[start_key],
        started_at__lt=range_info[end_key],
    )
    if filters.get('source'):
        queryset = queryset.filter(source_category=filters['source'])
    if filters.get('medium'):
        queryset = queryset.filter(utm_medium=filters['medium'])
    if filters.get('campaign'):
        queryset = queryset.filter(utm_campaign=filters['campaign'])
    if filters.get('device'):
        queryset = queryset.filter(device_category=filters['device'])
    if filters.get('page'):
        queryset = queryset.filter(Q(landing_path=filters['page']) | Q(exit_path=filters['page']))
    return queryset


def _pageview_queryset(range_info, filters, previous=False):
    start_key = 'previous_start_dt' if previous else 'start_dt'
    end_key = 'previous_end_dt' if previous else 'end_dt'
    queryset = PageView.objects.filter(
        viewed_at__gte=range_info[start_key],
        viewed_at__lt=range_info[end_key],
    )
    if filters.get('page'):
        queryset = queryset.filter(path=filters['page'])
    if filters.get('source'):
        queryset = queryset.filter(session__source_category=filters['source'])
    if filters.get('medium'):
        queryset = queryset.filter(session__utm_medium=filters['medium'])
    if filters.get('campaign'):
        queryset = queryset.filter(session__utm_campaign=filters['campaign'])
    if filters.get('device'):
        queryset = queryset.filter(session__device_category=filters['device'])
    return queryset


def _event_metrics(events, sessions):
    total = events.count()
    session_count = sessions.count()
    return {
        'conversions': total,
        'visitors': events.values('visitor_id').distinct().count(),
        'sessions': session_count,
        'goals': events.filter(goal__isnull=False).count(),
        'leads': events.filter(event_type='lead_generated').count(),
        'forms': events.filter(event_type__in=['form_submission', 'newsletter_signup', 'contact_request']).count(),
        'cta': events.filter(event_type='cta_click').count(),
        'rate': round((total / session_count) * 100, 2) if session_count else 0.0,
    }


def _kpi(label, current, previous, enabled, value=None, display=None, help_text='', rate=False):
    return {
        'label': label,
        'value': current if value is None else value,
        'display': display or str(current),
        'comparison': _comparison(current, previous, rate=rate, enabled=enabled),
        'help': help_text,
    }


def _event_chart(events, range_info):
    grain = 'daily' if range_info['span_days'] <= 31 else 'weekly' if range_info['span_days'] <= 120 else 'monthly'
    keys = _bucket_keys(range_info['start'], range_info['end'], grain)
    rows = (
        events.annotate(bucket=_trunc_expression('occurred_at', grain))
        .values('bucket')
        .annotate(total=Count('id'), visitors=Count('visitor_id', distinct=True))
    )
    row_map = {key.strftime('%Y-%m-%d'): row for key, row in zip(keys, [])}
    mapped = {}
    for row in rows:
        bucket = row['bucket']
        mapped[bucket.strftime('%Y-%m-%d') if hasattr(bucket, 'strftime') else str(bucket)] = row
    conversions = [mapped.get(key.strftime('%Y-%m-%d'), {}).get('total', 0) for key in keys]
    visitors = [mapped.get(key.strftime('%Y-%m-%d'), {}).get('visitors', 0) for key in keys]
    labels = [_bucket_label(key, grain) for key in keys]
    return {
        'labels': labels,
        'conversions': conversions,
        'visitors': visitors,
        'points': [
            {'label': label, 'events': total, 'visitors': count}
            for label, total, count in zip(labels, conversions, visitors)
        ],
        'max': max(conversions + visitors + [1]),
        'grain': grain,
    }


def _grouped_rows(events, field, sessions=None, limit=None):
    rows = (
        events.values(field)
        .annotate(total=Count('id'), visitors=Count('visitor_id', distinct=True))
        .order_by('-total')
    )
    totals = {}
    if sessions is not None:
        totals = dict(
            sessions.values(field)
            .annotate(total=Count('id'))
            .values_list(field, 'total')
        )
    result = []
    for row in rows:
        key = row[field] or 'Unattributed'
        denominator = totals.get(row[field], 0)
        result.append({
            'label': str(key),
            'key': str(row[field] or ''),
            'events': row['total'],
            'visitors': row['visitors'],
            'sessions': denominator,
            'rate': round((row['total'] / denominator) * 100, 2) if denominator else 0.0,
            'sort_key': str(key).lower(),
        })
    return result[:limit] if limit else result


def _recent_events(events, limit=8):
    return [
        {
            'id': event.pk,
            'key': event.event_key,
            'name': event.name,
            'event_type': event.get_event_type_display(),
            'path': event.path or '—',
            'occurred_at': event.occurred_at,
            'device': event.device_category,
            'source': event.source_category,
            'campaign': event.utm_campaign or '—',
            'visitor': event.privacy_safe_visitor,
            'session': event.privacy_safe_session,
            'goal': event.goal.name if event.goal_id else '—',
        }
        for event in events.select_related('goal', 'visitor', 'session').order_by('-occurred_at')[:limit]
    ]


def _paginate(request, rows, param='page'):
    paginator = Paginator(rows, PAGE_SIZE)
    page = paginator.get_page(request.GET.get(param))
    params = request.GET.copy()
    params.pop(param, None)
    return {'page': page, 'paginator': paginator, 'querystring': params.urlencode()}


def _goal_performance(events, sessions, pageviews, filters):
    total_sessions = sessions.count()
    rows = []
    for goal in ConversionGoal.objects.all():
        if goal.goal_type == 'Page Visit':
            target = ConversionGoal._path_value(goal.target_page or goal.target_url)
            matching_sessions = sessions.filter(Q(landing_path=target) | Q(exit_path=target)).count()
            matching_visitors = sessions.filter(Q(landing_path=target) | Q(exit_path=target)).values('visitor_id').distinct().count()
        else:
            goal_events = events.filter(goal=goal)
            matching_sessions = goal_events.values('session_id').distinct().count()
            matching_visitors = goal_events.values('visitor_id').distinct().count()
        if filters.get('goal_status') and goal.status != filters['goal_status']:
            continue
        rows.append({
            'id': goal.pk,
            'key': goal.goal_key,
            'name': goal.name,
            'type': goal.goal_type,
            'status': goal.status,
            'completions': matching_sessions,
            'visitors': matching_visitors,
            'rate': round((matching_sessions / total_sessions) * 100, 2) if total_sessions else 0.0,
        })
    return sorted(rows, key=lambda row: (-row['completions'], row['name']))


def _step_queryset(step, events, pageviews):
    if step.step_type == 'page_view':
        queryset = pageviews.filter(path=step.target_path)
        return queryset.values('visitor_id').annotate(first_at=Min('viewed_at'))
    queryset = events
    if step.goal_id:
        queryset = queryset.filter(goal=step.goal)
    elif step.event_name:
        queryset = queryset.filter(name=step.event_name)
    if step.target_path:
        queryset = queryset.filter(Q(path=step.target_path) | Q(landing_path=step.target_path))
    return queryset.values('visitor_id').annotate(first_at=Min('occurred_at'))


def _funnel_result(funnel, events, pageviews, sessions):
    steps = list(funnel.steps.select_related('goal').all())
    rows = []
    completed = {}
    entry_count = 0
    for index, step in enumerate(steps):
        step_visitors = {row['visitor_id']: row['first_at'] for row in _step_queryset(step, events, pageviews)}
        if index == 0:
            completed = step_visitors
            entry_count = len(completed)
        else:
            completed = {
                visitor_id: step_time
                for visitor_id, step_time in step_visitors.items()
                if visitor_id in completed and step_time >= completed[visitor_id]
            }
        count = len(completed)
        previous_count = rows[-1]['visitors'] if rows else count
        step_rate = round((count / previous_count) * 100, 1) if previous_count else 0.0
        drop_off = round(100 - step_rate, 1) if previous_count else 0.0
        overall = round((count / entry_count) * 100, 1) if entry_count else 0.0
        rows.append({
            'order': step.order,
            'label': step.label,
            'type': step.get_step_type_display(),
            'entered': len(step_visitors),
            'visitors': count,
            'step_rate': step_rate,
            'drop_off': drop_off,
            'overall': overall,
        })
    overall_rate = rows[-1]['overall'] if rows else 0.0
    return {
        'funnel': funnel,
        'steps': rows,
        'overall_rate': overall_rate,
        'sessions': sessions.count(),
    }


def _campaign_roi(events, sessions, range_info):
    rows = []
    for cost in CampaignCost.objects.select_related('campaign').all():
        campaign_events = events.filter(utm_campaign=cost.campaign.utm_campaign)
        campaign_sessions = sessions.filter(utm_campaign=cost.campaign.utm_campaign)
        conversions = campaign_events.count()
        leads = campaign_events.filter(event_type='lead_generated').count()
        multiplier = {
            'one_time': Decimal('1'),
            'daily': Decimal(str(range_info['span_days'])),
            'weekly': Decimal(str(range_info['span_days'])) / Decimal('7'),
            'monthly': Decimal(str(range_info['span_days'])) / Decimal('30'),
        }.get(cost.cost_period, Decimal('1'))
        period_cost = (cost.cost_amount * multiplier).quantize(Decimal('0.01'))
        rows.append({
            'id': cost.pk,
            'campaign': cost.campaign.name,
            'campaign_key': cost.campaign.campaign_key,
            'currency': cost.currency,
            'period': cost.get_cost_period_display(),
            'cost': cost.cost_amount,
            'period_cost': period_cost,
            'conversions': conversions,
            'leads': leads,
            'sessions': campaign_sessions.count(),
            'rate': round((conversions / campaign_sessions.count()) * 100, 2) if campaign_sessions.count() else 0.0,
            'cost_per_conversion': (period_cost / Decimal(conversions)).quantize(Decimal('0.01')) if conversions else None,
            'cost_per_lead': (period_cost / Decimal(leads)).quantize(Decimal('0.01')) if leads else None,
            'revenue': None,
            'roi': None,
        })
    return {'rows': rows, 'roi_available': False, 'revenue_available': False, 'note': REVENUE_NOTE}


def _report_rows(events, sessions, view, range_info):
    events = events.select_related('goal', 'session', 'visitor')
    if view == 'events':
        rows = _grouped_rows(events, 'name', limit=None)
        for row in rows:
            event_type = events.filter(name=row['key']).values('event_type').first()
            row['secondary'] = dict(ConversionEvent.EVENT_TYPE_CHOICES).get(event_type['event_type'], '') if event_type else ''
    elif view == 'pages':
        rows = _grouped_rows(events, 'path', limit=None)
        for row in rows:
            row['secondary'] = 'Page URL'
    elif view == 'sources':
        rows = _grouped_rows(events, 'source_category', sessions, limit=None)
        for row in rows:
            row['secondary'] = 'Traffic source'
    elif view == 'campaigns':
        rows = _grouped_rows(events, 'utm_campaign', sessions, limit=None)
        for row in rows:
            row['secondary'] = 'UTM campaign'
    elif view == 'devices':
        rows = _grouped_rows(events, 'device_category', sessions, limit=None)
        for row in rows:
            row['secondary'] = 'Device'
    elif view == 'landing_pages':
        rows = _grouped_rows(events, 'landing_path', sessions, limit=None)
        for row in rows:
            row['secondary'] = 'Landing page'
    else:
        chart = _event_chart(events, range_info)
        rows = [
            {
                'label': label,
                'events': total,
                'visitors': visitors,
                'secondary': 'Date bucket',
                'sort_key': label,
            }
            for label, total, visitors in zip(chart['labels'], chart['conversions'], chart['visitors'])
        ]
    for row in rows:
        row.setdefault('secondary', '')
        row.setdefault('sessions', 0)
        row.setdefault('rate', 0.0)
    return rows


def _sort_report(rows, filters):
    key_map = {
        'events': 'events',
        'visitors': 'visitors',
        'name': 'label',
        'page': 'label',
        'campaign': 'label',
        'source': 'label',
        'date': 'label',
    }
    key = key_map.get(filters['sort'], 'events')
    reverse = filters['direction'] == 'desc'
    return sorted(rows, key=lambda row: str(row.get(key, '')).lower() if key == 'label' else row.get(key, 0), reverse=reverse)


def build_conversion_tracking_config(request):
    rules = []
    for rule in TrackingRule.objects.filter(status='Active').select_related('goal'):
        rules.append({
            'selector': rule.selector,
            'eventType': rule.event_type,
            'eventName': rule.event_name,
            'goalKey': rule.goal.goal_key if rule.goal_id else '',
            'path': rule.target_path or request.path_info[:500],
        })
    try:
        from django.urls import NoReverseMatch, reverse
        endpoint = reverse('analytics_conversion')
    except NoReverseMatch:
        endpoint = '/conversion/beacon/'
    return {'endpoint': endpoint, 'rules': rules}


def create_conversion_event(session, *, name, event_type='custom_event', path='', description='', category='',
                            source_label='', dedupe_key='', value=None, goal=None, occurred_at=None):
    name = clean_event_name(name)
    if not is_safe_event_name(name):
        return None
    event_type = event_type if event_type in dict(ConversionEvent.EVENT_TYPE_CHOICES) else 'custom_event'
    path = clean_path(path)
    dedupe_key = ' '.join(str(dedupe_key or '').split())[:120]
    if not dedupe_key:
        dedupe_key = f'{name}|{event_type}|{path}|{int((occurred_at or timezone.now()).timestamp())}'
    if goal and goal.status != 'Active':
        goal = None
    if not goal:
        goal = ConversionGoal.objects.filter(status='Active', event_name=name).first() or ConversionGoal.objects.filter(
            status='Active', goal_type='Page Visit', target_page=path
        ).first()

    try:
        with transaction.atomic():
            exists = ConversionEvent.objects.filter(session=session, dedupe_key=dedupe_key).exists()
            if exists:
                return ConversionEvent.objects.get(session=session, dedupe_key=dedupe_key)
            return ConversionEvent.objects.create(
                session=session,
                visitor=session.visitor,
                goal=goal,
                name=name,
                event_type=event_type,
                description=description[:300],
                category=category[:120],
                source_label=source_label[:120],
                path=path,
                occurred_at=occurred_at or timezone.now(),
                dedupe_key=dedupe_key,
                value=value,
                source_category=session.source_category,
                utm_source=session.utm_source,
                utm_medium=session.utm_medium,
                utm_campaign=session.utm_campaign,
                utm_term=session.utm_term,
                utm_content=session.utm_content,
                device_category=session.device_category,
                landing_path=session.landing_path,
            )
    except (IntegrityError, ValueError):
        return ConversionEvent.objects.filter(session=session, dedupe_key=dedupe_key).first()


def record_conversion(request, *, name, event_type='custom_event', path=None, description='', category='',
                      dedupe_key='', value=None, goal=None):
    if not is_trackable_conversion_request(request):
        return None
    visitor_key = get_visitor_key(request)
    session_key = get_session_key(request, visitor_key)
    session = AnalyticsSession.objects.filter(
        session_key=session_key,
        visitor__visitor_key=visitor_key,
    ).first()
    if not session:
        return None
    return create_conversion_event(
        session,
        name=name,
        event_type=event_type,
        path=path or request.path_info[:500],
        description=description,
        category=category,
        dedupe_key=dedupe_key,
        value=value,
        goal=goal,
    )


def record_conversion_from_token(request):
    if not is_trackable_conversion_request(request):
        return None
    payload = decode_tracking_token(request.POST.get('token'))
    if not payload:
        return None
    session = AnalyticsSession.objects.filter(
        session_key=payload['s'],
        visitor__visitor_key=payload['v'],
    ).first()
    if not session:
        return None
    recent = ConversionEvent.objects.filter(
        session=session,
        occurred_at__gte=timezone.now() - timedelta(seconds=RATE_LIMIT_SECONDS),
    ).count()
    if recent >= RATE_LIMIT_COUNT:
        return None
    name = request.POST.get('event_name', '')
    event_type = request.POST.get('event_type', 'custom_event')
    dedupe_key = request.POST.get('dedupe_key', '') or request.POST.get('event_id', '')
    goal_key = request.POST.get('goal_key', '')
    goal = ConversionGoal.objects.filter(goal_key=goal_key, status='Active').first() if goal_key else None
    value = request.POST.get('value', '')
    try:
        value = Decimal(value) if value else None
    except (ValueError, TypeError):
        value = None
    return create_conversion_event(
        session,
        name=name,
        event_type=event_type,
        path=request.POST.get('path', payload.get('p', '')),
        description=request.POST.get('description', ''),
        category=request.POST.get('category', ''),
        source_label=request.POST.get('source', ''),
        dedupe_key=dedupe_key,
        value=value,
        goal=goal,
    )


def build_conversion_context(request):
    filters = _request_filters(request)
    range_info = _range_info(filters)
    events = _event_queryset(range_info, filters)
    previous_events = _event_queryset(range_info, filters, previous=True)
    sessions = _session_queryset(range_info, filters)
    previous_sessions = _session_queryset(range_info, filters, previous=True)
    pageviews = _pageview_queryset(range_info, filters)
    previous_pageviews = _pageview_queryset(range_info, filters, previous=True)

    current_metrics = _event_metrics(events, sessions)
    previous_metrics = _event_metrics(previous_events, previous_sessions)
    compare = filters['compare']

    kpis = [
        _kpi('Total Conversions', current_metrics['conversions'], previous_metrics['conversions'], compare),
        _kpi('Conversion Rate', current_metrics['rate'], previous_metrics['rate'], compare, display=f'{current_metrics["rate"]:.2f}%', rate=True),
        _kpi('Total Leads', current_metrics['leads'], previous_metrics['leads'], compare),
        _kpi('Form Submissions', current_metrics['forms'], previous_metrics['forms'], compare),
        _kpi('CTA Clicks', current_metrics['cta'], previous_metrics['cta'], compare),
        _kpi('Goal Completions', current_metrics['goals'], previous_metrics['goals'], compare),
    ]

    report_rows = _sort_report(_report_rows(events, sessions, filters['report'], range_info), filters)
    goals_qs = ConversionGoal.objects.all()
    if filters.get('goal_status'):
        goals_qs = goals_qs.filter(status=filters['goal_status'])
    if filters.get('query'):
        goals_qs = goals_qs.filter(Q(name__icontains=filters['query']) | Q(description__icontains=filters['query']))
    goal_performance = _goal_performance(events, sessions, pageviews, filters)
    performance_by_id = {row['id']: row for row in goal_performance}
    goals = list(goals_qs)
    for goal in goals:
        goal.performance = performance_by_id.get(goal.pk)

    funnels_qs = ConversionFunnel.objects.prefetch_related('steps').all()
    if filters.get('funnel_status'):
        funnels_qs = funnels_qs.filter(status=filters['funnel_status'])
    funnels = []
    for funnel in funnels_qs:
        current_result = _funnel_result(funnel, events, pageviews, sessions)
        previous_result = _funnel_result(funnel, previous_events, previous_pageviews, previous_sessions)
        current_result['previous_overall_rate'] = previous_result['overall_rate']
        current_result['comparison'] = _comparison(
            current_result['overall_rate'],
            previous_result['overall_rate'],
            rate=True,
            enabled=compare,
        )
        funnels.append(current_result)

    rules_qs = TrackingRule.objects.select_related('goal').all()
    if filters.get('rule_status'):
        rules_qs = rules_qs.filter(status=filters['rule_status'])
    if filters.get('query'):
        rules_qs = rules_qs.filter(Q(name__icontains=filters['query']) | Q(event_name__icontains=filters['query']))

    debug_rows = [
        {
            'id': event.pk,
            'key': event.event_key,
            'name': event.name,
            'event_type': event.get_event_type_display(),
            'path': event.path or '—',
            'occurred_at': event.occurred_at,
            'device': event.device_category,
            'source': event.source_category,
            'medium': event.utm_medium or '—',
            'campaign': event.utm_campaign or '—',
            'visitor': event.privacy_safe_visitor,
            'session': event.privacy_safe_session,
            'goal': event.goal.name if event.goal_id else '—',
            'status': 'Recorded',
        }
        for event in events.select_related('goal', 'visitor', 'session').order_by('-occurred_at')
    ]

    context = {
        'sections': CONVERSION_SECTIONS,
        'active_section': filters['section'],
        'filter_form': filters['form'],
        'filters': {key: value for key, value in filters.items() if key != 'form'},
        'range': range_info,
        'kpis': kpis,
        'metrics': current_metrics,
        'chart': _event_chart(events, range_info),
        'breakdowns': {
            'type': _grouped_rows(events, 'event_type', limit=8),
            'source': _grouped_rows(events, 'source_category', sessions, limit=8),
            'campaign': _grouped_rows(events, 'utm_campaign', sessions, limit=8),
            'page': _grouped_rows(events, 'path', limit=8),
        },
        'recent_events': _recent_events(events),
        'goals': goals,
        'goal_performance': goal_performance,
        'funnels': funnels,
        'reports': _paginate(request, report_rows, 'report_page'),
        'tracking_rules': list(rules_qs),
        'roi': _campaign_roi(events, sessions, range_info),
        'debug_events': _paginate(request, debug_rows, 'debug_page'),
        'privacy_note': PRIVACY_NOTE,
        'revenue_note': REVENUE_NOTE,
        'querystring': request.GET.urlencode(),
        'has_data': events.exists(),
    }
    return context


def build_event_detail_context(event, request):
    filters = _request_filters(request)
    range_info = _range_info(filters)
    sessions = _session_queryset(range_info, filters)
    return {
        'event': event,
        'metrics': _event_metrics(ConversionEvent.objects.filter(pk=event.pk), sessions),
        'privacy_safe_visitor': event.privacy_safe_visitor,
        'privacy_safe_session': event.privacy_safe_session,
        'attribution': {
            'source': event.source_category,
            'source_label': event.source_label or '—',
            'utm_source': event.utm_source or '—',
            'utm_medium': event.utm_medium or '—',
            'utm_campaign': event.utm_campaign or '—',
            'utm_content': event.utm_content or '—',
            'device': event.device_category,
            'landing_path': event.landing_path or '—',
        },
        'privacy_note': PRIVACY_NOTE,
    }
