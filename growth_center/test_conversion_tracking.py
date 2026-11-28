from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from growth_center.conversion import build_conversion_context, record_conversion
from growth_center.models import (
    AnalyticsSession,
    Campaign,
    CampaignCost,
    ConversionEvent,
    ConversionFunnel,
    ConversionFunnelStep,
    ConversionGoal,
    PageView,
    TrackingRule,
    Visitor,
)
from growth_center.tracking import build_tracking_token, get_session_key, get_visitor_key


class ConversionTrackingTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            'conversion-staff', 'conversion@example.com', 'password', is_staff=True
        )
        self.factory = RequestFactory()
        self.now = timezone.now()
        self.request = self.factory.get('/products/', REMOTE_ADDR='127.0.0.1')
        self.request.user = AnonymousUser()
        visitor_key = get_visitor_key(self.request)
        session_key = get_session_key(self.request, visitor_key)
        self.visitor = Visitor.objects.create(
            visitor_key=visitor_key, first_seen=self.now, last_seen=self.now
        )
        self.session_obj = AnalyticsSession.objects.create(
            session_key=session_key,
            visitor=self.visitor,
            started_at=self.now,
            last_seen_at=self.now,
            landing_path='/',
            exit_path='/',
            source_category='Organic Search',
            utm_source='google',
            utm_medium='organic',
            utm_campaign='spring-launch',
            device_category='Desktop',
        )
        PageView.objects.create(
            session=self.session_obj, visitor=self.visitor, path='/', viewed_at=self.now
        )
        self.url = reverse('admin:growth-center-conversion')
        self.client.force_login(self.staff)

    def _event(self, name='get_started', event_type='cta_click', dedupe_key='one', **kwargs):
        return ConversionEvent.objects.create(
            session=self.session_obj,
            visitor=self.visitor,
            name=name,
            event_type=event_type,
            path=kwargs.pop('path', '/products/'),
            dedupe_key=dedupe_key,
            occurred_at=self.now,
            source_category=self.session_obj.source_category,
            utm_source=self.session_obj.utm_source,
            utm_medium=self.session_obj.utm_medium,
            utm_campaign=self.session_obj.utm_campaign,
            device_category=self.session_obj.device_category,
            landing_path=self.session_obj.landing_path,
            **kwargs,
        )

    def test_dashboard_is_staff_only_and_exposes_all_sections(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.staff)
        sections = ['overview', 'events', 'goals', 'funnels', 'reports', 'setup', 'debugger']
        for section in sections:
            response = self.client.get(self.url, {'section': section})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Conversion Tracking')

    def test_dashboard_ajax_returns_partial_html(self):
        response = self.client.get(
            self.url, {'section': 'overview'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['section'], 'overview')
        self.assertIn('Conversions over time', payload['html'])

    def test_public_endpoint_rejects_bad_tokens_and_records_real_events(self):
        self.client.logout()
        endpoint = reverse('analytics_conversion')
        bad = self.client.post(endpoint, {'token': 'invalid', 'event_name': 'get_started'})
        self.assertEqual(bad.status_code, 204)
        self.assertEqual(ConversionEvent.objects.count(), 0)

        token = build_tracking_token(self.request)
        response = self.client.post(endpoint, {
            'token': token,
            'event_name': 'get_started',
            'event_type': 'cta_click',
            'dedupe_key': 'cta-1',
            'path': '/products/',
            'source': 'Explore Collection',
        })
        self.assertEqual(response.status_code, 200)
        event = ConversionEvent.objects.get()
        self.assertEqual(event.name, 'get_started')
        self.assertEqual(event.utm_campaign, 'spring-launch')
        self.assertEqual(event.source_label, 'Explore Collection')
        self.assertEqual(event.privacy_safe_visitor, self.visitor.visitor_key[:12])

        duplicate = self.client.post(endpoint, {
            'token': token,
            'event_name': 'get_started',
            'event_type': 'cta_click',
            'dedupe_key': 'cta-1',
        })
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(ConversionEvent.objects.count(), 1)

    def test_server_side_helper_tracks_only_trackable_requests_and_dedupes(self):
        event = record_conversion(
            self.request,
            name='contact_request',
            event_type='contact_request',
            dedupe_key='form-submit-42',
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.name, 'contact_request')
        duplicate = record_conversion(
            self.request,
            name='contact_request',
            event_type='contact_request',
            dedupe_key='form-submit-42',
        )
        self.assertEqual(duplicate.pk, event.pk)
        self.assertEqual(ConversionEvent.objects.count(), 1)

        dnt_request = self.factory.get('/support/', HTTP_DNT='1')
        dnt_request.user = AnonymousUser()
        self.assertIsNone(record_conversion(dnt_request, name='contact_request'))

        auth_request = self.factory.get('/support/')
        auth_request.user = self.staff
        self.assertIsNone(record_conversion(auth_request, name='contact_request'))

        admin_request = self.factory.get('/admin/')
        admin_request.user = AnonymousUser()
        self.assertIsNone(record_conversion(admin_request, name='contact_request'))

    def test_goal_editor_and_actions(self):
        response = self.client.post(reverse('admin:growth-center-conversion-goal-create'), {
            'name': 'Get Started',
            'description': 'Real CTA click',
            'goal_type': 'CTA Click',
            'event_name': 'get_started',
            'status': 'Active',
        })
        self.assertEqual(response.status_code, 302)
        goal = ConversionGoal.objects.get(name='Get Started')
        self.assertTrue(goal.goal_key.startswith('GOAL-'))

        action_url = reverse('admin:growth-center-conversion-goal-action', args=[goal.goal_key])
        self.client.post(action_url, {'action': 'toggle'})
        goal.refresh_from_db()
        self.assertEqual(goal.status, 'Inactive')

        self._event(name='get_started', goal=goal)
        context = build_conversion_context(
            self.factory.get(self.url, {'section': 'goals', 'range': 'today'})
        )
        self.assertEqual(context['metrics']['conversions'], 1)
        self.assertEqual(context['metrics']['goals'], 1)
        self.assertEqual(context['goal_performance'][0]['completions'], 1)

    def test_funnel_editor_and_sequential_calculation(self):
        response = self.client.post(reverse('admin:growth-center-conversion-funnel-create'), {
            'name': 'Activation',
            'description': 'Visit then convert',
            'status': 'Active',
            'steps-TOTAL_FORMS': '2',
            'steps-INITIAL_FORMS': '0',
            'steps-MIN_NUM_FORMS': '1',
            'steps-MAX_NUM_FORMS': '1000',
            'steps-0-order': '1',
            'steps-0-label': 'Home visit',
            'steps-0-step_type': 'page_view',
            'steps-0-target_path': '/',
            'steps-1-order': '2',
            'steps-1-label': 'Get started',
            'steps-1-step_type': 'conversion',
            'steps-1-event_name': 'get_started',
        })
        self.assertEqual(response.status_code, 302)
        funnel = ConversionFunnel.objects.get(name='Activation')
        self.assertEqual(funnel.steps.count(), 2)

        PageView.objects.create(
            session=self.session_obj, visitor=self.visitor, path='/support/', viewed_at=self.now
        )
        self._event(name='get_started', dedupe_key='funnel-1', path='/support/')
        context = build_conversion_context(
            self.factory.get(self.url, {'section': 'funnels', 'range': 'today'})
        )
        result = context['funnels'][0]
        self.assertEqual(result['steps'][0]['visitors'], 1)
        self.assertEqual(result['steps'][1]['visitors'], 1)
        self.assertEqual(result['overall_rate'], 100.0)
        self.assertIn('comparison', result)

    def test_tracking_rule_editor_config_and_validation(self):
        response = self.client.post(reverse('admin:growth-center-conversion-rule-create'), {
            'name': 'Get started rule',
            'selector': '[data-track-event="get_started"]',
            'event_type': 'cta_click',
            'event_name': 'get_started',
            'target_path': '/',
            'status': 'Active',
        })
        self.assertEqual(response.status_code, 302)
        rule = TrackingRule.objects.get(name='Get started rule')
        self.assertTrue(rule.rule_key.startswith('RULE-'))

        request = self.factory.get(self.url, {'section': 'setup', 'range': 'today'})
        context = build_conversion_context(request)
        self.assertEqual(context['tracking_rules'][0].event_name, 'get_started')

        invalid = self.client.post(reverse('admin:growth-center-conversion-rule-create'), {
            'name': 'Unsafe',
            'selector': 'body *',
            'event_type': 'cta_click',
            'event_name': 'unsafe_event',
            'status': 'Active',
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(TrackingRule.objects.filter(name='Unsafe').exists())

    def test_reports_filters_and_campaign_cost_without_revenue(self):
        campaign = Campaign.objects.create(
            name='Spring Launch',
            destination_url='https://example.com/',
            utm_source='google',
            utm_medium='cpc',
            utm_campaign='spring-launch',
            status='Active',
            created_by=self.staff,
        )
        CampaignCost.objects.create(campaign=campaign, cost_amount=Decimal('500.00'), currency='INR')
        self._event(name='get_started', event_type='lead_generated', dedupe_key='campaign-1')

        response = self.client.get(self.url, {
            'section': 'reports',
            'report': 'campaigns',
            'range': 'today',
            'sort': 'events',
            'direction': 'desc',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cost / conversion')
        self.assertContains(response, 'Not available')

        context = build_conversion_context(
            self.factory.get(self.url, {'section': 'reports', 'report': 'campaigns', 'range': 'today'})
        )
        self.assertEqual(context['roi']['rows'][0]['conversions'], 1)
        self.assertEqual(context['roi']['rows'][0]['cost_per_conversion'], Decimal('500.00'))
        self.assertFalse(context['roi']['roi_available'])

        filtered = build_conversion_context(
            self.factory.get(self.url, {'section': 'events', 'range': 'today', 'campaign': 'missing'})
        )
        self.assertEqual(filtered['metrics']['conversions'], 0)

    def test_event_detail_is_privacy_safe(self):
        event = self._event(name='get_started')
        detail_url = reverse('admin:growth-center-conversion-event-detail', args=[event.event_key])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, event.privacy_safe_visitor)
        self.assertNotContains(response, self.visitor.visitor_key)
        self.assertNotContains(response, self.session_obj.session_key)

    def test_public_templates_include_stable_tracking_attributes(self):
        template_root = Path(settings.BASE_DIR) / 'templates'
        detail_html = (template_root / 'products' / 'detail.html').read_text()
        self.assertIn('data-track-event="request_access"', detail_html)
        self.assertIn('data-track-event="secure_download"', detail_html)

        home_html = (template_root / 'core' / 'home.html').read_text()
        self.assertIn('data-track-event="cta_click"', home_html)

        tracker_js = (Path(settings.BASE_DIR) / 'static' / 'js' / 'growth_tracker.js').read_text()
        self.assertIn('data-track-event', tracker_js)
