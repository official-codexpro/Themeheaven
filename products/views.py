import json
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

from .catalogue import PAGE_SIZE, visible_products
from .models import ExcelDashboard, WordPressTheme


def _query(request):
    return (request.GET.get('q') or '').strip()


def _offset(request):
    try:
        return max(0, int(request.GET.get('offset', 0)))
    except (TypeError, ValueError):
        return 0


def _batch(request, model, kind):
    queryset = visible_products(model, _query(request), request.user)
    offset = _offset(request)
    products = list(queryset[offset:offset + PAGE_SIZE])
    html = ''.join(
        render_to_string(
            'products/partials/card.html',
            {'product': product, 'kind': kind},
            request=request,
        )
        for product in products
    )
    next_offset = offset + len(products)
    return JsonResponse({
        'html': html,
        'next_offset': next_offset,
        'has_more': queryset.count() > next_offset,
    })


def wordpress_more(request):
    return _batch(request, WordPressTheme, 'wordpress')


def excel_more(request):
    return _batch(request, ExcelDashboard, 'excel')


def wordpress_detail(request, slug):
    product = get_object_or_404(
        visible_products(WordPressTheme, '', request.user),
        slug=slug,
    )
    return render(request, 'products/detail.html', {
        'product': product,
        'kind': 'wordpress',
        'can_download': request.user.is_authenticated and request.user.is_staff,
        'download_url': product.get_absolute_url(),
    })


def excel_detail(request, slug):
    product = get_object_or_404(
        visible_products(ExcelDashboard, '', request.user),
        slug=slug,
    )
    return render(request, 'products/detail.html', {
        'product': product,
        'kind': 'excel',
        'can_download': request.user.is_authenticated and request.user.is_staff,
        'download_url': product.get_absolute_url(),
    })


def _safe_extension(product):
    return Path(product.download_file.name).suffix.lower()


def _serve_product_file(request, product):
    if not product.download_file:
        raise Http404('This product has no downloadable file.')
    file_path = Path(product.download_file.storage.path(product.download_file.name)).resolve()
    private_root = Path(settings.PRODUCT_PRIVATE_ROOT).resolve()
    if private_root not in file_path.parents or not file_path.is_file():
        raise Http404('The requested file is unavailable.')
    download = product.download_file.open('rb')
    filename = f'{product.slug}{_safe_extension(product)}'
    return FileResponse(download, as_attachment=True, filename=filename)


@staff_member_required
def download_wordpress(request, pk):
    product = get_object_or_404(WordPressTheme, pk=pk)
    return _serve_product_file(request, product)


@staff_member_required
def download_excel(request, pk):
    product = get_object_or_404(ExcelDashboard, pk=pk)
    return _serve_product_file(request, product)


def quick_preview(request, model, pk):
    product = get_object_or_404(visible_products(model, '', request.user), pk=pk)
    payload = json.loads(product.preview_data_json)
    return JsonResponse(payload)


def wordpress_preview(request, pk):
    return quick_preview(request, WordPressTheme, pk)


def excel_preview(request, pk):
    return quick_preview(request, ExcelDashboard, pk)
