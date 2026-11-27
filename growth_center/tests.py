import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AnalyticsSession, PageView, Visitor
from .services import SECTIONS, build_analytics_context
from .tracking import (
    build_tracking_token,
    classify_browser,
    classify_device,
    classify_source,
    country_code_from_request,
    decode_tracking_token,
    is_bot_request,
    track_page_view,
)


class SourceClassificationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_missing_referrer_is_direct(self):
        request = self.factory.get('/')
        self.assertEqual(classify_source(request), ('Direct', ''))

    def test_internal_referrer_is_direct(self):
        request = self.factory.get('/', HTTP_REFERER='http://testserver/support/')
        self.assertEqual(classify_source(request), ('Direct', ''))

    def test_search_referrer_is_organic(self):
        request = self.factory.get('/', HTTP_REFERER='https://www.google.com/search?q=themes')
        self.assertEqual(classify_source(request), ('Organic Search', 'google.com'))

    def test_social_referrer_is_social(self):
        request = self.factory.get('/', HTTP_REFERER='https://instagram.com/p/example/')
        self.assertEqual(classify_source(request), ('Social', 'instagram.com'))

    def test_external_referrer_is_referral(self):
        request = self.factory.get('/', HTTP_REFERER='https://example.com/article')
        self.assertEqual(classify_source(request), ('Referral', 'example.com'))

    def test_email_utm_is_email(self):
        request = self.factory.get('/?utm_source=newsletter&utm_medium=email')
        self.assertEqual(classify_source(request), ('Email', 'newsletter'))

    def test_paid_utm_is_paid_search(self):
        request = self.factory.get('/?utm_source=google&utm_medium=cpc&utm_campaign=launch')
        self.assertEqual(classify_source(request), ('Paid Search', 'google'))

    def test_generic_utm_is_campaign(self):
        request = self.factory.get('/?utm_source=partner&utm_medium=banner')
        self.assertEqual(classify_source(request), ('Campaign/UTM', 'partner'))

    def test_invalid_referrer_is_other(self):
        request = self.factory.get('/', HTTP_REFERER='https://')
        self.assertEqual(classify_source(request), ('Other', ''))

    def test_device_browser_and_bot_detection(self):
        request = self.factory.get(
            '/',
            HTTP_USER_AGENT='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1',
        )
        self.assertEqual(classify_device(request.META['HTTP_USER_AGENT']), 'Mobile')
        self.assertEqual(classify_browser(request.META['HTTP_USER_AGENT']), 'Safari')
        self.assertFalse(is_bot_request(request))

        bot_request = self.factory.get('/', HTTP_USER_AGENT='Googlebot/2.1')
        self.assertTrue(is_bot_request(bot_request))

    def test_country_header_is_validated(self):
        request = self.factory.get('/', HTTP_CF_IPCOUNTRY='us')
        self.assertEqual(country_code_from_request(request), 'US')
        request = self.factory.get('/', HTTP_CF_IPCOUNTRY='invalid')
        self.assertEqual(country_code_from_request(request), '')

    def test_tracking_token_round_trip(self):
        request = self.factory.get('/support/', HTTP_USER_AGENT='Mozilla/5.0')
        token = build_tracking_token(request)
        payload = decode_tracking_token(token)
        self.assertEqual(payload['p'], '/support/')
        self.assertEqual(len(payload['v']), 64)
        self.assertIsNone(decode_tracking_token(f'{token}tampered'))


