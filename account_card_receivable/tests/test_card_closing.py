# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import CardReceivableCommon


@tagged("post_install", "-at_install")
class TestCardClosing(CardReceivableCommon):
    """From the sale to the bank: every account in between ends at zero."""

    def test_interest_charged_by_the_issuer_is_settled_at_once(self):
        """The card holder pays ten installments to the issuer; the acquirer
        pays the sale to the company in a single settlement."""
        invoice = self._invoice(1200.0)
        payment = self._pay(
            invoice,
            installments=10,
            installment_interest_amount=96.0,
            installment_interest_bearer="customer",
            installment_interest_charged_by="provider",
            acquirer_reference="100001",
        )
        receivables = self._receivables(payment)
        self.assertEqual(receivables.mapped("debit"), [1200.0])
        self.assertEqual(receivables.card_modality, "installment_issuer")
        self.assertEqual(
            receivables.date_maturity, self.sale_date + timedelta(days=30)
        )
        statement = self._statement(
            self._settlement_lines("100001", [1200.0], 3.0, installment_count=10)
        )
        self.assertEqual(statement.line_ids.state, "matched")
        self.assertEqual(statement.line_ids.fee_difference, 0.0)
        statement.action_reconcile()
        self.assertEqual(statement.state, "done")
        banked = self._bank_deposits()
        self.assertEqual(banked, 1164.0)
        self.assertClosed(invoice, banked, fees=36.0)

    def test_interest_charged_by_the_company_is_settled_per_installment(self):
        """The surcharge is on the invoice: the acquirer owes twelve
        installments of the invoice total."""
        invoice = self._invoice(1320.0)
        payment = self._pay(
            invoice,
            installments=12,
            installment_interest_amount=120.0,
            installment_interest_bearer="customer",
            installment_interest_charged_by="merchant",
            acquirer_reference="100002",
        )
        receivables = self._receivables(payment)
        self.assertEqual(receivables.mapped("debit"), [110.0] * 12)
        self.assertEqual(set(receivables.mapped("card_modality")), {"installment_merchant"})
        self.assertEqual(
            receivables[-1].date_maturity, self.sale_date + timedelta(days=360)
        )
        statement = self._statement(
            self._settlement_lines("100002", [110.0] * 12, 4.0)
        )
        self.assertEqual(set(statement.line_ids.mapped("state")), {"matched"})
        statement.action_reconcile()
        banked = self._bank_deposits()
        self.assertEqual(banked, 1267.2)
        self.assertClosed(invoice, banked, fees=52.8)

    def test_interest_borne_by_the_company_is_settled_per_installment(self):
        invoice = self._invoice(1200.0)
        payment = self._pay(
            invoice,
            installments=6,
            installment_interest_amount=60.0,
            installment_interest_bearer="company",
            acquirer_reference="100003",
        )
        self.assertEqual(self._receivables(payment).mapped("debit"), [200.0] * 6)
        statement = self._statement(self._settlement_lines("100003", [200.0] * 6, 4.0))
        statement.action_reconcile()
        banked = self._bank_deposits()
        self.assertEqual(banked, 1152.0)
        # The cost of the installments is what the acquirer charged, not the
        # estimate of the plan.
        self.assertClosed(invoice, banked, fees=48.0)

    def test_single_installment(self):
        invoice = self._invoice(500.0)
        payment = self._pay(invoice, acquirer_reference="100004")
        self.assertEqual(self._receivables(payment).mapped("debit"), [500.0])
        statement = self._statement(self._settlement_lines("100004", [500.0], 3.0))
        statement.action_reconcile()
        banked = self._bank_deposits()
        self.assertClosed(invoice, banked, fees=15.0)

    def test_cents_on_another_installment_still_close(self):
        """Odoo puts the cent of the division on the first installment, this
        acquirer on the last one."""
        invoice = self._invoice(1000.0)
        payment = self._pay(invoice, installments=3, acquirer_reference="100005")
        self.assertEqual(
            self._receivables(payment).mapped("debit"), [333.34, 333.33, 333.33]
        )
        statement = self._statement(
            self._settlement_lines("100005", [333.33, 333.33, 333.34], 4.0)
        )
        self.assertEqual(set(statement.line_ids.mapped("state")), {"matched"})
        statement.action_reconcile()
        banked = self._bank_deposits()
        self.assertClosed(invoice, banked, fees=self._balance(self.fee_account))

    def test_cents_follow_the_setting_of_the_acquirer(self):
        self.acquirer.rounding_installment = "last"
        invoice = self._invoice(1000.0)
        payment = self._pay(invoice, installments=3, acquirer_reference="100006")
        self.assertEqual(
            self._receivables(payment).mapped("debit"), [333.33, 333.33, 333.34]
        )

    def test_sale_that_does_not_match_as_a_whole_stays_open(self):
        """Cents are forgiven between installments, never on the sale."""
        invoice = self._invoice(1000.0)
        self._pay(invoice, installments=3, acquirer_reference="100007")
        statement = self._statement(
            self._settlement_lines("100007", [333.33, 333.33, 333.30], 4.0)
        )
        statement.action_reconcile()
        self._bank_deposits()
        self.assertEqual(self._balance(self.receivable_account), 0.04)
        self.assertTrue(self._open_lines(self.receivable_account))

    def test_two_cards_on_the_same_invoice(self):
        invoice = self._invoice(1200.0)
        first = self._pay(
            invoice, amount=600.0, installments=3, acquirer_reference="100008"
        )
        self.assertEqual(invoice.amount_residual, 600.0)
        second = self._pay(invoice, amount=600.0, acquirer_reference="100009")
        self.assertEqual(self._receivables(first).mapped("debit"), [200.0] * 3)
        self.assertEqual(self._receivables(second).mapped("debit"), [600.0])
        statement = self._statement(
            self._settlement_lines("100008", [200.0] * 3, 4.0)
            + self._settlement_lines("100009", [600.0], 3.0)
        )
        statement.action_reconcile()
        banked = self._bank_deposits()
        self.assertClosed(invoice, banked, fees=42.0)

    def test_partial_payment_opens_only_what_was_paid(self):
        invoice = self._invoice(1200.0)
        payment = self._pay(invoice, amount=500.0, acquirer_reference="100010")
        self.assertEqual(invoice.amount_residual, 700.0)
        self.assertEqual(self._receivables(payment).mapped("debit"), [500.0])
        self.assertEqual(self._balance(self.receivable_account), 500.0)

    def test_payment_in_another_journal_is_not_owed_by_the_acquirer(self):
        invoice = self._invoice(300.0)
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": invoice.partner_id.id,
                "journal_id": self.bank_journal.id,
                "amount": 300.0,
            }
        )
        payment.action_post()
        self.assertFalse(payment.card_transfer_move_ids)

    def test_resetting_a_payment_takes_the_receivables_back(self):
        invoice = self._invoice(600.0)
        payment = self._pay(invoice, installments=3, acquirer_reference="100011")
        self.assertEqual(self._balance(self.receivable_account), 600.0)
        payment.action_draft()
        self.assertEqual(self._balance(self.receivable_account), 0.0)
        self.assertEqual(self._balance(self.outstanding_account), 0.0)

    def test_settled_payment_cannot_be_reset(self):
        invoice = self._invoice(600.0)
        payment = self._pay(invoice, acquirer_reference="100012")
        self._statement(
            self._settlement_lines("100012", [600.0], 3.0)
        ).action_reconcile()
        with self.assertRaises(UserError):
            payment.action_draft()

    def test_payment_registered_from_the_invoice(self):
        """The wizard of the invoice is one of the channels."""
        plan = self.env["payment.installment.plan"].create(
            {
                "name": "Card terminal",
                "journal_ids": [(6, 0, self.card_journal.ids)],
                "currency_id": self.currency.id,
                "line_ids": [(0, 0, {"installments": 3})],
            }
        )
        invoice = self._invoice(900.0)
        payment = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create(
                {
                    "journal_id": self.card_journal.id,
                    "payment_date": self.sale_date,
                    "installment_plan_line_id": plan.line_ids.id,
                    "acquirer_reference": "100013",
                }
            )
            ._create_payments()
        )
        self.assertEqual(self._receivables(payment).mapped("debit"), [300.0] * 3)
        statement = self._statement(self._settlement_lines("100013", [300.0] * 3, 4.0))
        statement.action_reconcile()
        banked = self._bank_deposits()
        self.assertClosed(invoice, banked, fees=36.0)
