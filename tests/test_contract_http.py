"""Binds the reuse-eligibility contract to the loopback HTTP adapter."""
import unittest
from .adapters import HttpAdapter
from .reuse_contract import ReuseContract


class HttpReuseContractTest(ReuseContract, unittest.TestCase):
    adapter_factory = HttpAdapter


if __name__ == '__main__':
    unittest.main()
