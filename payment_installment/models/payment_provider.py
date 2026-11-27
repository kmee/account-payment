# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    support_installments = fields.Boolean(
        string="Installments", compute="_compute_feature_support_fields"
    )
    installment_plan_ids = fields.Many2many(
        comodel_name="payment.installment.plan",
        relation="payment_installment_plan_provider_rel",
        column1="provider_id",
        column2="plan_id",
        string="Installment Plans",
    )

    def _compute_feature_support_fields(self):
        """Override of `payment`: a provider module that sends the number of
        installments to its gateway sets `support_installments`."""
        res = super()._compute_feature_support_fields()
        self.update({"support_installments": False})
        return res

    def _get_installment_plan(self, payment_method):
        """Return the plan offered for a payment method or for its primary one."""
        self.ensure_one()
        if not self.support_installments or not payment_method:
            return self.env["payment.installment.plan"]
        methods = payment_method | payment_method.primary_payment_method_id
        return self.installment_plan_ids.filtered(
            lambda plan: plan.active
            and plan.payment_method_ids & methods
            and plan.company_id in (self.company_id, self.env["res.company"])
        )[:1]

    def _get_installment_options(self, payment_method, amount, currency):
        """Return the options of the installment selector, or nothing when the
        single installment is the only one."""
        self.ensure_one()
        plan = self._get_installment_plan(payment_method)
        if not plan or not amount or not currency:
            return []
        options = plan._get_options(amount, currency)
        return options if len(options) > 1 else []
