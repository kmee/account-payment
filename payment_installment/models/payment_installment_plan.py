# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import format_amount


class PaymentInstallmentPlan(models.Model):
    _name = "payment.installment.plan"
    _description = "Payment Installment Plan"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company", help="Leave empty to share the plan."
    )
    provider_ids = fields.Many2many(
        comodel_name="payment.provider",
        relation="payment_installment_plan_provider_rel",
        column1="plan_id",
        column2="provider_id",
        string="Providers",
    )
    payment_method_ids = fields.Many2many(
        comodel_name="payment.method",
        relation="payment_installment_plan_method_rel",
        column1="plan_id",
        column2="payment_method_id",
        string="Payment Methods",
        domain="[('is_primary', '=', True)]",
        default=lambda self: self.env.ref(
            "payment.payment_method_card", raise_if_not_found=False
        ),
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    min_installment_amount = fields.Monetary(
        help="Options whose installment would be lower are not offered.",
    )
    line_ids = fields.One2many(
        comodel_name="payment.installment.plan.line",
        inverse_name="plan_id",
        string="Options",
        copy=True,
    )
    max_installments = fields.Integer(compute="_compute_max_installments")

    @api.depends("line_ids.installments")
    def _compute_max_installments(self):
        for plan in self:
            plan.max_installments = max(plan.line_ids.mapped("installments") or [1])

    def _get_options(self, amount, currency):
        """Return the installment options of the plan for an amount, as dicts.

        The single installment is always the first option.
        """
        self.ensure_one()
        options = [self._prepare_option(amount, currency, 1)]
        min_amount = self._get_min_installment_amount(currency)
        for line in self.line_ids.sorted("installments"):
            option = self._prepare_option(
                amount,
                currency,
                line.installments,
                interest_percent=line.interest_percent,
                interest_bearer=line.interest_bearer,
            )
            if currency.compare_amounts(option["installment_amount"], min_amount) >= 0:
                options.append(option)
        return options

    def _get_min_installment_amount(self, currency):
        self.ensure_one()
        if not self.min_installment_amount or self.currency_id == currency:
            return self.min_installment_amount
        return self.currency_id._convert(
            self.min_installment_amount,
            currency,
            self.company_id or self.env.company,
            fields.Date.context_today(self),
        )

    def _prepare_option(
        self,
        amount,
        currency,
        installments,
        interest_percent=0.0,
        interest_bearer="customer",
    ):
        interest_amount = currency.round(amount * interest_percent / 100)
        payer_interest = interest_amount if interest_bearer == "customer" else 0.0
        total_amount = currency.round(amount + payer_interest)
        option = {
            "installments": installments,
            "installment_amount": currency.round(total_amount / installments),
            "total_amount": total_amount,
            "interest_amount": interest_amount,
            "interest_bearer": interest_bearer if interest_amount else False,
        }
        option["label"] = self._get_option_label(option, currency)
        return option

    def _get_option_label(self, option, currency):
        installment = format_amount(self.env, option["installment_amount"], currency)
        if option["installments"] == 1:
            return _("1x of %(amount)s", amount=installment)
        if option["interest_bearer"] != "customer":
            return _(
                "%(count)sx of %(amount)s, interest-free",
                count=option["installments"],
                amount=installment,
            )
        return _(
            "%(count)sx of %(amount)s (total %(total)s)",
            count=option["installments"],
            amount=installment,
            total=format_amount(self.env, option["total_amount"], currency),
        )


class PaymentInstallmentPlanLine(models.Model):
    _name = "payment.installment.plan.line"
    _description = "Payment Installment Plan Option"
    _order = "installments"

    _sql_constraints = [
        (
            "installments_unique",
            "unique(plan_id, installments)",
            "A plan can have only one option per number of installments.",
        ),
    ]

    plan_id = fields.Many2one(
        comodel_name="payment.installment.plan",
        required=True,
        ondelete="cascade",
        index=True,
    )
    installments = fields.Integer(required=True, default=2)
    interest_percent = fields.Float(
        string="Interest (%)",
        digits=(16, 4),
        help="Total interest over the amount, whatever the number of installments.",
    )
    interest_bearer = fields.Selection(
        selection=[("customer", "Customer"), ("company", "Company")],
        string="Interest Paid By",
        required=True,
        default="customer",
        help="Customer: the payer is charged the amount plus the interest.\n"
        "Company: the payer is charged the amount and the company bears the "
        "interest.",
    )

    @api.constrains("installments", "interest_percent")
    def _check_installments(self):
        for line in self:
            if line.installments < 2:
                raise ValidationError(
                    _("The single installment is always offered: start at two.")
                )
            if line.interest_percent < 0:
                raise ValidationError(_("The interest cannot be negative."))
