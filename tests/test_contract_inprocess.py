"""Binds the reuse-eligibility contract to the in-process adapter."""
import unittest
from .adapters import InProcessAdapter
from .reuse_contract import ReuseContract


class InProcessReuseContractTest(ReuseContract, unittest.TestCase):
    adapter_factory = InProcessAdapter


if __name__ == '__main__':
    unittest.main()
