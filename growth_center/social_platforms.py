PLATFORMS = (
    {
        'key': 'instagram',
        'label': 'Instagram',
        'limit': 2200,
        'title_limit': 0,
        'home_url': 'https://www.instagram.com/',
        'media': 'Images and video',
        'icon': 'instagram',
    },
    {
        'key': 'facebook',
        'label': 'Facebook',
        'limit': 63206,
        'title_limit': 0,
        'home_url': 'https://www.facebook.com/',
        'media': 'Images, video, and links',
        'icon': 'facebook',
    },
    {
        'key': 'linkedin',
        'label': 'LinkedIn',
        'limit': 3000,
        'title_limit': 0,
        'home_url': 'https://www.linkedin.com/feed/',
        'media': 'Images and video',
        'icon': 'linkedin',
    },
    {
        'key': 'x',
        'label': 'X (Twitter)',
        'limit': 280,
        'title_limit': 0,
        'home_url': 'https://x.com/',
        'media': 'Images and video',
        'icon': 'x',
    },
    {
        'key': 'pinterest',
        'label': 'Pinterest',
        'limit': 500,
        'title_limit': 100,
        'home_url': 'https://www.pinterest.com/',
        'media': 'Vertical images and video',
        'icon': 'pinterest',
    },
    {
        'key': 'youtube',
        'label': 'YouTube',
        'limit': 5000,
        'title_limit': 100,
        'home_url': 'https://www.youtube.com/',
        'media': 'Video',
        'icon': 'youtube',
    },
)

PLATFORM_KEYS = tuple(platform['key'] for platform in PLATFORMS)
PLATFORM_CHOICES = tuple((platform['key'], platform['label']) for platform in PLATFORMS)
PLATFORM_BY_KEY = {platform['key']: platform for platform in PLATFORMS}
PLATFORM_SOURCE_HOSTS = {
    'instagram': ('instagram.com',),
    'facebook': ('facebook.com', 'fb.com'),
    'linkedin': ('linkedin.com',),
    'x': ('twitter.com', 'x.com', 't.co'),
    'pinterest': ('pinterest.com', 'pin.it'),
    'youtube': ('youtube.com', 'youtu.be'),
}

STATUSES = (
    ('Draft', 'Draft'),
    ('Ready', 'Ready'),
    ('Scheduled', 'Scheduled'),
    ('Publishing', 'Publishing'),
    ('Published', 'Published'),
    ('Failed', 'Failed'),
    ('Cancelled', 'Cancelled'),
)

CONTENT_TYPES = (
    ('post', 'Standard Post'),
    ('story', 'Story'),
    ('reel', 'Reel / Short'),
    ('carousel', 'Carousel'),
    ('video', 'Video'),
    ('pin', 'Pin'),
    ('article', 'Article / Long Form'),
)

TEMPLATE_KINDS = (
    ('template', 'Post Template'),
    ('caption', 'Caption Template'),
    ('idea', 'Content Idea'),
    ('cta', 'Call to Action'),
    ('hashtags', 'Hashtag Group'),
)

ACCOUNT_STATUSES = (
    ('Not Connected', 'Not Connected'),
    ('Connected', 'Connected'),
    ('Disconnected', 'Disconnected'),
)

SECTIONS = (
    ('overview', 'Overview'),
    ('calendar', 'Content Calendar'),
    ('posts', 'Posts'),
    ('create', 'Create Post'),
    ('media', 'Media Library'),
    ('templates', 'Templates'),
    ('accounts', 'Social Accounts'),
    ('performance', 'Performance'),
)

CALENDAR_VIEWS = (
    ('month', 'Monthly'),
    ('week', 'Weekly'),
    ('day', 'Daily'),
    ('list', 'List View'),
)

POST_SORTS = (
    ('scheduled', 'Scheduled Date'),
    ('created', 'Created Date'),
    ('title', 'Title'),
    ('status', 'Status'),
)

DEFAULT_TEXT = {
    'instagram': 'Write a caption for Instagram. Keep it clear and add hashtags where useful.',
    'facebook': 'Write a Facebook post. Links and longer copy are supported.',
    'linkedin': 'Write a professional LinkedIn post with a clear takeaway.',
    'x': 'Keep this post within 280 characters.',
    'pinterest': 'Write a concise Pinterest description with searchable terms.',
    'youtube': 'Write the YouTube description. Add links and timestamps where useful.',
}
