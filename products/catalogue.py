from django.db.models import Q


PAGE_SIZE = 8


def visible_products(model, query='', user=None):
    queryset = model.objects.all()
    if not (user and user.is_authenticated and user.is_staff):
        queryset = queryset.filter(is_active=True)
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(short_description__icontains=query)
            | Q(description__icontains=query)
            | Q(demo_url__icontains=query)
        )
    return queryset.prefetch_related('screenshots').order_by('display_order', '-created_at')
