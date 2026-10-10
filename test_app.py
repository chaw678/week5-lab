"""One test per acceptance criterion. Run with:  python3 -m unittest"""

import unittest
from datetime import timedelta

from sqlalchemy import select

from app import Loan, create_app


class BorrowDuckTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.engine.dispose()

    def loans(self):
        with self.app.Session() as session:
            return session.scalars(select(Loan)).all()

    def borrow(self, member_id, duck_id):
        return self.client.post(
            "/loans",
            data={"member_id": member_id, "duck_id": duck_id},
            follow_redirects=True,
        )

    def test_loan_is_recorded(self):
        self.borrow("M001", "D001")

        (loan,) = self.loans()
        self.assertEqual(loan.member_id, "M001")
        self.assertEqual(loan.duck_id, "D001")
        self.assertIsNotNone(loan.borrowed_at)
        self.assertIsNone(loan.returned_at)

    def test_due_date_is_seven_days_after_borrowing(self):
        self.borrow("M001", "D001")

        (loan,) = self.loans()
        self.assertEqual(loan.due_at - loan.borrowed_at, timedelta(days=7))

    def test_duck_on_loan_cannot_be_borrowed(self):
        self.borrow("M001", "D001")

        response = self.borrow("M002", "D001")

        self.assertEqual(len(self.loans()), 1)
        self.assertIn(b"unavailable", response.data)

    def test_member_can_hold_several_ducks(self):
        self.borrow("M001", "D001")
        self.borrow("M001", "D002")

        self.assertEqual(len(self.loans()), 2)


if __name__ == "__main__":
    unittest.main()
