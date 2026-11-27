# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment.controllers import portal as payment_portal


class PaymentPortal(payment_portal.PaymentPortal):
    @staticmethod
    def _validate_transaction_kwargs(kwargs, additional_allowed_keys=()):
        return payment_portal.PaymentPortal._validate_transaction_kwargs(
            kwargs,
            additional_allowed_keys=(*additional_allowed_keys, "installments"),
        )

    def _create_transaction(
        self, *args, installments=None, custom_create_values=None, **kwargs
    ):
        installments = int(installments or 1)
        if installments > 1:
            option = self._get_installment_option(installments, **kwargs)
            custom_create_values = {
                **(custom_create_values or {}),
                "installments": installments,
                "installment_interest_amount": option["interest_amount"],
                "installment_interest_bearer": option["interest_bearer"],
            }
        return super()._create_transaction(
            *args, custom_create_values=custom_create_values, **kwargs
        )

    def _get_installment_option(self, installments, **kwargs):
        """Return the option chosen by the payer, if the provider offers it."""
        if kwargs.get("is_validation") or kwargs.get("flow") == "token":
            raise ValidationError(
                _("A saved payment method is charged in a single installment.")
            )
        provider_sudo = (
            request.env["payment.provider"].sudo().browse(kwargs.get("provider_id"))
        )
        payment_method_sudo = (
            request.env["payment.method"].sudo().browse(kwargs.get("payment_method_id"))
        )
        currency = request.env["res.currency"].browse(kwargs.get("currency_id"))
        options = provider_sudo._get_installment_options(
            payment_method_sudo, kwargs.get("amount"), currency
        )
        option = next(
            (opt for opt in options if opt["installments"] == installments), None
        )
        if not option:
            raise ValidationError(
                _(
                    "Paying in %(count)s installments is not available for this "
                    "payment.",
                    count=installments,
                )
            )
        return option
