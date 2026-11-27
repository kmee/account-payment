# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PaymentInstallmentMixin(models.AbstractModel):
    """What a payment made in installments is, wherever it is recorded.

    The same fields describe an online transaction, a payment registered by
    hand and a point of sale payment, so that what comes next (receivables from
    the card acquirer, reconciliation) does not depend on the channel.

    The model using the mixin must have a `currency_id` field.
    """

    _name = "payment.installment.mixin"
    _description = "Payment Installment Mixin"

    # Declared for the monetary fields below; the models using the mixin have
    # their own definition of the field.
    currency_id = fields.Many2one(comodel_name="res.currency")
    installments = fields.Integer(default=1, copy=False)
    installment_plan_line_id = fields.Many2one(
        comodel_name="payment.installment.plan.line",
        string="Installment Option",
        ondelete="set null",
        copy=False,
    )
    installment_amount = fields.Monetary(copy=False)
    installment_interest_amount = fields.Monetary(
        string="Installment Interest",
        copy=False,
        help="Interest charged for the installments.",
    )
    installment_interest_bearer = fields.Selection(
        selection=[("customer", "Customer"), ("company", "Company")],
        string="Interest Paid By",
        copy=False,
        help="Customer: the interest is charged to the payer.\n"
        "Company: the payer pays the amount and the company bears the interest "
        "as a cost of the sale.",
    )
    installment_interest_charged_by = fields.Selection(
        selection=[("provider", "Provider"), ("merchant", "Company")],
        string="Interest Charged By",
        copy=False,
        help="Provider: the provider (or the card issuer) charges the interest "
        "on top of the amount.\n"
        "Company: the interest is a surcharge of the document being paid and is "
        "already part of the amount.",
    )
    amount_charged = fields.Monetary(
        copy=False,
        help="What the payer is charged: the amount, plus the interest when the "
        "customer pays it to the provider.",
    )
    card_brand_id = fields.Many2one(
        comodel_name="payment.method",
        string="Card Brand",
        domain="[('is_primary', '=', False)]",
        copy=False,
    )
    acquirer_reference = fields.Char(
        copy=False,
        help="Reference of the payment at the card acquirer, as printed on the "
        "acquirer statements (NSU in Brazil).",
    )
    authorization_code = fields.Char(copy=False)

    def _get_installment_field_names(self):
        return [
            "installments",
            "installment_plan_line_id",
            "installment_amount",
            "installment_interest_amount",
            "installment_interest_bearer",
            "installment_interest_charged_by",
            "amount_charged",
            "card_brand_id",
            "acquirer_reference",
            "authorization_code",
        ]

    def _get_installment_values(self):
        """Return the installment data of the record, as create values.

        Used to hand the data over from one record to the next one, such as
        from a transaction to the payment created for it.
        """
        self.ensure_one()
        return self._convert_to_write(
            {name: self[name] for name in self._get_installment_field_names()}
        )
