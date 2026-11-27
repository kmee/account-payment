# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment.controllers import portal as payment_portal


class PaymentPortal(payment_portal.PaymentPortal):
    @staticmethod
    def _validate_transaction_kwargs(kwargs, additional_allowed_keys=()):
        """Let the transaction routes receive the number of installments."""
        return payment_portal.PaymentPortal._validate_transaction_kwargs(
            kwargs,
            additional_allowed_keys=(*additional_allowed_keys, "installments"),
        )

    def _create_transaction(
        self, *args, installments=None, custom_create_values=None, **kwargs
    ):
        """Check the installments chosen by the payer and store them.

        Whatever the document being paid (sales order, invoice, payment link),
        the routes end up here, so the check is done once for all of them.
        """
        installments = int(installments or 1)
        if installments > 1:
            if kwargs.get("is_validation") or kwargs.get("flow") == "token":
                raise ValidationError(
                    _("A saved payment method is charged in a single installment.")
                )
            provider_sudo = (
                request.env["payment.provider"].sudo().browse(kwargs.get("provider_id"))
            )
            payment_method_sudo = (
                request.env["payment.method"]
                .sudo()
                .browse(kwargs.get("payment_method_id"))
            )
            currency = request.env["res.currency"].browse(kwargs.get("currency_id"))
            installment_values = request.env[
                "payment.transaction"
            ]._get_checked_installment_values(
                provider_sudo,
                payment_method_sudo,
                kwargs.get("amount"),
                currency,
                installments,
            )
            custom_create_values = {
                **(custom_create_values or {}),
                **installment_values,
            }
        return super()._create_transaction(
            *args, custom_create_values=custom_create_values, **kwargs
        )
