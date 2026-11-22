import hashlib
import json
import re

from .errors import Problem


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate_json_key')
        value[key] = item
    return value


def _reject_constant(value):
    raise ValueError('nonfinite_json')


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def decode(text):
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_constant)


def document(text):
    if not isinstance(text, str) or not 0 < len(text) <= 262144:
        raise Problem('input_size')
    try:
        raw = text.encode('utf-8')
        if len(raw) > 262144:
            raise Problem('input_size')
        value = decode(text)
        canonical = encode(value)
    except Problem:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise Problem('invalid_json') from exc
    if not isinstance(value, dict):
        raise Problem('expected_object')
    return value, canonical, sha(canonical), sha(raw)


def sha(value):
    return hashlib.sha256(value.encode('utf-8') if isinstance(value, str) else value).hexdigest()


def dataset(value):
    if not isinstance(value, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', value) is None:
        raise Problem('dataset_name')
    return value


def identifier(value):
    if not isinstance(value, str) or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise Problem('identifier')
    return value


def generation(value):
    if type(value) is not int or not 0 <= value <= 2**63 - 2:
        raise Problem('generation')
    return value
