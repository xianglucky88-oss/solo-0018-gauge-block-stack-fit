from pathlib import Path

from .errors import Problem


WEB = Path(__file__).resolve().parent.parent
_FILES = {'/': ('index.html', 'text/html'), '/assets/theme.css': ('theme.css', 'text/css')}
_FILES.update({f'/assets/{module}.js': (f'{module}.js', 'text/javascript')
               for module in ('app', 'api', 'intake', 'revisions', 'results')})


def get(path):
    if path == '/example.json':
        return (WEB / 'examples' / 'workbench.json').read_bytes(), 'application/json'
    asset = _FILES.get(path)
    if not asset:
        raise Problem('unknown_endpoint', 404)
    name, mime = asset
    return (WEB / 'web' / name).read_bytes(), mime
