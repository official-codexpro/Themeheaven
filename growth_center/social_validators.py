from pathlib import Path

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

SOCIAL_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
SOCIAL_VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov'}
SOCIAL_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP', 'GIF'}
SOCIAL_IMAGE_CONTENT_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif', ''}
SOCIAL_VIDEO_CONTENT_TYPES = {'video/mp4', 'video/webm', 'video/quicktime', ''}
EXTENSION_FORMATS = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP', '.gif': 'GIF'}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_IMAGE_DIMENSION = 6000


def reset_upload(upload):
    try:
        upload.seek(0)
    except (AttributeError, OSError, ValueError):
        pass


def detect_media_type(upload):
    extension = Path(getattr(upload, 'name', '') or '').suffix.lower()
    if extension in SOCIAL_IMAGE_EXTENSIONS:
        return 'Image'
    if extension in SOCIAL_VIDEO_EXTENSIONS:
        return 'Video'
    return ''


def _validate_image(upload, extension):
    content_type = (getattr(upload, 'content_type', '') or '').lower()
    if content_type and content_type not in SOCIAL_IMAGE_CONTENT_TYPES:
        raise ValidationError('Unsupported image content type.')
    if upload.size > MAX_IMAGE_BYTES:
        raise ValidationError('Image files must be 8 MB or smaller.')

    try:
        image = Image.open(upload)
        image_format = image.format
        width, height = image.size
        if image_format not in SOCIAL_IMAGE_FORMATS:
            raise ValidationError('Use a JPG, PNG, WebP, or GIF image.')
        if EXTENSION_FORMATS.get(extension) != image_format:
            raise ValidationError('The file extension does not match the image format.')
        if max(width, height) > MAX_IMAGE_DIMENSION:
            raise ValidationError('Image dimensions must be 6000 pixels or smaller.')
        image.verify()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError('The image file could not be read.')
    finally:
        reset_upload(upload)


def _validate_video(upload, extension):
    content_type = (getattr(upload, 'content_type', '') or '').lower()
    if content_type and content_type not in SOCIAL_VIDEO_CONTENT_TYPES:
        raise ValidationError('Unsupported video content type.')
    if upload.size > MAX_VIDEO_BYTES:
        raise ValidationError('Video files must be 50 MB or smaller.')

    header = upload.read(16)
    reset_upload(upload)
    if extension == '.webm':
        if not header.startswith(b'\x1a\x45\xdf\xa3'):
            raise ValidationError('The WebM video file is not valid.')
    elif b'ftyp' not in header[:12]:
        raise ValidationError('The MP4 or MOV video file is not valid.')


def validate_social_media(upload):
    extension = Path(getattr(upload, 'name', '') or '').suffix.lower()
    if extension in SOCIAL_IMAGE_EXTENSIONS:
        _validate_image(upload, extension)
        return
    if extension in SOCIAL_VIDEO_EXTENSIONS:
        _validate_video(upload, extension)
        return
    raise ValidationError('Use JPG, PNG, WebP, GIF, MP4, WebM, or MOV files only.')
