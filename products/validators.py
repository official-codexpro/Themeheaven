import os
import zipfile
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
IMAGE_CONTENT_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}
IMAGE_EXTENSION_FORMATS = {
    '.jpg': {'JPEG'},
    '.jpeg': {'JPEG'},
    '.png': {'PNG'},
    '.webp': {'WEBP'},
}
MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_IMAGE_DIMENSION = 6000

WORDPRESS_EXTENSIONS = {'.zip'}
WORDPRESS_CONTENT_TYPES = {
    'application/zip',
    'application/x-zip-compressed',
    'application/octet-stream',
    '',
}
EXCEL_EXTENSIONS = {'.xlsx', '.xlsm', '.xltx', '.xltm', '.xls'}
EXCEL_CONTENT_TYPES = {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel.sheet.macroEnabled.12',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.template',
    'application/vnd.ms-excel.template.macroEnabled.12',
    'application/vnd.ms-excel',
    'application/zip',
    'application/octet-stream',
    '',
}
MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE = 200 * 1024 * 1024


def _extension(upload):
    return os.path.splitext(upload.name.lower())[1]


def _content_type(upload):
    return (getattr(upload, 'content_type', '') or '').lower()


def _reset(upload):
    try:
        upload.seek(0)
    except (AttributeError, OSError, ValueError):
        pass


def validate_product_image(upload):
    if upload.size > MAX_IMAGE_SIZE:
        raise ValidationError('Image files must be 8 MB or smaller.')

    extension = _extension(upload)
    if extension not in IMAGE_EXTENSIONS:
        raise ValidationError('Use a JPG, PNG, or WEBP image.')

    content_type = _content_type(upload)
    if content_type and content_type not in IMAGE_CONTENT_TYPES:
        raise ValidationError('The uploaded image has an unsupported content type.')

    try:
        with Image.open(upload) as image:
            if image.format not in IMAGE_FORMATS:
                raise ValidationError('The image format must be JPG, PNG, or WEBP.')
            if image.format not in IMAGE_EXTENSION_FORMATS[extension]:
                raise ValidationError('The image extension does not match its format.')
            if max(image.size) > MAX_IMAGE_DIMENSION:
                raise ValidationError('Image dimensions must be 6000 pixels or less.')
            image.verify()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError('The uploaded file is not a valid image.')
    finally:
        _reset(upload)


def _validate_zip_container(upload):
    with zipfile.ZipFile(upload) as archive:
        infos = archive.infolist()
        if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_SIZE:
            raise ValidationError('The archive expands to an unsafe size.')
        for info in infos:
            name = info.filename.replace('\\', '/')
            if name.startswith('/') or any(part == '..' for part in name.split('/')):
                raise ValidationError('The archive contains unsafe paths.')
    _reset(upload)


def validate_wordpress_package(upload):
    if upload.size > MAX_FILE_SIZE:
        raise ValidationError('WordPress packages must be 50 MB or smaller.')

    if _extension(upload) not in WORDPRESS_EXTENSIONS:
        raise ValidationError('WordPress packages must be valid ZIP files.')

    if _content_type(upload) not in WORDPRESS_CONTENT_TYPES:
        raise ValidationError('The WordPress package has an unsupported content type.')

    header = upload.read(4)
    _reset(upload)
    if header[:2] not in {b'PK', b'PK\x03\x04'}:
        raise ValidationError('The WordPress package is not a valid ZIP archive.')

    try:
        _validate_zip_container(upload)
    except zipfile.BadZipFile:
        raise ValidationError('The WordPress package is not a valid ZIP archive.')
    finally:
        _reset(upload)


def validate_excel_workbook(upload):
    if upload.size > MAX_FILE_SIZE:
        raise ValidationError('Excel workbooks must be 50 MB or smaller.')

    if _extension(upload) not in EXCEL_EXTENSIONS:
        raise ValidationError('Excel files must use .xlsx, .xlsm, .xltx, .xltm, or .xls.')

    if _content_type(upload) not in EXCEL_CONTENT_TYPES:
        raise ValidationError('The Excel workbook has an unsupported content type.')

    header = upload.read(8)
    _reset(upload)
    extension = _extension(upload)

    if extension == '.xls':
        if header[:8] != b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            raise ValidationError('The Excel workbook is not a valid .xls file.')
        return

    if header[:4] not in {b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'}:
        raise ValidationError('The Excel workbook is not a valid Office file.')

    try:
        with zipfile.ZipFile(upload) as archive:
            names = archive.namelist()
            if '[Content_Types].xml' not in names:
                raise ValidationError('The Excel workbook is missing Office metadata.')
            if not any(name.startswith('xl/workbook') for name in names):
                raise ValidationError('The uploaded ZIP is not an Excel workbook.')
            if sum(info.file_size for info in archive.infolist()) > MAX_UNCOMPRESSED_SIZE:
                raise ValidationError('The workbook expands to an unsafe size.')
            for name in names:
                normalized = name.replace('\\', '/')
                if normalized.startswith('/') or any(part == '..' for part in normalized.split('/')):
                    raise ValidationError('The workbook contains unsafe paths.')
    except zipfile.BadZipFile:
        raise ValidationError('The Excel workbook is not a valid Office file.')
    finally:
        _reset(upload)


def validate_http_url(value):
    if not value:
        return
    parsed = urlparse(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValidationError('Use a full http or https URL.')
