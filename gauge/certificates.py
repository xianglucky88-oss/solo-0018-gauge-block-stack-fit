"""Resolve usable correction and uncertainty for a synthetic gauge block."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Certified:
    center_nm: int
    uncertainty_nm: int
    certificate: str


def number(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(label)
    return value


def day(value):
    if not isinstance(value,str) or len(value)!=10:
        raise ValueError('certificate_date')
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('certificate_date')
    return parsed


def resolve(doc):
    when = day(doc['on'])
    catalog = doc['blocks']
    if not isinstance(catalog,dict) or not 1 <= len(catalog) <= 22 or any(not k.strip() for k in catalog):
        raise ValueError('block_catalog')
    active, unusable = {}, {}
    for name,item in sorted(catalog.items()):
        nominal = number(item['nominal_nm'],1,1_000_000_000,'nominal_length')
        certs = item['certificates']
        if not isinstance(certs,list) or len(certs)>30:
            raise ValueError('certificate_count')
        seen, covering = set(), []
        for cert in certs:
            ref=cert['id']
            if not isinstance(ref,str) or not ref.strip() or ref in seen:
                raise ValueError('certificate_id')
            seen.add(ref)
            first,last=day(cert['from']),day(cert['until'])
            if first>=last:
                raise ValueError('certificate_window')
            bias=number(cert['correction_nm'],-nominal+1,nominal,'correction_nm')
            error=number(cert['uncertainty_nm'],0,nominal+bias-1,'uncertainty_nm')
            if first<=when<last:
                covering.append(Certified(nominal+bias,error,ref))
        if len(covering)==1:
            active[name]=covering[0]
        else:
            unusable[name]='overlap' if covering else 'no_valid_certificate'
    return active,unusable
