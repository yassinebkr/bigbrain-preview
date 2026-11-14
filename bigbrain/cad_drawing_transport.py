"""Compact drawing transport with authoritative source expansion and cropped regions."""

from copy import deepcopy

from .cad_drawings import DrawingSource, DrawingSpecification

WIRE_VERSION = 'cad-drawing/1'


def intake_schema(schema):
    """Reference runtime-owned sources while retaining dimension-specific regions."""
    schema = deepcopy(schema)
    source = schema['$defs']['DrawingSource']
    region = source['properties']['region']
    schema['$defs']['DrawingSource'] = {
        'type': 'object', 'additionalProperties': False,
        'properties': {'source_index': {'type': 'integer', 'minimum': 0, 'maximum': 7},
                       'region': region}, 'required': ['source_index']}
    def strip_versions(value):
        if isinstance(value, dict):
            properties = value.get('properties', {})
            if properties.get('schema_version', {}).get('const') == '1.0':
                properties.pop('schema_version')
                if 'required' in value:
                    value['required'] = [key for key in value['required'] if key != 'schema_version']
            for item in value.values():
                strip_versions(item)
        elif isinstance(value, list):
            for item in value:
                strip_versions(item)
    strip_versions(schema)
    schema['properties']['wire_version'] = {'type': 'string', 'const': WIRE_VERSION}
    schema['required'] = [*schema.get('required', []), 'wire_version']
    return schema


def compact_drawing(drawing, sources):
    """Remove default fields and bind each source reference to the supplied ledger."""
    drawing = DrawingSpecification.model_validate(drawing)
    ledger = {(source.attachment_id, source.sha256): index for index, source in enumerate(sources)}
    def encode(value):
        if isinstance(value, dict):
            if 'attachment_id' in value and 'sha256' in value:
                identity = (value['attachment_id'], value['sha256'])
                if identity not in ledger:
                    raise ValueError('Drawing source is outside the transport source ledger')
                result = {'source_index': ledger[identity]}
                if 'region' in value:
                    result['region'] = value['region']
                return result
            return {key: encode(item) for key, item in value.items()}
        if isinstance(value, list):
            return [encode(item) for item in value]
        return value
    return encode(drawing.model_dump(mode='json', exclude_defaults=True))


def expand_intake(value, sources):
    """Restore owned hashes and defaults before the complete internal validation."""
    value = deepcopy(value)
    if value.pop('wire_version', None) != WIRE_VERSION:
        raise ValueError('Unsupported CAD drawing transport version')
    def decode(item):
        if isinstance(item, dict):
            if 'source_index' in item:
                index = item['source_index']
                if (type(index) is not int or not 0 <= index < len(sources)
                        or set(item) - {'source_index', 'region'}):
                    raise ValueError('Invalid CAD source reference')
                source = sources[index].model_dump(mode='json')
                # Regions belong to each reference; the ledger binds image bytes.
                source['region'] = (item['region'] if item.get('region') is not None
                                    else (0, 0, 1, 1))
                return DrawingSource.model_validate(source).model_dump(mode='json')
            return {key: decode(child) for key, child in item.items()}
        if isinstance(item, list):
            return [decode(child) for child in item]
        return item
    return decode(value)
