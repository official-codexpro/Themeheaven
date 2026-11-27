import json
import tempfile
from datetime import timedelta
from io import BytesIO
from urllib.parse import parse_qsl, urlsplit

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .models import Campaign, SocialAccount, SocialMediaAsset, SocialPost, SocialPostPlatform, SocialPostTemplate
from .social import build_post_tracking_url
from .social_platforms import PLATFORMS, PLATFORM_BY_KEY


def png_upload(name='sample.png'):
    buffer = BytesIO()
    Image.new('RGB', (12, 8), '#7c3aed').save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


def make_campaign(**overrides):
    data = {
        'name': 'Spring Launch',
        'destination_url': 'https://themehaven.in/products/?ref=home#pricing',
        'utm_source': 'newsletter',
        'utm_medium': 'email',
        'utm_campaign': 'spring_launch',
        'status': 'Active',
    }
    data.update(overrides)
    return Campaign.objects.create(**data)


def make_post(**overrides):
    data = {
        'title': 'Spring Launch Post',
        'content': 'A genuine social post prepared by staff.',
        'content_type': 'post',
        'status': 'Draft',
        'hashtags': 'themehaven, launch',
    }
    data.update(overrides)
    return SocialPost.objects.create(**data)


class SocialPlatformConfigTests(TestCase):
    def test_all_platforms_have_limits_and_manual_destinations(self):
        self.assertEqual(len(PLATFORMS), 6)
        self.assertEqual(PLATFORM_BY_KEY['x']['limit'], 280)
        self.assertEqual(PLATFORM_BY_KEY['pinterest']['title_limit'], 100)
        for platform in PLATFORMS:
            self.assertTrue(platform['home_url'].startswith('https://'))
            self.assertGreater(platform['limit'], 0)

    def test_accounts_default_to_not_connected(self):
        self.assertEqual(SocialAccount.objects.count(), 0)
        for platform in PLATFORMS:
            self.assertEqual(platform['key'] in PLATFORM_BY_KEY, True)


class SocialTrackingTests(TestCase):
    def test_tracking_url_reuses_campaign_builder_and_post_key(self):
        campaign = make_campaign()
        post = make_post(campaign=campaign)
        SocialPostPlatform.objects.create(post=post, platform='instagram')

        url = build_post_tracking_url(post, 'instagram')
        query = dict(parse_qsl(urlsplit(url).query))
        self.assertEqual(query['utm_source'], 'instagram')
        self.assertEqual(query['utm_medium'], 'organic_social')
        self.assertEqual(query['utm_campaign'], 'spring_launch')
        self.assertEqual(query['utm_content'], post.post_key)
        self.assertEqual(query['ref'], 'home')
        self.assertEqual(urlsplit(url).fragment, 'pricing')

    def test_tracking_url_is_empty_without_destination(self):
        post = make_post()
        self.assertEqual(build_post_tracking_url(post, 'facebook'), '')


