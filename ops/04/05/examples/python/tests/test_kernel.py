import unittest
from service import calculate


class KernelTest(unittest.TestCase):
    def test_signed_input(self):
        self.assertEqual(calculate(7), 49)
        self.assertEqual(calculate(-7), 49)
        self.assertEqual(calculate(0), 0)
