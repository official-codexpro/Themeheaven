from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class WhatsappSvgStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(
            location=settings.WHATSAPP_SVG_ROOT,
            base_url='',
            file_permissions_mode=0o640,
            directory_permissions_mode=0o750,
        )

    def url(self, name):
        return ''


whatsapp_svg_storage = WhatsappSvgStorage()


@deconstructible
class AppearanceSvgStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(
            location=settings.APPEARANCE_SVG_ROOT,
            base_url='',
            file_permissions_mode=0o640,
            directory_permissions_mode=0o750,
        )

    def url(self, name):
        return ''


appearance_svg_storage = AppearanceSvgStorage()
