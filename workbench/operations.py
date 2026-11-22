from .codec import decode, encode
from .errors import Problem


class Operations:
    def __init__(self, profile):
        self.profile = profile
        self.operations = profile.OPERATIONS

    def run(self, name, source):
        if not isinstance(name, str) or name not in self.operations:
            raise Problem('unknown_operation', 404)
        try:
            return encode(self.operations[name][1](decode(source)))
        except (KeyError, TypeError, ValueError, OverflowError, RecursionError, AttributeError, IndexError) as exc:
            detail = str(exc) if type(exc) is ValueError and str(exc).isascii() and len(str(exc)) < 100 else None
            raise Problem('domain_input', 422, detail) from exc

    def validate(self, source):
        for name in self.profile.REQUIRED:
            self.run(name, source)

    def metadata(self):
        return {'title': self.profile.TITLE, 'product': self.profile.PRODUCT, 'theme': self.profile.THEME,
                'example_dataset': self.profile.DEFAULT_DATASET, 'work_label': self.profile.WORK_LABEL,
                'operations': [{'id': key, 'label': label} for key, (label, _) in self.operations.items()]}
