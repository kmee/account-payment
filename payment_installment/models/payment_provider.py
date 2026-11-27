# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    installment_plan_ids = fields.Many2many(
        comodel_name="payment.installment.plan",
        relation="payment_installment_plan_provider_rel",
        column1="provider_id",
        column2="plan_id",
        string="Installment Plans",
    )

    def _get_installment_plan(self, payment_method):
        """Return the installment plan offered for a payment method, if any.

        A plan set on a primary payment method (e.g. Card) also applies to its
        brands.

        :param payment.method payment_method: The payment method to pay with.
        :return: The first matching plan.
        :rtype: payment.installment.plan
        """
        self.ensure_one()
        if not payment_method:
            return self.env["payment.installment.plan"]
        methods = payment_method | payment_method.primary_payment_method_id
        return self.installment_plan_ids.filtered(
            lambda plan: plan.active
            and plan.payment_method_ids & methods
            and plan.company_id in (self.company_id, self.env["res.company"])
        )[:1]

    def _get_installment_options(
        self, amount, currency, payment_method, allow_surcharge=False
    ):
        """Return the options to show in the installment selector.

        Nothing is returned when the single installment is the only option, as
        there is nothing to choose.

        :return: The options, as returned by `payment.installment.plan._get_options`.
        :rtype: list[dict]
        """
        self.ensure_one()
        plan = self._get_installment_plan(payment_method)
        if not plan or not amount or not currency:
            return []
        options = plan._get_options(amount, currency, allow_surcharge=allow_surcharge)
        return options if len(options) > 1 else []

    def _get_payment_form_installment_options(
        self, amount, currency, payment_method, **kwargs
    ):
        """Return the options of the installment selector of the payment form.

        Modules that know the document being paid override this method to offer
        the options that need the document, such as a surcharge.

        :param dict kwargs: The payment context, with the same optional keys the
            payment engine hands over to its helpers (`sale_order_id`, ...).
        """
        self.ensure_one()
        return self._get_installment_options(amount, currency, payment_method)
