# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from .test_installment_plan import InstallmentCommon


@tagged("post_install", "-at_install")
class TestPaymentTransaction(InstallmentCommon):
    def test_single_installment_by_default(self):
        tx = self._create_transaction("redirect", amount=1000.0)
        self.assertEqual(tx.installments, 1)
        self.assertEqual(tx.installment_amount, 1000.0)
        self.assertEqual(tx.amount_charged, 1000.0)

    def test_interest_paid_by_the_customer(self):
        tx = self._create_transaction(
            "redirect",
            amount=1000.0,
            installments=10,
            installment_interest_amount=50.0,
            installment_interest_bearer="customer",
        )
        self.assertEqual(tx.amount, 1000.0)
        self.assertEqual(tx.amount_charged, 1050.0)
        self.assertEqual(tx.installment_amount, 105.0)
        tx.installments = 5
        self.assertEqual(tx.installment_amount, 210.0)
        tx.amount_charged = 1062.5
        self.assertEqual(tx.amount_charged, 1062.5)

    def test_interest_paid_by_the_company(self):
        tx = self._create_transaction(
            "redirect",
            amount=1000.0,
            installments=10,
            installment_interest_amount=50.0,
            installment_interest_bearer="company",
        )
        self.assertEqual(tx.amount_charged, 1000.0)
        self.assertEqual(tx.installment_amount, 100.0)
