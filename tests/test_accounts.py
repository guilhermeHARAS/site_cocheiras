import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from auth import new_password_record, verify


class AccountTests(unittest.TestCase):
    def test_new_accounts_receive_separate_workspaces(self):
        first = new_password_record("primeiro@example.com", "senha-123")
        second = new_password_record("segundo@example.com", "senha-456")
        self.assertNotEqual(first["workspaceId"], second["workspaceId"])

    def test_additional_email_can_share_workspace_with_own_password(self):
        owner = new_password_record("dono@example.com", "senha-dono")
        member = new_password_record(
            "membro@example.com",
            "senha-membro",
            workspace_id=owner["workspaceId"],
        )
        self.assertEqual(owner["workspaceId"], member["workspaceId"])
        self.assertTrue(verify(member, "membro@example.com", "senha-membro"))
        self.assertFalse(verify(member, "membro@example.com", "senha-dono"))
        self.assertNotIn("password", member)


if __name__ == "__main__":
    unittest.main()
