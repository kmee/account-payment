# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from odoo.addons.account_payment.tests.common import AccountPaymentCommon

from .common import CardReceivableCommon


@tagged("post_install", "-at_install")
class TestCardOnline(AccountPaymentCommon, CardReceivableCommon):
    """A payment made online ends at the bank the same way."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider.journal_id.card_acquirer_id = cls.acquirer
        cls.provider.journal_id.inbound_payment_method_line_ids.filtered(
            lambda line: line.payment_provider_id == cls.provider
        ).payment_account_id = cls.outstanding_account

    def test_transaction_in_installments_opens_the_receivables(self):
        self.enable_post_process_patcher = False
        invoice = self._invoice(1200.0)
        tx = self._create_transaction(
            "redirect",
            amount=1200.0,
            currency_id=invoice.currency_id.id,
            partner_id=invoice.partner_id.id,
            invoice_ids=[(6, 0, invoice.ids)],
            installments=3,
            acquirer_reference="300001",
            authorization_code="ZZZ999",
        )
        tx._set_done()
        tx._post_process()
        payment = tx.payment_id
        self.assertEqual(payment.installments, 3)
        self.assertEqual(payment.installment_amount, 400.0)
        self.assertEqual(payment.acquirer_reference, "300001")
        self.assertEqual(payment.authorization_code, "ZZZ999")
        receivables = self._receivables(payment)
        self.assertEqual(receivables.mapped("debit"), [400.0] * 3)
        self.assertEqual(set(receivables.mapped("card_acquirer_reference")), {"300001"})
        lines = self._settlement_lines("300001", [400.0] * 3, 4.0)
        for line in lines:
            # The transaction is made today: settle on the due dates of Odoo.
            line["sale_date"] = payment.date
            line["payment_date"] = payment.date
        statement = self._statement(lines)
        self.assertEqual(set(statement.line_ids.mapped("state")), {"matched"})
        statement.action_reconcile()
        banked = self._bank_deposits()
        self.assertClosed(invoice, banked, fees=48.0)
