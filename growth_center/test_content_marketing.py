from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .campaign_urls import build_campaign_url
from .content_forms import ContentItemForm
from .models import (
    AnalyticsSession,
    Campaign,
    ContentBrief,
    ContentCategory,
    ContentIdea,
    ContentRefreshTask,
    ContentTag,
    ContentTemplate,
    MarketingContent,
    SocialPost,
    Visitor,
)


def make_campaign(**overrides):
    data = {
        'name': 'Autumn Launch',
        'destination_url': 'https://themehaven.in/products/?ref=home#pricing',
        'utm_source': 'newsletter',
        'utm_medium': 'email',
        'utm_campaign': 'autumn_launch',
        'status': 'Active',
    }
    data.update(overrides)
    return Campaign.objects.create(**data)


def make_content(**overrides):
    data = {
        'title': 'Theme Care Guide',
        'slug': 'theme-care-guide',
        'content_type': 'Guide',
        'body': 'Step one. Step two. Step three.',
        'primary_keyword': 'theme care',
        'seo_title': 'Theme Care Guide | ThemeHaven',
        'meta_description': 'A practical guide to keeping your theme fast and reliable.',
        'heading_structure': 'H1: Theme Care\nH2: Updates',
        'internal_links': '/support/',
        'image_alt_text': 'Theme settings dashboard',
        'cta': 'Explore the product catalogue.',
        'status': 'Draft',
    }
    data.update(overrides)
    return MarketingContent.objects.create(**data)


class ContentMarketingModelTests(TestCase):
    def test_starter_templates_are_real_structures_not_published_content(self):
        names = set(ContentTemplate.objects.values_list('name', flat=True))
        self.assertIn('SEO Blog Post', names)
        self.assertIn('Case Study', names)
        self.assertIn('Landing Page', names)
        self.assertEqual(MarketingContent.objects.count(), 0)

    def test_categories_tags_and_keywords_are_grouped(self):
        category = ContentCategory.objects.create(name='Documentation')
        tag = ContentTag.objects.create(name='Beginner')
        item = make_content(category=category, status='Published', publication_url='https://themehaven.in/guide/')
        item.tags.add(tag)

        self.assertEqual(category.slug, 'documentation')
        self.assertEqual(tag.slug, 'beginner')
        self.assertIn(tag, item.tags.all())
        self.assertEqual(item.word_count, 6)
        self.assertEqual(item.reading_time, 1)

    def test_overdue_and_seo_checklist_reflect_real_fields(self):
        item = make_content(status='Planned', target_publication_date=timezone.localdate() - timedelta(days=1))
        self.assertTrue(item.is_overdue)
        checks = item.seo_checklist()
        self.assertTrue(checks['primary_keyword'])
        self.assertTrue(checks['content_preview'])

        empty = MarketingContent.objects.create(title='Empty', status='Idea')
        self.assertFalse(empty.seo_checklist()['primary_keyword'])
        self.assertFalse(empty.is_overdue)


class ContentItemFormTests(TestCase):
    def payload(self, **overrides):
        data = {
            'title': 'Real Content',
            'content_type': 'Blog Post',
            'body': 'Verified body content.',
            'status': 'Draft',
            'priority': 'Medium',
        }
        data.update(overrides)
        return data

    def test_publishing_requires_url_and_actual_confirmation(self):
        form = ContentItemForm(self.payload(status='Published'))
        self.assertFalse(form.is_valid())
        self.assertIn('publication_url', form.errors)
        self.assertIn('publication_confirmed', form.errors)

        form = ContentItemForm(self.payload(status='Published', publication_url='https://themehaven.in/real-content/', publication_confirmed='on'))
        self.assertTrue(form.is_valid(), form.errors)

    def test_scheduled_content_requires_date(self):
        form = ContentItemForm(self.payload(status='Scheduled'))
        self.assertFalse(form.is_valid())
        self.assertIn('target_publication_date', form.errors)

    def test_publish_confirmation_sets_real_published_timestamp(self):
        form = ContentItemForm(self.payload(status='Published', publication_url='https://themehaven.in/real-content/', publication_confirmed='on'))
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save()
        self.assertIsNotNone(item.published_at)


class ContentIdeaWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('contentadmin', 'content@example.com', 'pass12345')
        self.client = Client()
        self.client.force_login(self.user)

    def test_conversion_creates_content_once(self):
        idea = ContentIdea.objects.create(
            title='Explain theme updates',
            description='Cover the update flow.',
            content_type='Tutorial',
            potential_keywords='theme updates, wordpress updates',
            priority='High',
        )
        url = reverse('admin:growth-center-content-idea-action', args=[idea.idea_key])
        response = self.client.post(url, {'action': 'convert'})

        self.assertEqual(response.status_code, 302)
        idea.refresh_from_db()
        self.assertTrue(idea.is_used)
        self.assertIsNotNone(idea.converted_content)
        self.assertEqual(idea.converted_content.status, 'Planned')
        self.assertEqual(idea.converted_content.primary_keyword, 'theme updates')

        self.client.post(url, {'action': 'convert'})
        self.assertEqual(MarketingContent.objects.filter(title=idea.title).count(), 1)


class ContentViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('contentadmin', 'content@example.com', 'pass12345')
        self.client = Client()
        self.client.force_login(self.user)
        self.campaign = make_campaign()
        self.item = make_content(
            campaign=self.campaign,
            status='Published',
            publication_url='https://themehaven.in/guide/',
            target_publication_date=timezone.localdate() - timedelta(days=2),
        )
        self.item.published_at = timezone.now()
        self.item.save(update_fields=['published_at'])

    def test_dashboard_renders_every_internal_section(self):
        for section in ('overview', 'calendar', 'library', 'ideas', 'briefs', 'templates', 'performance', 'refresh'):
            response = self.client.get(reverse('admin:growth-center-content'), {'section': section})
            self.assertEqual(response.status_code, 200, section)
            self.assertContains(response, 'Content Marketing')

        response = self.client.get(reverse('admin:growth-center-content'), {'section': 'performance'})
        self.assertContains(response, 'Search Console is not connected')
        self.assertContains(response, self.item.title)

    def test_ajax_partial_returns_section_html(self):
        response = self.client.get(
            reverse('admin:growth-center-content'),
            {'section': 'library', 'format': 'json'},
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['section'], 'library')
        self.assertIn(self.item.title, payload['html'])

    def test_editor_creates_and_publishes_real_content(self):
        response = self.client.post(reverse('admin:growth-center-content-create'), {
            'title': 'New guide',
            'content_type': 'Guide',
            'status': 'Published',
            'priority': 'High',
            'body': 'Checked guidance.',
            'publication_url': 'https://themehaven.in/new-guide/',
            'publication_confirmed': 'on',
        })
        item = MarketingContent.objects.get(title='New guide')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(item.status, 'Published')
        self.assertIsNotNone(item.published_at)

    def test_editor_rejects_unconfirmed_publish(self):
        response = self.client.post(reverse('admin:growth-center-content-create'), {
            'title': 'Fake guide',
            'content_type': 'Guide',
            'status': 'Published',
            'body': 'Checked guidance.',
            'publication_url': 'https://themehaven.in/fake-guide/',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MarketingContent.objects.filter(title='Fake guide').exists())

    def test_detail_shows_workflow_and_seo_checklist(self):
        response = self.client.get(reverse('admin:growth-center-content-detail', args=[self.item.content_key]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.item.title)
        self.assertContains(response, 'SEO checklist')

    def test_calendar_reschedule_moves_planned_content(self):
        item = make_content(title='Planned guide', status='Planned', target_publication_date=timezone.localdate())
        url = reverse('admin:growth-center-content-calendar-reschedule')
        response = self.client.post(url, {
            'key': item.content_key,
            'date': (timezone.localdate() + timedelta(days=3)).isoformat(),
        }, headers={'X-Requested-With': 'XMLHttpRequest'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        item.refresh_from_db()
        self.assertEqual(item.status, 'Scheduled')
        self.assertEqual(item.target_publication_date, timezone.localdate() + timedelta(days=3))

    def test_published_content_cannot_be_rescheduled(self):
        response = self.client.post(reverse('admin:growth-center-content-calendar-reschedule'), {
            'key': self.item.content_key,
            'date': timezone.localdate().isoformat(),
        }, headers={'X-Requested-With': 'XMLHttpRequest'})
        self.assertEqual(response.status_code, 400)

    def test_social_promotion_uses_campaign_url_builder_and_creates_draft(self):
        response = self.client.post(reverse('admin:growth-center-content-social-promo', args=[self.item.content_key]))
        self.assertEqual(response.status_code, 302)
        post = SocialPost.objects.get(title=f'Promote: {self.item.title}')

        expected, error = build_campaign_url(
            self.item.publication_url,
            source='content-marketing',
            medium='social',
            campaign=self.campaign.utm_campaign,
            content=self.item.content_key.lower()[:120],
        )
        self.assertEqual(error, '')
        self.assertEqual(post.destination_url, expected)
        query = dict(parse_qs(urlsplit(post.destination_url).query))
        self.assertEqual(query['utm_campaign'], ['autumn_launch'])
        self.assertEqual(query['utm_content'], [self.item.content_key.lower()])
        self.assertEqual(post.status, 'Draft')
        self.assertIn(self.item, post.content_items.all())

    def test_social_promotion_requires_campaign(self):
        item = make_content(title='No campaign', status='Published', publication_url='https://themehaven.in/no-campaign/')
        response = self.client.post(reverse('admin:growth-center-content-social-promo', args=[item.content_key]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SocialPost.objects.filter(title='Promote: No campaign').exists())


class ContentAnalyticsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('contentadmin', 'content@example.com', 'pass12345')
        self.client = Client()
        self.client.force_login(self.user)
        self.item = make_content(status='Published', publication_url='https://themehaven.in/real-guide/', slug='real-guide')
        self.item.published_at = timezone.now()
        self.item.save(update_fields=['published_at'])

        visitor = Visitor.objects.create(visitor_key='content-visitor')
        session = AnalyticsSession.objects.create(
            session_key='content-session',
            visitor=visitor,
            source_category='Organic Search',
            landing_path='/real-guide',
            utm_content=self.item.content_key,
            utm_campaign='autumn_launch',
            page_view_count=1,
        )
        session.started_at = timezone.now()
        session.save(update_fields=['started_at'])

    def test_performance_uses_real_sessions_and_states_search_console_unavailable(self):
        response = self.client.get(reverse('admin:growth-center-content'), {'section': 'performance'})
        context = response.context['performance']
        self.assertEqual(context['metrics']['total_sessions'], 1)
        self.assertFalse(context['search_console_connected'])
        self.assertEqual(context['top'][0]['title'], self.item.title)
        self.assertEqual(context['top'][0]['visits'], 1)


class ContentBriefRefreshTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('contentadmin', 'content@example.com', 'pass12345')
        self.client = Client()
        self.client.force_login(self.user)
        self.item = make_content(status='Published', publication_url='https://themehaven.in/guide/')
        self.item.published_at = timezone.now()
        self.item.save(update_fields=['published_at'])

    def test_brief_can_be_created_from_template(self):
        template = ContentTemplate.objects.get(name='SEO Blog Post')
        response = self.client.get(reverse('admin:growth-center-content-brief-create'), {'template': template.template_key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].initial['suggested_headings'], template.headings)

        response = self.client.post(reverse('admin:growth-center-content-brief-create'), {
            'working_title': 'Brief from template',
            'content_type': 'Blog Post',
            'objective': 'Explain the workflow.',
            'suggested_headings': template.headings,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContentBrief.objects.filter(working_title='Brief from template').count(), 1)

    def test_refresh_completion_requires_notes(self):
        task = ContentRefreshTask.objects.create(content=self.item, reason='Outdated screenshots', status='Pending')
        response = self.client.post(
            reverse('admin:growth-center-content-refresh-action', args=[task.refresh_key]),
            {'action': 'complete'},
        )
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, 'Pending')

        response = self.client.post(
            reverse('admin:growth-center-content-refresh-action', args=[task.refresh_key]),
            {'action': 'complete', 'notes': 'Replaced screenshots and checked links.'},
        )
        task.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(task.status, 'Completed')
        self.assertIsNotNone(task.completed_at)
