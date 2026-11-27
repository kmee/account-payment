# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAccountPaymentInstallment(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.company_data["default_journal_bank"]
        cls.plan = cls.env["payment.installment.plan"].create(
            {
                "name": "Card terminal",
                "journal_ids": [Command.set(cls.journal.ids)],
                "currency_id": cls.env.company.currency_id.id,
                "min_installment_amount": 50.0,
                "line_ids": [
                    Command.create({"installments": 3}),
                    Command.create(
                        {
                            "installments": 6,
                            "interest_rate": 5.0,
                            "interest_bearer": "company",
                        }
                    ),
                    Command.create({"installments": 10, "interest_rate": 8.0}),
                    Command.create(
                        {
                            "installments": 12,
                            "interest_rate": 10.0,
                            "interest_charged_by": "merchant",
                        }
                    ),
                ],
            }
        )
        cls.invoice = cls.init_invoice(
            "out_invoice", amounts=[1200.0], taxes=cls.env["account.tax"], post=True
        )

    def _line(self, installments):
        return self.plan.line_ids.filtered(lambda x: x.installments == installments)

    def _wizard(self, invoice=None, **values):
        invoice = invoice or self.invoice
        return (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create({"journal_id": self.journal.id, **values})
        )

    def test_plan_of_the_journal(self):
        self.assertEqual(self.journal._get_installment_plan(), self.plan)
        self.assertEqual(self._wizard().installment_plan_id, self.plan)
        other = self.company_data["default_journal_cash"]
        self.assertFalse(other._get_installment_plan())

    def test_payment_in_a_single_installment(self):
        payment = self._wizard(acquirer_reference="123456")._create_payments()
        self.assertEqual(payment.installments, 1)
        self.assertEqual(payment.acquirer_reference, "123456")
        self.assertEqual(self.invoice.amount_residual, 0.0)

    def test_payment_in_installments_keeps_the_card_data(self):
        payment = self._wizard(
            installment_plan_line_id=self._line(3).id,
            acquirer_reference="123456",
            authorization_code="A1B2C3",
        )._create_payments()
        self.assertEqual(payment.amount, 1200.0)
        self.assertEqual(payment.installments, 3)
        self.assertEqual(payment.installment_amount, 400.0)
        self.assertFalse(payment.installment_interest_amount)
        self.assertEqual(payment.amount_charged, 1200.0)
        self.assertEqual(payment.acquirer_reference, "123456")
        self.assertEqual(payment.authorization_code, "A1B2C3")
        self.assertEqual(self.invoice.amount_residual, 0.0)

    def test_interest_of_the_issuer_does_not_change_the_payment(self):
        payment = self._wizard(
            installment_plan_line_id=self._line(10).id
        )._create_payments()
        self.assertEqual(payment.amount, 1200.0)
        self.assertEqual(payment.installment_interest_amount, 96.0)
        self.assertEqual(payment.installment_interest_bearer, "customer")
        self.assertEqual(payment.installment_interest_charged_by, "provider")
        self.assertEqual(payment.amount_charged, 1296.0)
        self.assertEqual(payment.installment_amount, 129.6)
        self.assertEqual(self.invoice.amount_residual, 0.0)

    def test_interest_borne_by_the_company(self):
        payment = self._wizard(
            installment_plan_line_id=self._line(6).id
        )._create_payments()
        self.assertEqual(payment.installment_interest_bearer, "company")
        self.assertEqual(payment.installment_interest_amount, 60.0)
        self.assertEqual(payment.amount_charged, 1200.0)
        self.assertEqual(payment.installment_amount, 200.0)

    def test_interest_charged_by_the_company_must_be_on_the_invoice(self):
        with self.assertRaises(UserError):
            self._wizard(installment_plan_line_id=self._line(12).id)._create_payments()

    def test_minimum_installment_amount(self):
        invoice = self.init_invoice(
            "out_invoice", amounts=[120.0], taxes=self.env["account.tax"], post=True
        )
        with self.assertRaises(UserError):
            self._wizard(
                invoice=invoice, installment_plan_line_id=self._line(3).id
            )._create_payments()

    def test_changing_the_journal_drops_the_option(self):
        wizard = self._wizard(installment_plan_line_id=self._line(3).id)
        wizard.journal_id = self.company_data["default_journal_cash"]
        self.assertFalse(wizard.installment_plan_id)
        self.assertFalse(wizard.installment_plan_line_id)
