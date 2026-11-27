# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    _sql_constraints = [
        (
            "installments_positive",
            "CHECK(installments >= 1)",
            "A transaction has at least one installment.",
        ),
    ]

    installments = fields.Integer(default=1, readonly=True, copy=False)
    installment_interest_amount = fields.Monetary(
        string="Installment Interest", readonly=True, copy=False
    )
    installment_interest_bearer = fields.Selection(
        selection=[("customer", "Customer"), ("company", "Company")],
        string="Interest Paid By",
        readonly=True,
        copy=False,
    )
    amount_charged = fields.Monetary(
        compute="_compute_installment_amounts",
        store=True,
        readonly=True,
        copy=False,
        help="The amount plus the interest paid by the customer.",
    )
    installment_amount = fields.Monetary(
        compute="_compute_installment_amounts",
        store=True,
        readonly=True,
        copy=False,
    )

    @api.depends(
        "amount",
        "installments",
        "installment_interest_amount",
        "installment_interest_bearer",
    )
    def _compute_installment_amounts(self):
        for tx in self:
            interest = (
                tx.installment_interest_amount
                if tx.installment_interest_bearer == "customer"
                else 0.0
            )
            tx.amount_charged = tx.currency_id.round(tx.amount + interest)
            tx.installment_amount = tx.currency_id.round(
                tx.amount_charged / max(tx.installments, 1)
            )
