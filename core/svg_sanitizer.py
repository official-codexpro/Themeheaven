import re
import xml.etree.ElementTree as ET

SVG_NAMESPACE = 'http://www.w3.org/2000/svg'
MAX_SVG_BYTES = 256 * 1024
MAX_SVG_ELEMENTS = 200
MAX_PATH_LENGTH = 12000

ALLOWED_ELEMENTS = {
    'svg', 'g', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline',
    'polygon', 'defs', 'clipPath', 'mask', 'linearGradient', 'radialGradient',
    'stop',
}

ALLOWED_ATTRIBUTES = {
    'viewBox', 'preserveAspectRatio', 'width', 'height', 'x', 'y', 'x1', 'y1',
    'x2', 'y2', 'cx', 'cy', 'r', 'rx', 'ry', 'd', 'points', 'fill', 'stroke',
    'fill-opacity', 'stroke-opacity', 'stroke-width', 'stroke-linecap',
    'stroke-linejoin', 'stroke-miterlimit', 'stroke-dasharray',
    'stroke-dashoffset', 'fill-rule', 'clip-rule', 'opacity', 'transform',
    'id', 'clip-path', 'mask', 'offset', 'stop-color', 'stop-opacity',
    'gradientUnits', 'gradientTransform', 'fx', 'fy',
}

SAFE_REFERENCE = re.compile(r'^url\(#([A-Za-z][A-Za-z0-9_.-]*)\)$')
SAFE_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]*$')
UNSAFE_SCHEME = re.compile(r'(?:javascript|data|vbscript|file):', re.IGNORECASE)
XML_DECLARATION = re.compile(r'^\s*<\?xml[^>]*\?>')
BINARY_BYTE = re.compile(rb'[\x00-\x08\x0b\x0c\x0e-\x1f]')


class SvgValidationError(ValueError):
    pass


def _split_tag(tag):
    if not isinstance(tag, str):
        return None, None
    if tag.startswith('{'):
        namespace, _, local = tag[1:].partition('}')
        return namespace, local
    return None, tag


def _is_allowed_element(tag):
    namespace, name = _split_tag(tag)
    return namespace in (None, SVG_NAMESPACE) and name in ALLOWED_ELEMENTS


def _clean_value(name, value):
    compact = re.sub(r'\s+', '', value)
    if UNSAFE_SCHEME.search(compact):
        return None
    for reference in re.findall(r'url\(([^)]*)\)', compact, re.IGNORECASE):
        if not SAFE_REFERENCE.fullmatch(f'url({reference})'):
            return None
    if name == 'id' and not SAFE_ID.fullmatch(value):
        return None
    if name == 'd' and len(value) > MAX_PATH_LENGTH:
        return None
    return value


def sanitize_svg(value):
    if isinstance(value, str):
        raw = value.encode('utf-8')
    elif isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    else:
        raise SvgValidationError('Upload a valid SVG file.')

    if not raw or len(raw) > MAX_SVG_BYTES:
        raise SvgValidationError('SVG files must be smaller than 256 KB.')
    if BINARY_BYTE.search(raw):
        raise SvgValidationError('The uploaded file is not a text SVG.')

    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise SvgValidationError('The SVG must use UTF-8 encoding.')

    text = XML_DECLARATION.sub('', text, count=1).strip()
    upper_text = text.upper()
    if '<?' in text or '<!DOCTYPE' in upper_text or '<!ENTITY' in upper_text:
        raise SvgValidationError('The SVG contains unsupported XML declarations.')
    if not re.search(r'<svg(?:\s|>)', text, re.IGNORECASE):
        raise SvgValidationError('The uploaded file is not an SVG image.')

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise SvgValidationError('The uploaded SVG is not valid XML.')

    namespace, root_name = _split_tag(root.tag)
    if namespace not in (None, SVG_NAMESPACE) or root_name != 'svg':
        raise SvgValidationError('The SVG must start with an svg element.')

    elements = list(root.iter())
    if len(elements) > MAX_SVG_ELEMENTS:
        raise SvgValidationError('The SVG contains too many elements.')

    parents = {child: parent for parent in elements for child in parent}
    for element in elements:
        if element is not root and not _is_allowed_element(element.tag):
            parents[element].remove(element)
            continue

        for attribute, value in list(element.attrib.items()):
            if '}' in attribute or attribute not in ALLOWED_ATTRIBUTES:
                del element.attrib[attribute]
                continue
            value = _clean_value(attribute, value)
            if value is None:
                del element.attrib[attribute]
                continue
            if attribute in {'fill', 'stroke'} and value.lower() not in {'none'} and not value.lower().startswith('url('):
                value = 'currentColor'
            element.attrib[attribute] = value

        if element is root:
            element.attrib['fill'] = 'currentColor'
        element.text = None
        element.tail = None

    if len(list(root.iter())) < 2:
        raise SvgValidationError('The SVG does not contain any drawable elements.')

    ET.register_namespace('', SVG_NAMESPACE)
    return ET.tostring(root, encoding='unicode', short_empty_elements=True)
