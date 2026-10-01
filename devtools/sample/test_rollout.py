"""One regression check for the demonstration's incomplete replica rollout."""

import unittest

from rollout import replicas_ready


class RolloutTest(unittest.TestCase):
    def test_all_requested_replicas_must_be_available(self):
        self.assertTrue(replicas_ready(3, 3))
        self.assertFalse(replicas_ready(3, 1))


if __name__ == "__main__":
    unittest.main()
