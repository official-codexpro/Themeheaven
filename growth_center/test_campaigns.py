import json
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from .campaign_urls import build_campaign_url, strip_utm_params
from .models import Campaign


def make_campaign(**overrides):
    data = {
        'name': 'Summer Sale',
        'destination_url': 'https://themehaven.in/products/?ref=home#pricing',
        'utm_source': 'google',
        'utm_medium': 'cpc',
        'utm_campaign': 'summer_sale_2026',
        'status': 'Active',
    }
    data.update(overrides)
    return Campaign.objects.create(**data)


class CampaignUrlBuilderTests(TestCase):
    def test_build_url_preserves_existing_params_and_replaces_utm_values(self):
        url, error = build_campaign_url(
            'https://themehaven.in/products/?ref=home&utm_source=old&utm_campaign=old#pricing',
            'newsletter',
            'email',
            'spring_launch',
            'header_link',
            'button_a',
        )
        self.assertEqual(error, '')
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, 'https')
        self.assertEqual(parsed.netloc, 'themehaven.in')
        self.assertEqual(parsed.path, '/products/')
        self.assertEqual(parsed.fragment, 'pricing')
        self.assertEqual(query['ref'], ['home'])
        self.assertEqual(query['utm_source'], ['newsletter'])
        self.assertEqual(query['utm_medium'], ['email'])
        self.assertEqual(query['utm_campaign'], ['spring_launch'])
        self.assertEqual(query['utm_term'], ['header_link'])
        self.assertEqual(query['utm_content'], ['button_a'])

    def test_strip_utm_params_keeps_custom_query_and_fragment(self):
        result = strip_utm_params('https://example.com/page?ref=partner&utm_source=facebook#section')
        self.assertEqual(result, 'https://example.com/page?ref=partner#section')

    def test_build_url_rejects_invalid_destination(self):
        url, error = build_campaign_url('example.com/page', 'google', 'cpc', 'launch')
        self.assertEqual(url, '')
        self.assertIn('http(s)', error)

    def test_build_url_requires_source_medium_and_campaign(self):
        _url, error = build_campaign_url('https://example.com/', '', 'cpc', 'launch')
        self.assertIn('Source', error)
        _url, error = build_campaign_url('https://example.com/', 'google', '', 'launch')
        self.assertIn('Medium', error)
        _url, error = build_campaign_url('https://example.com/', 'google', 'cpc', '')
        self.assertIn('Campaign', error)


class CampaignModelTests(TestCase):
    def test_campaign_gets_unique_public_key(self):
        first = make_campaign()
        second = make_campaign(name='Autumn Sale', utm_campaign='autumn_sale_2026')
        self.assertTrue(first.campaign_key.startswith('CMP-'))
        self.assertNotEqual(first.campaign_key, second.campaign_key)

    def test_campaign_rejects_end_date_before_start_date(self):
        campaign = Campaign(
            name='Invalid Schedule',
            destination_url='https://example.com/',
            utm_source='google',
            utm_medium='cpc',
            utm_campaign='invalid_schedule',
            start_date='2026-10-10',
            end_date='2026-10-01',
        )
        with self.assertRaises(ValidationError):
            campaign.full_clean()


class CampaignViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='campaignadmin',
            email='campaign@example.com',
            password='pass12345',
        )
        self.client.force_login(self.user)

    def visit_with_utm(self, campaign):
        client = Client()
        return client.get('/support/', {
            'utm_source': campaign.utm_source,
            'utm_medium': campaign.utm_medium,
            'utm_campaign': campaign.utm_campaign,
        })

    def test_dashboard_uses_real_campaign_traffic(self):
        campaign = make_campaign()
        self.assertEqual(self.visit_with_utm(campaign).status_code, 200)

        response = self.client.get(reverse('admin:growth-center-campaigns'), {'section': 'overview'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Campaigns / UTM Manager')
        self.assertContains(response, 'Total Campaign Visits')
        self.assertContains(response, campaign.name)
        self.assertEqual(response.context['campaign_count'], 1)
        self.assertEqual(response.context['visits_count'], 1)
        self.assertEqual(response.context['visitors_count'], 1)

    def test_dashboard_filters_and_ajax_partial_work(self):
        make_campaign(name='Paused Campaign', status='Paused')
        make_campaign(name='Active Campaign', utm_campaign='active_campaign', status='Active')

        response = self.client.get(reverse('admin:growth-center-campaigns'), {
            'section': 'campaigns',
            'status': 'Paused',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paused Campaign')
        self.assertNotContains(response, 'Active Campaign</a>')

        ajax = self.client.get(reverse('admin:growth-center-campaigns'), {
            'section': 'campaigns',
            'status': 'Paused',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(ajax.status_code, 200)
        payload = json.loads(ajax.content.decode())
        self.assertIn('Campaign Management', payload['html'])

    def test_builder_creates_campaign_and_clean_destination(self):
        response = self.client.post(reverse('admin:growth-center-campaign-create'), {
            'name': 'Newsletter Launch',
            'description': 'Email launch campaign',
            'objective': 'traffic',
            'destination_url': 'https://example.com/offers/?ref=email&utm_source=old#signup',
            'utm_source': 'newsletter',
            'utm_medium': 'email',
            'utm_campaign': 'newsletter_launch',
            'utm_term': '',
            'utm_content': 'footer_cta',
            'start_date': '2026-11-01',
            'end_date': '2026-11-30',
            'status': 'Active',
            'notes': 'Internal note',
        })
        campaign = Campaign.objects.get(utm_campaign='newsletter_launch')
        self.assertRedirects(response, reverse('admin:growth-center-campaign-detail', args=[campaign.campaign_key]))
        self.assertEqual(campaign.destination_url, 'https://example.com/offers/?ref=email#signup')
        self.assertEqual(campaign.created_by, self.user)
        self.assertEqual(campaign.status, 'Active')

    def test_builder_rejects_duplicate_utm_campaign(self):
        make_campaign()
        response = self.client.post(reverse('admin:growth-center-campaign-create'), {
            'name': 'Duplicate UTM',
            'destination_url': 'https://example.com/',
            'utm_source': 'google',
            'utm_medium': 'cpc',
            'utm_campaign': 'summer_sale_2026',
            'status': 'Draft',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors['utm_campaign'])
        self.assertEqual(Campaign.objects.count(), 1)

    def test_detail_page_shows_real_campaign_performance(self):
        campaign = make_campaign()
        self.assertEqual(self.visit_with_utm(campaign).status_code, 200)

        response = self.client.get(reverse('admin:growth-center-campaign-detail', args=[campaign.campaign_key]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Campaign Performance')
        self.assertContains(response, 'utm_campaign=summer_sale_2026')
        self.assertContains(response, '/support/')
        self.assertTrue(response.context['has_data'])

    def test_duplicate_pause_resume_archive_and_delete_actions(self):
        campaign = make_campaign()

        response = self.client.post(reverse('admin:growth-center-campaign-action', args=[campaign.campaign_key]), {
            'action': 'duplicate',
        })
        copy = Campaign.objects.get(utm_campaign='summer_sale_2026-copy')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(copy.status, 'Draft')
        self.assertEqual(copy.name, 'Summer Sale (Copy)')

        self.client.post(reverse('admin:growth-center-campaign-action', args=[campaign.campaign_key]), {'action': 'pause'})
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'Paused')

        self.client.post(reverse('admin:growth-center-campaign-action', args=[campaign.campaign_key]), {'action': 'resume'})
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'Active')

        self.client.post(reverse('admin:growth-center-campaign-action', args=[campaign.campaign_key]), {'action': 'archive'})
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'Archived')

        response = self.client.post(reverse('admin:growth-center-campaign-action', args=[campaign.campaign_key]), {
            'action': 'delete',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Campaign.objects.filter(pk=campaign.pk).exists())

        self.client.post(reverse('admin:growth-center-campaign-action', args=[campaign.campaign_key]), {
            'action': 'delete',
            'confirm': '1',
        })
        self.assertFalse(Campaign.objects.filter(pk=campaign.pk).exists())

    def test_analytics_acquisition_links_to_campaign_detail(self):
        campaign = make_campaign()
        self.assertEqual(self.visit_with_utm(campaign).status_code, 200)

        response = self.client.get(reverse('admin:growth-center-analytics'), {'section': 'acquisition'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('admin:growth-center-campaign-detail', args=[campaign.campaign_key]))

    def test_campaign_pages_require_staff_access(self):
        self.client.logout()
        response = self.client.get(reverse('admin:growth-center-campaigns'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

        response = self.client.post(reverse('admin:growth-center-campaign-create'), {})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)
