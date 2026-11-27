import io
import os
import re

from django.core.exceptions import ValidationError

SEO_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
SEO_IMAGE_MAX_BYTES = 2 * 1024 * 1024
GOOGLE_TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{10,120}$')
CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
HTML_TAG = re.compile(r'<[^>]*>')

SAFE_ROBOTS_TXT = """User-agent: *
Allow: /
Disallow: /admin/
Disallow: /products/preview/
Disallow: /products/download/
Disallow: /api/
"""


def validate_seo_image(upload):
    extension = os.path.splitext(upload.name.lower())[1]
    if extension not in SEO_IMAGE_EXTENSIONS:
        raise ValidationError('Upload a PNG, JPG, or WebP image.')

    if upload.size > SEO_IMAGE_MAX_BYTES:
        raise ValidationError('SEO images must be 2 MB or smaller.')

    try:
        from PIL import Image

        position = upload.tell()
        with Image.open(upload) as image:
            if (image.format or '').lower() not in {'png', 'jpeg', 'webp'}:
                raise ValidationError('Upload a valid PNG, JPG, or WebP image.')
            image.verify()
        upload.seek(position)
    except (OSError, ValueError):
        raise ValidationError('The uploaded file is not a valid image.')
    except AttributeError:
        raise ValidationError('The uploaded file could not be read.')


def sanitize_text(value, max_length):
    text = ' '.join(str(value or '').split())
    text = HTML_TAG.sub('', text)
    text = CONTROL_CHARS.sub('', text)
    return text[:max_length].strip()


def sanitize_google_token(value):
    text = str(value or '').strip()
    match = re.search(r'content\s*=\s*["\']([^"\']+)["\']', text, re.IGNORECASE)
    if match:
        text = match.group(1).strip()
    text = HTML_TAG.sub('', text).strip()
    return text


def is_valid_google_token(value):
    return bool(GOOGLE_TOKEN_PATTERN.fullmatch(value or ''))


def sanitize_robots_txt(value):
    text = str(value or '').replace('\r\n', '\n').replace('\r', '\n')
    lines = []
    for line in text.split('\n')[:1200]:
        line = CONTROL_CHARS.sub('', line).strip()
        if HTML_TAG.search(line):
            continue
        lines.append(line)
    return '\n'.join(lines).strip()[:20000]


def robots_txt_warnings(value):
    warnings = []
    current_agents = []
    for raw_line in str(value or '').replace('\r\n', '\n').split('\n'):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' not in line:
            continue
        directive, _, target = line.partition(':')
        directive = directive.strip().lower()
        target = target.strip()
        if directive == 'user-agent':
            current_agents.append(target.lower())
            continue
        if directive != 'disallow' or not target:
            continue
        applies_to_all = not current_agents or '*' in current_agents
        if applies_to_all and target in {'/', '/*'}:
            warnings.append('The rule blocks the entire website from all search engines.')
        if target in {'/static/', '/static', '/css/', '/js/', '/assets/'}:
            warnings.append('The rule blocks CSS, JavaScript, or static assets used for rendering.')
    return list(dict.fromkeys(warnings))


def make_test_image(size=(8, 8), image_format='PNG'):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new('RGB', size, color=(30, 64, 120)).save(buffer, format=image_format)
    buffer.seek(0)
    return buffer.getvalue()
