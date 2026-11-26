from django.urls import path

from . import views

app_name = 'products'

urlpatterns = [
    path('wordpress/', views.wordpress_more, name='wordpress_more'),
    path('excel/', views.excel_more, name='excel_more'),
    path('wordpress/<slug:slug>/', views.wordpress_detail, name='wordpress_detail'),
    path('excel/<slug:slug>/', views.excel_detail, name='excel_detail'),
    path('preview/wordpress/<int:pk>/', views.wordpress_preview, name='wordpress_preview'),
    path('preview/excel/<int:pk>/', views.excel_preview, name='excel_preview'),
    path('download/wordpress/<int:pk>/', views.download_wordpress, name='download_wordpress'),
    path('download/excel/<int:pk>/', views.download_excel, name='download_excel'),
]
