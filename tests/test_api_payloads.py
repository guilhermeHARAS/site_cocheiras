import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import Handler


class HorsePayloadTests(unittest.TestCase):
    def test_legacy_photo_is_not_sent_to_the_browser(self):
        stored = {"id": "horse-1", "name": "Persa", "photo": "data:image/png;base64,muitos-dados"}
        payload = Handler._horse_payload(stored)

        self.assertNotIn("photo", payload)
        self.assertEqual(payload["id"], "horse-1")
        self.assertEqual(payload["name"], "Persa")
        self.assertIn("photo", stored)


if __name__ == "__main__":
    unittest.main()
