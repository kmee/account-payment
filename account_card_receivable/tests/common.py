# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import Command, fields

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class CardReceivableCommon(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.currency = cls.env.company.currency_id
        # Sales are old enough for every installment to have been settled.
        cls.sale_date = fields.Date.today() - timedelta(days=400)

        def account(code, name, account_type, reconcile=False):
            return cls.env["account.account"].create(
                {
                    "code": code,
                    "name": name,
                    "account_type": account_type,
                    "reconcile": reconcile,
                }
            )

        cls.outstanding_account = account(
            "101481", "Card payments to classify", "asset_current", True
        )
        cls.receivable_account = account(
            "101482", "Receivable from acquirers", "asset_current", True
        )
        cls.clearing_account = account(
            "101483", "Acquirers to settle", "asset_current", True
        )
        cls.fee_account = account("601481", "Card fees", "expense")
        cls.adjustment_account = account("601482", "Acquirer adjustments", "expense")
        cls.chargeback_account = account("601483", "Chargebacks", "expense")
        cls.acquirer_partner = cls.env["res.partner"].create({"name": "Acquirer"})
        cls.acquirer = cls.env["account.card.acquirer"].create(
            {
                "name": "Acquirer",
                "partner_id": cls.acquirer_partner.id,
                "journal_id": cls.company_data["default_journal_misc"].id,
                "receivable_account_id": cls.receivable_account.id,
                "clearing_account_id": cls.clearing_account.id,
                "fee_account_id": cls.fee_account.id,
                "adjustment_account_id": cls.adjustment_account.id,
                "chargeback_account_id": cls.chargeback_account.id,
                "rule_ids": [
                    Command.create({"modality": "credit", "fee_percent": 3.0}),
                    Command.create(
                        {
                            "modality": "installment_issuer",
                            "installments_from": 2,
                            "installments_to": 12,
                            "fee_percent": 3.0,
                        }
                    ),
                    Command.create(
                        {
                            "modality": "installment_merchant",
                            "installments_from": 2,
                            "installments_to": 12,
                            "fee_percent": 4.0,
                        }
                    ),
                ],
            }
        )
        cls.card_journal = cls.env["account.journal"].create(
            {
                "name": "Card",
                "code": "CARD",
                "type": "bank",
                "card_acquirer_id": cls.acquirer.id,
            }
        )
        cls.card_journal.inbound_payment_method_line_ids.payment_account_id = (
            cls.outstanding_account
        )
        cls.bank_journal = cls.company_data["default_journal_bank"]

    # === Steps of a sale === #

    def _invoice(self, amount):
        return self.init_invoice(
            "out_invoice",
            partner=self.partner_a,
            invoice_date=self.sale_date,
            amounts=[amount],
            taxes=self.env["account.tax"],
            post=True,
        )

    def _pay(self, invoice, amount=None, **values):
        """Register a card payment of the invoice, as any channel would."""
        payment = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": invoice.partner_id.id,
                "journal_id": self.card_journal.id,
                "date": self.sale_date,
                "amount": invoice.amount_residual if amount is None else amount,
                **values,
            }
        )
        payment.action_post()
        counterpart = payment._seek_for_lines()[1]
        receivable = invoice.line_ids.filtered(
            lambda line: line.account_id == counterpart.account_id
            and not line.reconciled
        )
        (counterpart | receivable).reconcile()
        return payment

    def _receivables(self, payment):
        return payment.card_transfer_move_ids.line_ids.filtered(
            "card_acquirer_id"
        ).sorted("card_installment")

    def _statement(self, lines):
        statement = self.env["account.card.statement"].create(
            {
                "acquirer_id": self.acquirer.id,
                "line_ids": [Command.create(values) for values in lines],
            }
        )
        statement.action_match()
        return statement

    def _settlement_lines(self, reference, amounts, fee_percent, start=30, **extra):
        """Statement lines of a sale settled in `amounts`, one per month."""
        lines = []
        for index, gross in enumerate(amounts):
            fee = self.currency.round(gross * fee_percent / 100)
            lines.append(
                {
                    "payment_date": self.sale_date
                    + timedelta(days=start + 30 * index),
                    "sale_date": self.sale_date,
                    "reference": reference,
                    "installment": index + 1,
                    "installment_count": len(amounts),
                    "gross_amount": gross,
                    "fee_amount": fee,
                    "net_amount": self.currency.round(gross - fee),
                    **extra,
                }
            )
        return lines

    def _bank_deposits(self):
        """Receive in the bank what the acquirer says it paid, day by day.

        :return: The total received.
        """
        open_lines = self.env["account.move.line"].search(
            [
                ("account_id", "=", self.clearing_account.id),
                ("parent_state", "=", "posted"),
                ("reconciled", "=", False),
            ]
        )
        total = 0.0
        for line in open_lines:
            amount = line.amount_residual
            total += amount
            deposit = self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "journal_id": self.bank_journal.id,
                    "date": line.date_maturity or line.date,
                    "line_ids": [
                        Command.create(
                            {
                                "name": "Deposit",
                                "account_id": self.bank_journal.default_account_id.id,
                                "debit": amount if amount > 0 else 0.0,
                                "credit": -amount if amount < 0 else 0.0,
                            }
                        ),
                        Command.create(
                            {
                                "name": "Deposit",
                                "account_id": self.clearing_account.id,
                                "partner_id": self.acquirer_partner.id,
                                "debit": -amount if amount < 0 else 0.0,
                                "credit": amount if amount > 0 else 0.0,
                            }
                        ),
                    ],
                }
            )
            deposit.action_post()
            (
                line
                | deposit.line_ids.filtered(
                    lambda aml: aml.account_id == self.clearing_account
                )
            ).reconcile()
        return self.currency.round(total)

    # === The proof === #

    def _balance(self, account):
        lines = self.env["account.move.line"].search(
            [("account_id", "=", account.id), ("parent_state", "=", "posted")]
        )
        return self.currency.round(sum(lines.mapped("balance")))

    def _open_lines(self, account):
        return self.env["account.move.line"].search(
            [
                ("account_id", "=", account.id),
                ("parent_state", "=", "posted"),
                ("reconciled", "=", False),
            ]
        )

    def assertClosed(self, invoices, banked, fees):
        """The accounts between the customer and the bank are all at zero, and
        what reached the bank plus the fees is what was invoiced."""
        for invoice in invoices:
            self.assertEqual(invoice.amount_residual, 0.0, "customer still owes")
            self.assertEqual(invoice.payment_state, "paid")
        for account in (
            self.outstanding_account,
            self.receivable_account,
            self.clearing_account,
        ):
            self.assertEqual(self._balance(account), 0.0, account.name)
            self.assertFalse(self._open_lines(account), account.name)
        self.assertEqual(
            self.acquirer._get_balances(), {"receivable": 0.0, "clearing": 0.0}
        )
        self.assertAlmostEqual(self._balance(self.fee_account), fees, places=2)
        self.assertAlmostEqual(
            banked + fees, sum(invoices.mapped("amount_total")), places=2
        )
