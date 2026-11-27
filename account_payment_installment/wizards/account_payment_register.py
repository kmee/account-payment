# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    installment_plan_id = fields.Many2one(
        comodel_name="payment.installment.plan",
        compute="_compute_installment_plan_id",
    )
    installment_plan_line_id = fields.Many2one(
        comodel_name="payment.installment.plan.line",
        string="Installments",
        domain="[('plan_id', '=', installment_plan_id)]",
        compute="_compute_installment_plan_line_id",
        store=True,
        readonly=False,
        help="Leave empty for a payment in a single installment.",
    )
    card_brand_id = fields.Many2one(
        comodel_name="payment.method",
        string="Card Brand",
        domain="[('is_primary', '=', False)]",
    )
    acquirer_reference = fields.Char(
        help="Reference of the payment at the card acquirer, as printed on the "
        "terminal receipt and on the acquirer statements (NSU in Brazil).",
    )
    authorization_code = fields.Char()

    @api.depends("journal_id", "payment_type", "can_edit_wizard")
    def _compute_installment_plan_id(self):
        for wizard in self:
            plan = self.env["payment.installment.plan"]
            if (
                wizard.journal_id
                and wizard.payment_type == "inbound"
                and wizard.can_edit_wizard
            ):
                plan = wizard.journal_id._get_installment_plan()
            wizard.installment_plan_id = plan

    @api.depends("journal_id")
    def _compute_installment_plan_line_id(self):
        for wizard in self:
            if wizard.installment_plan_line_id.plan_id != wizard.installment_plan_id:
                wizard.installment_plan_line_id = False

    def _get_installment_payment_values(self):
        """Return the installment and card values of the payment to create."""
        self.ensure_one()
        values = {
            "card_brand_id": self.card_brand_id.id,
            "acquirer_reference": self.acquirer_reference,
            "authorization_code": self.authorization_code,
        }
        line = self.installment_plan_line_id
        if not line:
            return values
        if line._is_surcharge():
            raise UserError(
                _(
                    "The interest of this option is charged by the company and "
                    "must be on the invoice: it cannot be added when the payment "
                    "is registered."
                )
            )
        options = line.plan_id._get_options(self.amount, self.currency_id)
        option = next((opt for opt in options if opt["line_id"] == line.id), None)
        if not option:
            raise UserError(
                _(
                    "Paying %(amount)s in %(count)s installments is below the "
                    "minimum installment of the plan.",
                    amount=self.currency_id.format(self.amount),
                    count=line.installments,
                )
            )
        values.update(
            {
                "installments": option["installments"],
                "installment_plan_line_id": line.id,
                "installment_amount": option["installment_amount"],
                "installment_interest_amount": option["interest_amount"],
                "installment_interest_bearer": option["interest_bearer"],
                "installment_interest_charged_by": option["interest_charged_by"],
                "amount_charged": option["total_amount"],
            }
        )
        return values

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.payment_type == "inbound":
            payment_vals.update(self._get_installment_payment_values())
        return payment_vals
