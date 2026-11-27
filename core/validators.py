import os
import re

from django.core.exceptions import ValidationError

from .svg_sanitizer import SvgValidationError, sanitize_svg

HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')
PHONE_CHARS = re.compile(r'^[0-9+()\s.\-]+$')
SVG_CONTENT_TYPES = {'image/svg+xml', 'application/svg+xml', 'application/octet-stream', ''}
SVG_EXTENSIONS = {'.svg'}
SVG_MAX_BYTES = 256 * 1024


def validate_hex_color(value):
    if not HEX_COLOR.fullmatch(value or ''):
        raise ValidationError('Use a hex color in #RRGGBB format.')


def validate_whatsapp_phone(value):
    if not value:
        return
    value = value.strip()
    if not PHONE_CHARS.fullmatch(value):
        raise ValidationError('Use digits with an optional country code (for example +1 555 123 4567).')
    digits = re.sub(r'\D', '', value)
    if not 7 <= len(digits) <= 15:
        raise ValidationError('Enter a phone number with 7 to 15 digits, including the country code.')


def _reset(upload):
    try:
        upload.seek(0)
    except (AttributeError, OSError, ValueError):
        pass


def validate_svg_upload(upload):
    if upload.size > SVG_MAX_BYTES:
        raise ValidationError('SVG files must be 256 KB or smaller.')

    extension = os.path.splitext(upload.name.lower())[1]
    if extension not in SVG_EXTENSIONS:
        raise ValidationError('Upload a file with a .svg extension.')

    content_type = (getattr(upload, 'content_type', '') or '').lower()
    if content_type not in SVG_CONTENT_TYPES:
        raise ValidationError('The uploaded file has an unsupported content type.')

    _reset(upload)
    content = upload.read()
    _reset(upload)
    try:
        sanitize_svg(content)
    except SvgValidationError as error:
        raise ValidationError(str(error))
    finally:
        _reset(upload)
