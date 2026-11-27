# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models


class AccountPayment(models.Model):
    _name = "account.payment"
    _inherit = ["account.payment", "payment.installment.mixin"]

    @api.model_create_multi
    def create(self, vals_list):
        """Complete the installment amounts left out by the caller."""
        for vals in vals_list:
            installments = vals.get("installments") or 1
            vals["installments"] = installments
            if installments > 1 or vals.get("installment_interest_amount"):
                amount = vals.get("amount") or 0.0
                interest = vals.get("installment_interest_amount") or 0.0
                if (
                    vals.get("installment_interest_bearer") == "company"
                    or vals.get("installment_interest_charged_by") == "merchant"
                ):
                    interest = 0.0
                vals.setdefault("amount_charged", amount + interest)
                vals.setdefault(
                    "installment_amount", vals["amount_charged"] / installments
                )
        return super().create(vals_list)