class SocialFormTests(TestCase):
    def setUp(self):
        self.campaign = make_campaign()

    def post_payload(self, **overrides):
        payload = {
            'title': 'Launch Teaser',
            'content': 'Prepared content for all selected platforms.',
            'content_type': 'post',
            'status': 'Draft',
            'platforms': ['instagram', 'x'],
            'platform_content_instagram': 'Instagram caption with enough room.',
            'platform_content_x': 'Short X caption.',
            'campaign': self.campaign.id,
            'destination_url': 'https://themehaven.in/launch/?ref=social#top',
            'utm_source': '',
            'utm_medium': '',
            'utm_campaign': '',
            'utm_term': '',
            'utm_content': '',
            'hashtags': 'themehaven',
            'notes': 'Internal note',
            'workflow_action': 'save_draft',
        }
        payload.update(overrides)
        return payload

    def test_form_creates_platform_entries_and_normalizes_fields(self):
        from .social_forms import SocialPostForm

        form = SocialPostForm(self.post_payload())
        self.assertTrue(form.is_valid(), form.errors)
        post = form.save()
        self.assertEqual(post.status, 'Draft')
        self.assertEqual(post.platform_keys, ['instagram', 'x'])
        entry = post.platform_entries.get(platform='x')
        self.assertEqual(entry.content, 'Short X caption.')
        self.assertEqual(post.destination_url, 'https://themehaven.in/launch/?ref=social#top')

    def test_form_requires_schedule_when_scheduling(self):
        from .social_forms import SocialPostForm

        payload = self.post_payload(workflow_action='schedule')
        form = SocialPostForm(payload)
        self.assertFalse(form.is_valid())
        self.assertIn('scheduled_date', form.errors)

    def test_form_schedules_platform_reminders_with_time_overrides(self):
        from .social_forms import SocialPostForm

        future = timezone.now() + timedelta(days=2)
        payload = self.post_payload(
            workflow_action='schedule',
            scheduled_date=future.date().isoformat(),
            scheduled_time=future.strftime('%H:%M'),
            platform_time_instagram='11:30',
        )
        form = SocialPostForm(payload)
        self.assertTrue(form.is_valid(), form.errors)
        post = form.save()
        self.assertEqual(post.status, 'Scheduled')
        instagram = post.platform_entries.get(platform='instagram')
        self.assertEqual(timezone.localtime(instagram.scheduled_at).strftime('%H:%M'), '11:30')


class SocialMediaAssetTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        settings_override = override_settings(SOCIAL_MEDIA_ROOT=self.temp_dir.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.addCleanup(self.temp_dir.cleanup)
        self.field = SocialMediaAsset._meta.get_field('file')
        self.original_storage = self.field.storage
        self.field.storage = FileSystemStorage(location=self.temp_dir.name)
        self.addCleanup(setattr, self.field, 'storage', self.original_storage)
        self.user = get_user_model().objects.create_superuser('socialadmin', 'social@example.com', 'pass12345')
        self.client.force_login(self.user)

    def test_upload_validates_image_and_serves_private_file(self):
        response = self.client.post(reverse('admin:growth-center-social'), {
            'section': 'media',
            'intent': 'upload_asset',
            'title': 'Launch Image',
            'media_type': 'Image',
            'alt_text': 'Launch graphic',
            'file': png_upload(),
        })
        self.assertEqual(response.status_code, 302)
        asset = SocialMediaAsset.objects.get(title='Launch Image')
        self.assertEqual(asset.media_type, 'Image')
        self.assertEqual(asset.mime_type, 'image/png')
        self.assertEqual(asset.width, 12)
        self.assertEqual(asset.height, 8)
        self.assertEqual(asset.uploaded_by, self.user)

        file_response = self.client.get(reverse('admin:growth-center-social-media-asset-file', args=[asset.id]))
        self.assertEqual(file_response.status_code, 200)
        self.assertEqual(file_response['Content-Type'], 'image/png')
        self.assertTrue(asset.file.storage.exists(asset.file.name))

        download = self.client.get(reverse('admin:growth-center-social-media-asset-file', args=[asset.id]), {'download': '1'})
        self.assertIn('attachment', download['Content-Disposition'])

    def test_rejects_video_upload_declared_as_image(self):
        from .social_forms import SocialMediaAssetForm

        upload = SimpleUploadedFile('clip.mp4', b'\x00\x00\x00\x18ftypisom', content_type='video/mp4')
        form = SocialMediaAssetForm({
            'title': 'Wrong Type',
            'media_type': 'Image',
            'alt_text': '',
        }, {'file': upload})
        self.assertFalse(form.is_valid())
        self.assertIn('media_type', form.errors)

    def test_asset_used_by_published_post_cannot_be_deleted(self):
        asset = SocialMediaAsset.objects.create(title='Published Asset', file=png_upload(), media_type='Image')
        post = make_post(status='Published')
        post.media.add(asset)

        response = self.client.post(reverse('admin:growth-center-social-media-asset-action', args=[asset.id]), {
            'action': 'delete',
            'confirm': '1',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SocialMediaAsset.objects.filter(id=asset.id).exists())


class SocialViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('socialadmin', 'social@example.com', 'pass12345')
        self.client.force_login(self.user)
        self.campaign = make_campaign()
        self.post = make_post(campaign=self.campaign)
        SocialPostPlatform.objects.create(post=self.post, platform='instagram')
        sync_urls = build_post_tracking_url(self.post, 'instagram')
        entry = self.post.platform_entries.get(platform='instagram')
        entry.tracking_url = sync_urls
        entry.save(update_fields=['tracking_url'])

    def test_dashboard_shows_real_workflow_state_and_no_fake_connections(self):
        response = self.client.get(reverse('admin:growth-center-social'), {'section': 'overview'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Social Media Manager')
        self.assertContains(response, self.post.title)
        self.assertEqual(response.context['total_posts'], 1)
        self.assertEqual(response.context['connected_count'], 0)

        accounts = self.client.get(reverse('admin:growth-center-social'), {'section': 'accounts'})
        self.assertContains(accounts, 'No native social API connections are configured')
        self.assertEqual(accounts.content.decode().count('Not Connected'), len(PLATFORMS))

    def test_ajax_partial_returns_html(self):
        response = self.client.get(reverse('admin:growth-center-social'), {
            'section': 'posts',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode())
        self.assertEqual(payload['section'], 'posts')
        self.assertIn('All Posts', payload['html'])

    def test_editor_creates_post_and_syncs_tracking_url(self):
        future = timezone.now() + timedelta(days=3)
        response = self.client.post(reverse('admin:growth-center-social-post-create'), {
            'title': 'Editor Created',
            'content': 'Content from the editor view.',
            'content_type': 'post',
            'status': 'Draft',
            'platforms': ['linkedin'],
            'platform_content_linkedin': 'LinkedIn content.',
            'campaign': self.campaign.id,
            'destination_url': 'https://themehaven.in/story/?ref=linkedin',
            'utm_source': '',
            'utm_medium': '',
            'utm_campaign': '',
            'utm_term': '',
            'utm_content': '',
            'hashtags': '',
            'notes': '',
            'scheduled_date': future.date().isoformat(),
            'scheduled_time': future.strftime('%H:%M'),
            'workflow_action': 'schedule',
        })
        self.assertEqual(response.status_code, 302)
        post = SocialPost.objects.get(title='Editor Created')
        entry = post.platform_entries.get(platform='linkedin')
        self.assertEqual(post.status, 'Scheduled')
        self.assertIn('utm_source=linkedin', entry.tracking_url)
        self.assertIn('utm_campaign=spring_launch', entry.tracking_url)

    def test_template_can_prefill_editor_and_be_deleted(self):
        template = SocialPostTemplate.objects.create(
            name='Launch Caption',
            content='Reusable launch caption.',
            hashtags='themehaven',
            platform='instagram',
            created_by=self.user,
        )
        editor = self.client.get(reverse('admin:growth-center-social-post-create'), {'template': template.template_key})
        self.assertContains(editor, 'Reusable launch caption.')

        response = self.client.post(reverse('admin:growth-center-social-template-action', args=[template.template_key]), {
            'action': 'delete',
            'confirm': '1',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SocialPostTemplate.objects.filter(id=template.id).exists())

    def test_post_actions_track_manual_publication_and_duplicate(self):
        entry = self.post.platform_entries.get(platform='instagram')
        detail_url = reverse('admin:growth-center-social-post-detail', args=[self.post.post_key])
        action_url = reverse('admin:growth-center-social-post-action', args=[self.post.post_key])

        response = self.client.post(action_url, {
            'action': 'mark_published',
            'platform': 'instagram',
            'publication_url': 'https://www.instagram.com/p/example/',
            'published_date': timezone.localdate().isoformat(),
            'published_time': '12:30',
        })
        self.assertRedirects(response, detail_url)
        entry.refresh_from_db()
        self.post.refresh_from_db()
        self.assertEqual(entry.status, 'Published')
        self.assertEqual(entry.published_by, self.user)
        self.assertEqual(self.post.status, 'Published')

        duplicate = self.client.post(action_url, {'action': 'duplicate'})
        self.assertEqual(duplicate.status_code, 302)
        copy = SocialPost.objects.get(title='Spring Launch Post (Copy)')
        self.assertEqual(copy.status, 'Draft')
        self.assertEqual(copy.platform_entries.count(), 1)

        self.client.post(action_url, {'action': 'mark_failed', 'platform': 'instagram'})
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'Failed')

    def test_reschedule_actions_are_reminders_only(self):
        entry = self.post.platform_entries.get(platform='instagram')
        future = timezone.now() + timedelta(days=5)
        action_url = reverse('admin:growth-center-social-post-action', args=[self.post.post_key])

        self.client.post(action_url, {
            'action': 'reschedule',
            'platform': 'instagram',
            'scheduled_date': future.date().isoformat(),
            'scheduled_time': future.strftime('%H:%M'),
        })
        entry.refresh_from_db()
        self.post.refresh_from_db()
        self.assertEqual(entry.status, 'Scheduled')
        self.assertIsNotNone(entry.scheduled_at)
        self.assertEqual(self.post.status, 'Scheduled')

        response = self.client.post(reverse('admin:growth-center-social-calendar-reschedule'), {
            'post_key': self.post.post_key,
            'platform': 'instagram',
            'date': future.date().isoformat(),
            'time': '09:45',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content.decode())['ok'])
        entry.refresh_from_db()
        self.assertEqual(timezone.localtime(entry.scheduled_at).strftime('%H:%M'), '09:45')

        self.client.post(action_url, {'action': 'cancel_schedule', 'platform': 'instagram'})
        entry.refresh_from_db()
        self.assertIsNone(entry.scheduled_at)
        self.assertEqual(entry.status, 'Draft')

    def test_delete_post_requires_confirmation(self):
        action_url = reverse('admin:growth-center-social-post-action', args=[self.post.post_key])
        self.client.post(action_url, {'action': 'delete'})
        self.assertTrue(SocialPost.objects.filter(id=self.post.id).exists())
        self.client.post(action_url, {'action': 'delete', 'confirm': '1'})
        self.assertFalse(SocialPost.objects.filter(id=self.post.id).exists())

    def test_staff_without_superuser_can_use_module(self):
        from django.contrib.auth.models import Permission

        staff = get_user_model().objects.create_user('socialstaff', 'staff@example.com', 'password', is_staff=True)
        staff.user_permissions.set(Permission.objects.all())
        self.client.force_login(staff)
        response = self.client.get(reverse('admin:growth-center-social'))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse('admin:growth-center-social'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])


class SocialPerformanceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('socialadmin', 'social@example.com', 'pass12345')
        self.client.force_login(self.user)
        self.campaign = make_campaign()
        self.post = make_post(campaign=self.campaign)
        SocialPostPlatform.objects.create(post=self.post, platform='instagram')

    def test_performance_shows_only_real_attributed_website_traffic(self):
        url = build_post_tracking_url(self.post, 'instagram')
        params = dict(parse_qsl(urlsplit(url).query))
        visitor = Client()
        self.assertEqual(visitor.get('/support/', params).status_code, 200)

        response = self.client.get(reverse('admin:growth-center-social'), {'section': 'performance'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Website attribution only')
        self.assertContains(response, 'do not represent platform reach')
        self.assertEqual(response.context['kpis']['visits'], 1)
        self.assertFalse(response.context['native_metrics_available'])
        self.assertEqual(response.context['post_rows'][0]['utm_content'], self.post.post_key)

    def test_performance_without_traffic_reports_empty_state(self):
        response = self.client.get(reverse('admin:growth-center-social'), {'section': 'performance'})
        self.assertContains(response, 'No social-attributed website traffic yet')
        self.assertEqual(response.context['kpis']['visits'], 0)
