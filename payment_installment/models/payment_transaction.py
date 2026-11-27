# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..const import NOTIFICATION_MAPPING


class PaymentTransaction(models.Model):
    _name = "payment.transaction"
    _inherit = ["payment.transaction", "payment.installment.mixin"]

    _sql_constraints = [
        (
            "installments_positive",
            "CHECK(installments >= 1)",
            "A transaction has at least one installment.",
        ),
    ]

    # === CRUD === #

    @api.model_create_multi
    def create(self, values_list):
        """Complete the installment amounts left out by the caller.

        Nothing is checked against the plans here: a transaction can also be
        recorded for a payment whose installments were decided elsewhere (a
        sales channel, a point of sale). The check is done where the payer
        chooses, see `_get_checked_installment_values`.
        """
        for values in values_list:
            installments = values.get("installments") or 1
            amount = values.get("amount") or 0.0
            values["installments"] = installments
            interest = values.get("installment_interest_amount") or 0.0
            if interest:
                values.setdefault("installment_interest_bearer", "customer")
            if (
                values.get("installment_interest_bearer") == "company"
                or values.get("installment_interest_charged_by") == "merchant"
            ):
                # Not charged on top of the amount: either the company bears it
                # or it is already part of the amount, as a surcharge.
                interest = 0.0
            values.setdefault("amount_charged", amount + interest)
            values.setdefault(
                "installment_amount", values["amount_charged"] / installments
            )
        return super().create(values_list)

    # === BUSINESS METHODS === #

    @api.model
    def _get_checked_installment_values(
        self,
        provider,
        payment_method,
        amount,
        currency,
        installments,
        allow_surcharge=False,
    ):
        """Return the create values of a number of installments chosen by a payer.

        :raise ValidationError: If the provider does not offer that number of
            installments for the payment method and the amount.
        """
        options = provider._get_installment_options(
            amount, currency, payment_method, allow_surcharge=allow_surcharge
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
        return {
            "installments": installments,
            "installment_plan_line_id": option["line_id"],
            "installment_amount": option["installment_amount"],
            "installment_interest_amount": option["interest_amount"],
            "installment_interest_bearer": option["interest_bearer"],
            "installment_interest_charged_by": option["interest_charged_by"],
            "amount_charged": option["total_amount"],
        }

    def _get_processing_values(self):
        """Hand the number of installments over to the provider flows."""
        processing_values = super()._get_processing_values()
        processing_values["installments"] = self.installments
        processing_values["installment_interest_bearer"] = (
            self.installment_interest_bearer
        )
        return processing_values

    # === NOTIFICATION DATA === #

    def _process_notification_data(self, notification_data):
        """Record what the provider reports about the installments."""
        res = super()._process_notification_data(notification_data)
        values = self._extract_installment_values(notification_data)
        if values:
            self.write(values)
        return res

    def _get_installment_notification_mapping(self):
        """Return where the provider reports the installment data.

        :return: Dotted paths in the notification data, by key. See `const.py`.
        :rtype: dict
        """
        self.ensure_one()
        return NOTIFICATION_MAPPING.get(self.provider_code, {})

    def _extract_installment_values(self, notification_data):
        """Turn the installment data of a notification into write values."""
        self.ensure_one()
        mapping = self._get_installment_notification_mapping()
        if not mapping or not isinstance(notification_data, dict):
            return {}

        def read(key):
            value = notification_data
            for part in mapping.get(key, "").split("."):
                value = value.get(part) if isinstance(value, dict) else None
            return value

        values = {}
        installments = read("installments")
        if installments:
            values["installments"] = int(installments)
        for key in ("installment_amount", "amount_charged"):
            amount = read(key)
            if amount:
                values[key] = float(amount)
        for key in ("acquirer_reference", "authorization_code"):
            reference = read(key)
            if reference:
                values[key] = str(reference)
        brand_code = read("card_brand_code")
        if brand_code:
            brand = self.env["payment.method"].search(
                [("code", "=", brand_code), ("is_primary", "=", False)], limit=1
            )
            if brand:
                values["card_brand_id"] = brand.id
        if values.get("amount_charged"):
            # The provider charged the payer more than the amount: the difference
            # is interest paid by the customer, whatever the plan said.
            interest = values["amount_charged"] - self.amount
            if self.currency_id.compare_amounts(interest, 0.0) > 0:
                values["installment_interest_amount"] = interest
                values["installment_interest_bearer"] = "customer"
                values["installment_interest_charged_by"] = "provider"
        return values
