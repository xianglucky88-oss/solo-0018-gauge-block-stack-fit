"""Evaluate stack intervals without assuming independent block errors."""
from .certificates import number, resolve


def target(doc):
    wanted = number(doc['target_nm'],1,10_000_000_000,'target_nm')
    tolerance = number(doc['tolerance_nm'],0,wanted-1,'tolerance_nm')
    return wanted-tolerance,wanted+tolerance


def describe(refs, certified, lower, upper):
    center=sum(certified[x].center_nm for x in refs)
    radius=sum(certified[x].uncertainty_nm for x in refs)
    a,b=center-radius,center+radius
    remaining=min(a-lower,upper-b)
    state='within' if remaining>=0 else ('partial' if a<=upper and b>=lower else 'outside')
    return {'blocks':list(refs), 'center_nm':center,'bounds_nm':[a,b],'state':state,'margin_nm':remaining,
            'evidence':{x:certified[x].certificate for x in refs}}


def check(doc):
    good,bad=resolve(doc)
    l,r=target(doc)
    refs=doc['stack']
    if not isinstance(refs,list) or not 1 <= len(refs) <= 6 or any(not isinstance(x,str) for x in refs) or len(set(refs))!=len(refs) or set(refs)-(good.keys()|bad.keys()):
        raise ValueError('stack_members')
    unresolved={x:bad[x] for x in refs if x in bad}
    if unresolved:
        return {'state':'unresolved','unusable':unresolved}
    return describe(refs,good,l,r)
