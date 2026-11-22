from .catalog import resolve
from .codec import decode, encode, identifier, sha


def compare(db, ops, name, before, after, operation):
    old = resolve(db, name, identifier(before))
    new = resolve(db, name, identifier(after))
    left, right = decode(old['document']), decode(new['document'])
    prior, later = ops.run(operation, old['document']), ops.run(operation, new['document'])
    changes = [{'field': key, 'change': 'added' if key not in left else
                'removed' if key not in right else 'changed'}
               for key in sorted(left.keys() | right.keys())
               if key not in left or key not in right or encode(left[key]) != encode(right[key])]
    return {'before': old['id'], 'after': new['id'], 'operation': operation, 'input_changes': changes,
            'output_changed': prior != later, 'before_sha': sha(prior), 'after_sha': sha(later),
            'before_output': decode(prior), 'after_output': decode(later)}
