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


POLICIES = {
    'privacy-policy': {
        'title': 'Privacy Policy',
        'intro': 'This policy explains how the current ThemeHaven website handles information when you browse the public pages of this site.',
        'sections': [
            {
                'heading': 'Information handled by this site',
                'paragraphs': [
                    'ThemeHaven currently operates as a catalogue of digital themes and templates. The public site does not include user accounts, a checkout flow, or payment forms, so it does not collect names, postal addresses, or payment details through those pages.',
                ],
            },
            {
                'heading': 'Search queries and theme preference',
                'paragraphs': [
                    'Search fields submit a query as a URL parameter to the homepage. The application does not store submitted search queries.',
                    'Your light or dark theme choice is saved in browser localStorage so the selected appearance persists on your device. That preference is not transmitted to a ThemeHaven server.',
                ],
            },
            {
                'heading': 'Cookies and third-party services',
                'paragraphs': [
                    'Public pages of this project do not set application cookies. Browser localStorage is used only for the theme preference. The Django administration area may set a session cookie for authorized staff.',
                    'Links to WhatsApp and, where configured, social platforms lead to third-party services that have their own privacy practices. ThemeHaven does not control those services.',
                ],
            },
            {
                'heading': 'Support and contact',
                'paragraphs': [
                    'Support contact details have not been configured for this project yet. The Support page linked in the footer provides the guidance currently available.',
                ],
            },
        ],
    },
    'terms-conditions': {
        'title': 'Terms & Conditions',
        'intro': 'These terms describe general use of the ThemeHaven website. They are not a license grant for any individual digital product.',
        'sections': [
            {
                'heading': 'Using the site',
                'paragraphs': [
                    'You may browse the catalogue, use the available search fields, and follow links for informational purposes. Please do not interfere with the operation of the site or attempt to access non-public areas.',
                ],
            },
            {
                'heading': 'Digital products and usage rights',
                'paragraphs': [
                    'The site presents themes, templates, and related digital resources. Product-specific usage rights, license scope, and redistribution rules are not published in this project.',
                    'Review any documentation supplied with a product and contact support before relying on a product for a particular use.',
                ],
            },
            {
                'heading': 'External links',
                'paragraphs': [
                    'External links are provided for convenience. Their content, availability, and operating terms are controlled by the organizations that run them.',
                ],
            },
            {
                'heading': 'Changes to these terms',
                'paragraphs': [
                    'Site content and these terms may be updated as the ThemeHaven project develops.',
                ],
                'items': [
                    'No refund window, shipping estimate, or product warranty is created by these general website terms.',
                    'Support contact details have not been configured yet; the Support page provides the currently available guidance.',
                ],
            },
        ],
    },
    'refund-cancellation-policy': {
        'title': 'Refund Policy',
        'intro': 'This policy explains the current approach to refund requests for ThemeHaven digital products.',
        'sections': [
            {
                'heading': 'No published refund window',
                'paragraphs': [
                    'ThemeHaven has not published a fixed refund period or money-back guarantee in this project. No specific timeframe should be assumed.',
                ],
            },
            {
                'heading': 'How requests are considered',
                'paragraphs': [
                    'Products are digital, so access and delivery differ from physical goods. Requests are considered by reviewing the circumstances of the specific order and any applicable legal requirements.',
                    'The current site does not implement an account area or a self-service refund flow.',
                ],
            },
            {
                'heading': 'How to ask for a review',
                'paragraphs': [
                    'Support contact details have not been configured for this project yet. Use the Support page to check the available guidance and include your order reference if you have one.',
                ],
            },
            {
                'heading': 'Payment-provider disputes',
                'paragraphs': [
                    'Where a payment provider is involved, its dispute process may apply independently of this policy.',
                ],
            },
        ],
    },
    'shipping-delivery-policy': {
        'title': 'User Agreement',
        'intro': 'This User Agreement explains the terms for using the ThemeHaven website and its digital resources.',
        'sections': [
            {
                'heading': 'Using ThemeHaven',
                'paragraphs': [
                    'You may browse the catalogue, use the available search fields, and follow informational links on this site. Do not interfere with the operation of the website or attempt to access non-public areas.',
                ],
            },
            {
                'heading': 'Digital resources',
                'paragraphs': [
                    'The site presents themes, templates, and related digital resources. Product-specific usage rights and license scope are not published in this project.',
                    'Review any documentation supplied with a resource before relying on it for a particular use.',
                ],
            },
            {
                'heading': 'Acceptable use',
                'paragraphs': [
                    'Use the resources in a lawful way and respect the rights of others. Redistribution and resale terms, where applicable, depend on the documentation provided with each resource.',
                ],
            },
            {
                'heading': 'External links and changes',
                'paragraphs': [
                    'External links are controlled by their own operators. Site content and this agreement may be updated as the ThemeHaven project develops.',
                ],
            },
        ],
    },
}


def policy(request, slug):
    return render(request, 'core/policy.html', {'policy': POLICIES[slug]})

