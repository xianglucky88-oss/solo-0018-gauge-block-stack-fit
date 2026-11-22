"""Static guards: the reuse decision must not be a relabelled full search.

The contract's instrumentation proves no full search runs at decision
time; these guards prove the shipped component is not even wired to one.
"""
import ast
import unittest
from pathlib import Path
from gauge import http_api, reuse, search

REUSE_SOURCE = Path(__file__).resolve().parent.parent / 'gauge' / 'reuse.py'


class ReusePathGuards(unittest.TestCase):

    def test_reuse_module_never_invokes_full_search(self):
        tree = ast.parse(REUSE_SOURCE.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                self.assertFalse(any('search' in name for name in modules),
                                 'gauge.reuse must not import the search module')
            if isinstance(node, ast.Attribute):
                self.assertNotEqual(node.attr, 'recommend',
                                    'gauge.reuse must not call the full search')
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotIn('conforming-stacks', node.value)

    def test_reuse_route_is_wired_to_the_decision_not_the_search(self):
        self.assertIs(http_api.ROUTES['/stackfit/reuse-decision'], reuse.decide)
        self.assertIsNot(http_api.ROUTES['/stackfit/reuse-decision'], search.recommend)


if __name__ == '__main__':
    unittest.main()
