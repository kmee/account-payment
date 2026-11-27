# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _create_payment(self, **extra_create_values):
        """Hand the installments and the card data over to the payment."""
        return super()._create_payment(
            **{**self._get_installment_values(), **extra_create_values}
        )
