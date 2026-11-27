from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class SocialMediaStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(
            location=settings.SOCIAL_MEDIA_ROOT,
            base_url='',
            file_permissions_mode=0o640,
            directory_permissions_mode=0o750,
        )

    def url(self, name):
        return ''


social_media_storage = SocialMediaStorage()
