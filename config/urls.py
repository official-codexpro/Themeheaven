"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core import views
from growth_center.views import robots_txt, sitemap_view

handler404 = 'core.views.custom_404'

urlpatterns = [
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap_view, name='sitemap'),
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('support/', views.support, name='support'),
    path('products/', include('products.urls')),
    path('privacy-policy/', views.policy, {'slug': 'privacy-policy'}, name='privacy_policy'),
    path('terms-conditions/', views.policy, {'slug': 'terms-conditions'}, name='terms_conditions'),
    path('refund-cancellation-policy/', views.policy, {'slug': 'refund-cancellation-policy'}, name='refund_cancellation_policy'),
    path('shipping-delivery-policy/', views.policy, {'slug': 'shipping-delivery-policy'}, name='shipping_delivery_policy'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
