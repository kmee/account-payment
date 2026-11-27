# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    card_acquirer_id = fields.Many2one(
        related="journal_id.card_acquirer_id", string="Card Acquirer"
    )
    card_transfer_move_ids = fields.One2many(
        comodel_name="account.move",
        inverse_name="card_payment_id",
        string="Acquirer Receivable Entries",
    )

    def _get_card_modality(self):
        """Return how the acquirer treats the payment.

        Installments whose interest the provider charges are financed by the
        card issuer; the others are financed by the company, whether it charges
        interest for them or not.
        """
        self.ensure_one()
        if self.installments > 1:
            if self.installment_interest_charged_by == "provider":
                return "installment_issuer"
            return "installment_merchant"
        return self.journal_id.card_modality or "credit"

    def action_post(self):
        res = super().action_post()
        self._card_open_receivables()
        return res

    def action_draft(self):
        self._card_remove_receivables()
        return super().action_draft()

    def action_cancel(self):
        self._card_remove_receivables()
        return super().action_cancel()

    def _card_open_receivables(self):
        """Move what was paid to the acquirer, one receivable per settlement.

        The payment is in a journal of a card acquirer: the money is not in the
        bank, the acquirer owes it. The outstanding line of the payment is
        settled against as many receivables as the acquirer will make
        settlements, each one with its due date.

        Every payment opens its own receivables, for its own amount: two cards
        on the same invoice are two debts of the acquirer.
        """
        for payment in self:
            acquirer = payment.card_acquirer_id
            if (
                not acquirer
                or payment.payment_type != "inbound"
                or payment.partner_type != "customer"
                or payment.move_id.state != "posted"
                or payment.card_transfer_move_ids.filtered(
                    lambda move: move.state == "posted"
                )
            ):
                continue
            liquidity_lines = payment._seek_for_lines()[0].filtered(
                lambda line: line.account_id.reconcile and not line.reconciled
            )
            amount = sum(liquidity_lines.mapped("amount_residual"))
            if payment.company_currency_id.compare_amounts(amount, 0.0) <= 0:
                continue
            payment._card_create_transfer(acquirer, liquidity_lines, amount)

    def _card_create_transfer(self, acquirer, liquidity_lines, amount):
        self.ensure_one()
        modality = self._get_card_modality()
        label = " ".join(
            part
            for part in (
                self.card_brand_id.name,
                self.acquirer_reference and _("ref. %s", self.acquirer_reference),
                self.name,
            )
            if part
        )
        common = {
            "card_acquirer_id": acquirer.id,
            "card_payment_id": self.id,
            "card_modality": modality,
            "card_acquirer_reference": self.acquirer_reference,
            "card_authorization_code": self.authorization_code,
            "card_brand_id": self.card_brand_id.id,
            "card_sale_date": self.date,
        }
        line_vals = [
            {
                "name": label,
                "account_id": liquidity_lines[0].account_id.id,
                "partner_id": liquidity_lines[0].partner_id.id,
                "debit": 0.0,
                "credit": amount,
            }
        ]
        for number, count, value, due in acquirer._get_settlements(
            modality, self.installments, amount, self.date, self.card_brand_id
        ):
            line_vals.append(
                {
                    **common,
                    "name": _(
                        "%(label)s %(number)s/%(count)s",
                        label=label,
                        number=number,
                        count=count,
                    ),
                    "account_id": acquirer.receivable_account_id.id,
                    "partner_id": acquirer.partner_id.id,
                    "debit": value,
                    "credit": 0.0,
                    "date_maturity": due,
                    "card_installment": number,
                    "card_installment_count": count,
                }
            )
        transfer = (
            self.env["account.move"]
            .sudo()
            .create(
                {
                    "move_type": "entry",
                    "journal_id": acquirer.journal_id.id,
                    "company_id": self.company_id.id,
                    "date": self.date,
                    "ref": label,
                    "card_payment_id": self.id,
                    "line_ids": [fields.Command.create(vals) for vals in line_vals],
                }
            )
        )
        transfer.action_post()
        counterpart = transfer.line_ids.filtered(
            lambda line: line.account_id == liquidity_lines[0].account_id
        )
        (counterpart | liquidity_lines).reconcile()
        return transfer

    def _card_remove_receivables(self):
        """Take the receivables back from the acquirer, if none was settled."""
        for payment in self:
            transfers = payment.card_transfer_move_ids.filtered(
                lambda move: move.state == "posted"
            )
            if not transfers:
                continue
            receivables = transfers.line_ids.filtered("card_acquirer_id")
            if any(line.matched_credit_ids for line in receivables):
                raise UserError(
                    _(
                        "The acquirer has already settled part of payment "
                        "%(payment)s: it cannot be reset or cancelled.",
                        payment=payment.display_name,
                    )
                )
            transfers.line_ids.remove_move_reconcile()
            transfers.button_draft()
            transfers.button_cancel()

    def _card_reconcile_rounding(self, acquirer):
        """Close the cents the acquirer put on another installment.

        The acquirer divides a sale its own way: a cent may be on the last
        installment where the receivables have it on the first one. Once the
        acquirer has settled the whole sale, what is left open on each side is
        the same cents and they close each other. If the sale as a whole does
        not match, nothing is closed and the difference stays visible.
        """
        for payment in self:
            leftovers = self.env["account.move.line"].search(
                [
                    ("card_payment_id", "=", payment.id),
                    ("account_id", "=", acquirer.receivable_account_id.id),
                    ("parent_state", "=", "posted"),
                    ("reconciled", "=", False),
                ]
            )
            if not leftovers:
                continue
            currency = payment.company_currency_id
            if currency.is_zero(sum(leftovers.mapped("amount_residual"))) and all(
                abs(line.amount_residual) <= acquirer.amount_tolerance
                for line in leftovers
            ):
                leftovers.reconcile()