class TrackingTests(TestCase):
    def test_public_html_page_is_tracked_once(self):
        response = self.client.get('/support/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AnalyticsSession.objects.count(), 1)
        self.assertEqual(PageView.objects.count(), 1)
        self.assertEqual(PageView.objects.first().path, '/support/')

        self.client.get('/support/')
        self.assertEqual(AnalyticsSession.objects.count(), 1)
        self.assertEqual(PageView.objects.count(), 1)
        self.assertEqual(AnalyticsSession.objects.first().page_view_count, 1)

    def test_new_page_in_session_increments_page_views(self):
        self.client.get('/support/')
        self.client.get('/privacy-policy/')
        session = AnalyticsSession.objects.first()
        self.assertEqual(session.page_view_count, 2)
        self.assertEqual(PageView.objects.count(), 2)

    def test_admin_and_download_paths_are_excluded(self):
        self.client.get('/admin/login/')
        self.client.get('/products/download/wordpress/1/')
        self.assertEqual(AnalyticsSession.objects.count(), 0)

    def test_ajax_and_do_not_track_are_excluded(self):
        self.client.get('/support/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.client.get('/support/', HTTP_DNT='1')
        self.assertEqual(AnalyticsSession.objects.count(), 0)

    def test_authenticated_visitors_are_excluded(self):
        user = get_user_model().objects.create_user(username='customer', password='pass12345')
        self.client.force_login(user)
        self.client.get('/support/')
        self.assertEqual(AnalyticsSession.objects.count(), 0)

    def test_non_html_responses_are_excluded(self):
        factory = RequestFactory()
        request = factory.get('/support/')
        request.user = get_user_model().objects.create_user(username='anon', password='pass12345')
        from django.http import HttpResponse

        response = HttpResponse('x', content_type='application/json')
        self.assertIsNone(track_page_view(request, response))
        self.assertEqual(AnalyticsSession.objects.count(), 0)

    def test_exit_beacon_records_duration_and_exit_path(self):
        response = self.client.get('/support/')
        self.assertEqual(response.status_code, 200)
        session = AnalyticsSession.objects.get()

        earlier = timezone.now() - timedelta(minutes=2)
        AnalyticsSession.objects.filter(pk=session.pk).update(started_at=earlier, last_seen_at=earlier)
        PageView.objects.filter(session=session).update(viewed_at=earlier)

        request = RequestFactory().get('/support/')
        token = build_tracking_token(request)
        beacon = self.client.post('/analytics/beacon/', {'token': token, 'duration_ms': '12000'})
        self.assertEqual(beacon.status_code, 204)

        session.refresh_from_db()
        view = PageView.objects.get(session=session)
        self.assertIsNotNone(session.ended_at)
        self.assertEqual(session.duration_seconds, 12)
        self.assertEqual(session.exit_path, '/support/')
        self.assertEqual(view.duration_seconds, 12)

    def test_beacon_rejects_tampered_tokens(self):
        self.client.get('/support/')
        session = AnalyticsSession.objects.get()
        response = self.client.post('/analytics/beacon/', {'token': 'invalid.token', 'duration_ms': '12000'})
        self.assertEqual(response.status_code, 204)
        session.refresh_from_db()
        self.assertIsNone(session.ended_at)

    def test_trusted_country_header_is_stored(self):
        self.client.get('/support/', HTTP_CF_IPCOUNTRY='us')
        session = AnalyticsSession.objects.get()
        self.assertEqual(session.country_code, 'US')
        self.assertEqual(session.visitor.country_code, 'US')

    def test_beacon_requires_post(self):
        response = self.client.get('/analytics/beacon/')
        self.assertEqual(response.status_code, 405)


class AnalyticsServiceTests(TestCase):
    def create_visit(
        self,
        when,
        visitor_key,
        session_key,
        path,
        source='Direct',
        extra_paths=(),
        is_returning=False,
        device='Desktop',
        country='',
        duration=None,
        utm_source='',
        utm_medium='',
        utm_campaign='',
        source_label='',
        exit_path=None,
    ):
        visitor, _ = Visitor.objects.get_or_create(
            visitor_key=visitor_key,
            defaults={'first_seen': when, 'last_seen': when, 'country_code': country},
        )
        session = AnalyticsSession.objects.create(
            session_key=session_key,
            visitor=visitor,
            started_at=when,
            last_seen_at=when,
            ended_at=when + timedelta(seconds=duration) if duration is not None else None,
            duration_seconds=duration,
            page_view_count=1 + len(extra_paths),
            is_returning=is_returning,
            source_category=source,
            source_label=source_label,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            landing_path=path,
            exit_path=exit_path or path,
            device_category=device,
            country_code=country,
        )
        PageView.objects.create(session=session, visitor=visitor, path=path, viewed_at=when)
        for index, extra_path in enumerate(extra_paths):
            PageView.objects.create(
                session=session,
                visitor=visitor,
                path=extra_path,
                from_path=path if index == 0 else '',
                viewed_at=when + timedelta(seconds=index + 1),
            )
        return session

    def context_for(self, query=''):
        request = RequestFactory().get(f'/admin/growth-center/analytics/{query}')
        return build_analytics_context(request)

    def test_metrics_and_comparisons_use_real_data(self):
        now = timezone.now()
        self.create_visit(now - timedelta(days=1), 'visitor-a', uuid.uuid4().hex, '/', 'Direct')
        self.create_visit(
            now - timedelta(days=1),
            'visitor-a',
            uuid.uuid4().hex,
            '/support/',
            'Organic Search',
            extra_paths=('/terms-conditions/',),
            is_returning=True,
        )
        self.create_visit(now - timedelta(days=10), 'visitor-old', uuid.uuid4().hex, '/', 'Social')

        context = self.context_for('?range=7d')
        self.assertEqual(context['kpis']['visitors']['value'], 2)
        self.assertEqual(context['kpis']['unique_visitors']['value'], 1)
        self.assertEqual(context['kpis']['page_views']['value'], 3)
        self.assertEqual(context['kpis']['bounce_rate']['value'], 50.0)
        self.assertEqual(context['bounce']['bounced_sessions'], 1)
        self.assertEqual(len(context['charts']['traffic']['labels']), 7)
        self.assertEqual(sum(context['charts']['growth']['new']), 1)
        self.assertEqual(sum(context['charts']['growth']['returning']), 1)
        source_counts = {row['category']: row['count'] for row in context['traffic_sources']}
        self.assertEqual(source_counts['Direct'], 1)
        self.assertEqual(source_counts['Organic Search'], 1)

    def test_source_filter_changes_all_metrics(self):
        now = timezone.now()
        self.create_visit(now - timedelta(days=1), 'visitor-a', uuid.uuid4().hex, '/', 'Direct')
        self.create_visit(
            now - timedelta(days=1),
            'visitor-b',
            uuid.uuid4().hex,
            '/support/',
            'Organic Search',
            extra_paths=('/terms-conditions/',),
        )

        context = self.context_for('?range=7d&source=Organic+Search')
        self.assertEqual(context['kpis']['visitors']['value'], 1)
        self.assertEqual(context['kpis']['page_views']['value'], 2)
        self.assertEqual(context['top_pages'][0]['path'], '/support/')

    def test_custom_range_excludes_older_sessions(self):
        now = timezone.now()
        self.create_visit(now - timedelta(days=3), 'visitor-a', uuid.uuid4().hex, '/')
        self.create_visit(now - timedelta(days=40), 'visitor-b', uuid.uuid4().hex, '/')
        start = (timezone.localdate() - timedelta(days=6)).isoformat()
        end = timezone.localdate().isoformat()

        context = self.context_for(f'?range=custom&start={start}&end={end}')
        self.assertEqual(context['kpis']['visitors']['value'], 1)

        wide_start = (timezone.localdate() - timedelta(days=60)).isoformat()
        context = self.context_for(f'?range=custom&start={wide_start}&end={end}')
        self.assertEqual(context['kpis']['visitors']['value'], 2)

    def test_top_page_sorting(self):
        now = timezone.now()
        self.create_visit(now - timedelta(days=1), 'visitor-a', uuid.uuid4().hex, '/support/', extra_paths=('/support/', '/support/'))
        self.create_visit(now - timedelta(days=1), 'visitor-b', uuid.uuid4().hex, '/')

        by_views = self.context_for('?range=7d&sort=views')
        self.assertEqual(by_views['top_pages'][0]['path'], '/support/')

        by_path = self.context_for('?range=7d&sort=path')
        self.assertEqual(by_path['top_pages'][0]['path'], '/')

    def test_device_filter_changes_metrics(self):
        now = timezone.now()
        self.create_visit(now - timedelta(days=1), 'desktop', uuid.uuid4().hex, '/', device='Desktop')
        self.create_visit(
            now - timedelta(days=1),
            'mobile',
            uuid.uuid4().hex,
            '/support/',
            device='Mobile',
            extra_paths=('/terms-conditions/',),
        )

        context = self.context_for('?range=7d&device=Mobile')
        self.assertEqual(context['kpis']['visitors']['value'], 1)
        self.assertEqual(context['kpis']['page_views']['value'], 2)
        self.assertEqual(context['device_breakdown'][0]['category'], 'Mobile')

    def test_landing_filter_changes_metrics(self):
        now = timezone.now()
        self.create_visit(now - timedelta(days=1), 'home', uuid.uuid4().hex, '/')
        self.create_visit(
            now - timedelta(days=1),
            'support',
            uuid.uuid4().hex,
            '/support/',
            extra_paths=('/terms-conditions/',),
        )

        context = self.context_for('?range=7d&landing=/support/')
        self.assertEqual(context['kpis']['visitors']['value'], 1)
        self.assertEqual(context['kpis']['page_views']['value'], 2)
        self.assertEqual(context['landing_page'][0]['path'], '/support/')

    def test_query_filters_reports(self):
        now = timezone.now()
        self.create_visit(now - timedelta(days=1), 'home', uuid.uuid4().hex, '/')
        self.create_visit(now - timedelta(days=1), 'support', uuid.uuid4().hex, '/support/')

        context = self.context_for('?range=7d&q=support')
        self.assertEqual([row['path'] for row in context['top_pages']], ['/support/'])

    def test_page_detail_uses_selected_page_only(self):
        now = timezone.now()
        self.create_visit(now - timedelta(days=1), 'first', uuid.uuid4().hex, '/', extra_paths=('/support/',))
        self.create_visit(now - timedelta(days=1), 'second', uuid.uuid4().hex, '/privacy-policy/')

        context = self.context_for('?range=7d&section=pages&page_path=/support/')
        detail = context['page_detail']
        self.assertEqual(detail['path'], '/support/')
        self.assertEqual(detail['metrics']['page_views'], 1)
        self.assertEqual(detail['metrics']['total_sessions'], 1)
        self.assertEqual(sum(detail['charts']['traffic']['page_views']), 1)

    def test_geography_only_uses_reliable_country_header(self):
        now = timezone.now()
        self.create_visit(now - timedelta(days=1), 'us', uuid.uuid4().hex, '/', country='US')
        self.create_visit(now - timedelta(days=1), 'de', uuid.uuid4().hex, '/support/', country='DE')
        self.create_visit(now - timedelta(days=1), 'unknown', uuid.uuid4().hex, '/terms-conditions/')

        context = self.context_for('?range=7d&section=geography')
        labels = {row['label'] for row in context['geography']}
        self.assertEqual(labels, {'US', 'DE'})

    def test_compare_can_be_disabled(self):
        now = timezone.now()
        self.create_visit(now - timedelta(days=1), 'current', uuid.uuid4().hex, '/')
        self.create_visit(now - timedelta(days=10), 'previous', uuid.uuid4().hex, '/')

        enabled = self.context_for('?range=7d')
        disabled = self.context_for('?range=7d&compare=0')
        self.assertIn('+', enabled['kpis']['visitors']['comparison']['label'])
        self.assertEqual(disabled['kpis']['visitors']['comparison']['label'], 'Comparison off')

    def test_acquisition_and_behavior_reports_use_real_data(self):
        now = timezone.now()
        self.create_visit(
            now - timedelta(days=1),
            'email',
            uuid.uuid4().hex,
            '/',
            source='Email',
            extra_paths=('/support/',),
            duration=45,
            utm_source='newsletter',
            utm_medium='email',
            utm_campaign='spring',
            source_label='newsletter',
        )
        self.create_visit(
            now - timedelta(days=1),
            'referral',
            uuid.uuid4().hex,
            '/privacy-policy/',
            source='Referral',
            source_label='example.com',
        )

        context = self.context_for('?range=7d')
        self.assertIn('newsletter', context['acquisition']['campaigns'][0]['label'])
        referrers = [row['label'] for row in context['acquisition']['referrers']]
        self.assertIn('example.com', referrers)
        self.assertEqual(context['audience']['duration_bands'][2]['count'], 1)
        navigation = context['behavior']['navigation']
        self.assertTrue(any(row['from_title'] == 'Home' and row['to_title'] == 'Support' for row in navigation))


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='growthadmin',
            email='admin@example.com',
            password='pass12345',
        )
        self.url = reverse('admin:growth-center-analytics')

    def test_anonymous_user_is_redirected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_superuser_sees_dashboard(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Marketing Analytics')
        self.assertContains(response, 'Traffic Overview')
        self.assertContains(response, 'GROWTH CENTER')

    def test_ajax_request_returns_partial_html(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Traffic Overview', response.json()['html'])
        self.assertIn('range', response.json())

    def test_dashboard_loads_analytics_assets_and_subnavigation(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, 'growth_analytics.css')
        self.assertContains(response, 'growth_analytics.js')
        self.assertContains(response, 'Landing Pages')
        self.assertContains(response, 'Geography')

    def test_section_query_switches_partial(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url, {'section': 'landing'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Landing Pages', response.json()['html'])

    def test_all_sections_render(self):
        self.client.force_login(self.user)
        for key, _label in SECTIONS:
            response = self.client.get(self.url, {'section': key}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertEqual(response.status_code, 200, key)
            self.assertTrue(response.json()['html'])
