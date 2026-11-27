import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AnalyticsSession, PageView, Visitor
from .services import build_analytics_context
from .tracking import classify_source, track_page_view


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

    def test_utm_referrer_is_campaign(self):
        request = self.factory.get('/?utm_source=newsletter&utm_medium=email')
        self.assertEqual(classify_source(request), ('Campaign/UTM', 'newsletter'))

    def test_invalid_referrer_is_other(self):
        request = self.factory.get('/', HTTP_REFERER='https://')
        self.assertEqual(classify_source(request), ('Other', ''))


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


class AnalyticsServiceTests(TestCase):
    def create_visit(self, when, visitor_key, session_key, path, source='Direct', extra_paths=(), is_returning=False):
        visitor, _ = Visitor.objects.get_or_create(
            visitor_key=visitor_key,
            defaults={'first_seen': when, 'last_seen': when},
        )
        session = AnalyticsSession.objects.create(
            session_key=session_key,
            visitor=visitor,
            started_at=when,
            last_seen_at=when,
            page_view_count=1 + len(extra_paths),
            is_returning=is_returning,
            source_category=source,
            landing_path=path,
        )
        PageView.objects.create(session=session, visitor=visitor, path=path, viewed_at=when)
        for index, extra_path in enumerate(extra_paths):
            PageView.objects.create(
                session=session,
                visitor=visitor,
                path=extra_path,
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
