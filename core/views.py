from django.shortcuts import render
# Create your views here.

def home(request):
    showcase_themes = [
        ('img/theme-astra-light.webp', 'Astra', 'astra'),
        ('img/theme-neve-light.webp', 'Neve', 'neve'),
        ('img/theme-oceanwp-light.webp', 'OceanWP', 'oceanwp'),
        ('img/theme-kadence-light.webp', 'Kadence', 'kadence'),
    ]
    business_categories = [
        {'name': 'Agency & Portfolio', 'slug': 'agency-portfolio', 'description': 'Showcase work and creative services.', 'image': 'img/theme-kadence-light.webp'},
        {'name': 'Business & Corporate', 'slug': 'business-corporate', 'description': 'Present your company with clarity.', 'image': 'img/theme-astra-light.webp'},
        {'name': 'Ecommerce & Online Store', 'slug': 'ecommerce-store', 'description': 'Build a polished storefront.', 'image': 'img/theme-neve-light.webp'},
        {'name': 'Restaurant & Food', 'slug': 'restaurant-food', 'description': 'Bring menus and dining brands online.', 'image': 'img/theme-oceanwp-light.webp'},
        {'name': 'Real Estate & Architecture', 'slug': 'real-estate-architecture', 'description': 'Present spaces and property listings.', 'image': 'img/theme-astra-light.webp'},
        {'name': 'Education & Courses', 'slug': 'education-courses', 'description': 'Organize learning and course content.', 'image': 'img/theme-kadence-light.webp'},
        {'name': 'Blog & Magazine', 'slug': 'blog-magazine', 'description': 'Make stories easy to explore.', 'image': 'img/theme-neve-light.webp'},
        {'name': 'SaaS & Technology', 'slug': 'saas-technology', 'description': 'Explain products and digital services.', 'image': 'img/theme-oceanwp-light.webp'},
    ]
    value_points = [
        ('Premium Quality', 'Explore a curated collection of polished designs.', 'M12 3l2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3z'),
        ('Instant Downloads', 'Get digital products without waiting for delivery.', 'M12 3v12m0 0 4-4m-4 4-4-4M4 17v3h16v-3'),
        ('Regular Updates', 'Keep your selected assets current over time.', 'M20 7v5h-5M4 17v-5h5m10.5-2A7 7 0 0 0 7.3 7L5 9m14 6-2.3 2A7 7 0 0 1 4.5 14'),
        ('Dedicated Support', 'Find help through the ThemeHaven support page.', 'M4 13v-2a8 8 0 0 1 16 0v2m-16 0H3v5h4v-5H4zm16 0h1v5h-4v-5h3zm-4 8h-4'),
    ]
    return render(request, 'core/home.html', {
        'showcase_themes': showcase_themes,
        'business_categories': business_categories,
        'value_points': value_points,
    })

def support(request):
    return render(request, 'core/support.html')

