import os
import sys

# Ensure src is in sys.path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from tests.test_token_audit import TestTokenAudit
import unittest

if __name__ == "__main__":
    unittest.main()
