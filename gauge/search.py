"""Enumerate bounded combinations and rank only fully conforming stacks."""
from itertools import combinations
from .certificates import number,resolve
from .fit import describe,target
from .reconfigure import plan as fixture_plan


def available(doc):
    good,bad=resolve(doc)
    return {'certified':{k:{'center_nm':x.center_nm,'uncertainty_nm':x.uncertainty_nm,'certificate':x.certificate} for k,x in good.items()},'unusable':bad}


def recommend(doc):
    good,bad=resolve(doc)
    l,r=target(doc)
    max_blocks=number(doc['max_blocks'],1,4,'max_blocks')
    policy=doc.get('rank','block_count')
    if policy not in ('block_count','margin'):
        raise ValueError('rank_policy')
    if 'fixture' in doc:
        # Locked blocks, mounted blocks, stoppage-only spares and the maximum
        # number of remove/add operations split the answer into an in-place
        # document and a free after-stoppage rebuild document.
        return fixture_plan(doc,good,bad,max_blocks,policy)
    best,count=None,0
    for size in range(1,max_blocks+1):
        for refs in combinations(sorted(good),size):
            row=describe(refs,good,l,r)
            if row['state']!='within':
                continue
            count+=1
            merit=(-size,row['margin_nm']) if policy=='block_count' else (row['margin_nm'],-size)
            if best is None or merit > best[0]:
                best=(merit,row)
    return {'state':'matched' if best else 'no_conforming_stack','feasible_count':count,
            'recommendation':best[1] if best else None,'unusable':bad,'rank':policy}
