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
        comodel_name="res.company",
        help="Leave empty to share the plan between companies.",
    )
    provider_ids = fields.Many2many(
        comodel_name="payment.provider",
        relation="payment_installment_plan_provider_rel",
        column1="plan_id",
        column2="provider_id",
        string="Providers",
        check_company=True,
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
        help="The plan is only offered for these payment methods.",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
        help="Currency of the minimum installment amount.",
    )
    min_installment_amount = fields.Monetary(
        help="An option is not offered when its installment would be lower than "
        "this amount.",
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

    def _get_options(self, amount, currency, allow_surcharge=False):
        """Return the installment options of the plan for an amount.

        The single installment is always the first option, whether the plan has
        lines or not.

        :param float amount: The amount to pay.
        :param res.currency currency: The currency of the amount.
        :param bool allow_surcharge: Whether the document being paid can take a
            surcharge. Options whose interest is charged by the company are
            only offered when it can.
        :return: One dict per option, sorted by number of installments.
        :rtype: list[dict]
        """
        self.ensure_one()
        options = [
            self._prepare_option(
                amount=amount, currency=currency, installments=1, interest_rate=0.0
            )
        ]
        min_amount = self._get_min_installment_amount(currency)
        for line in self.line_ids.sorted("installments"):
            if line._is_surcharge() and not allow_surcharge:
                continue
            option = self._prepare_option(
                amount=amount,
                currency=currency,
                installments=line.installments,
                interest_rate=line.interest_rate,
                interest_bearer=line.interest_bearer,
                interest_charged_by=line.interest_charged_by,
                line=line,
            )
            if currency.compare_amounts(option["installment_amount"], min_amount) < 0:
                continue
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
        interest_rate,
        interest_bearer="customer",
        interest_charged_by="provider",
        line=None,
    ):
        """Compute the amounts of one option.

        The interest rate is the total interest over the amount, not a monthly
        rate: 6.0 means 6% of the amount, whatever the number of installments.

        Who bears it changes what the payer pays:

        - the customer: the payer pays the amount plus the interest;
        - the company: the payer pays the amount, interest-free, and the
          interest is a cost of the sale for the company.
        """
        interest_amount = currency.round(amount * interest_rate / 100)
        payer_interest = interest_amount if interest_bearer == "customer" else 0.0
        total_amount = currency.round(amount + payer_interest)
        option = {
            "installments": installments,
            "installment_amount": currency.round(total_amount / installments),
            "total_amount": total_amount,
            "interest_amount": interest_amount,
            "interest_bearer": interest_bearer if interest_amount else False,
            "interest_charged_by": interest_charged_by if payer_interest else False,
            "interest_rate": interest_rate,
            "line_id": line.id if line else False,
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

    plan_id = fields.Many2one(
        comodel_name="payment.installment.plan",
        required=True,
        ondelete="cascade",
        index=True,
    )
    installments = fields.Integer(required=True, default=2)
    interest_rate = fields.Float(
        string="Interest (%)",
        digits=(16, 4),
        help="Total interest over the amount for this number of installments, "
        "charged by the provider. Leave at zero when there is none.",
    )
    interest_bearer = fields.Selection(
        selection=[("customer", "Customer"), ("company", "Company")],
        string="Interest Paid By",
        required=True,
        default="customer",
        help="Customer: the payer pays the amount plus the interest.\n"
        "Company: the payer pays the amount, interest-free, and the company "
        "bears the interest as a cost of the sale.",
    )

    _sql_constraints = [
        (
            "installments_unique",
            "unique(plan_id, installments)",
            "A plan can have only one option per number of installments.",
        ),
    ]

    interest_charged_by = fields.Selection(
        selection=[("provider", "Provider"), ("merchant", "Company")],
        required=True,
        default="provider",
        help="Who charges the interest paid by the customer.\n"
        "Provider: the provider (or the card issuer) adds it to what it charges "
        "the payer; the document being paid is not changed.\n"
        "Company: the company adds it to the document being paid as a surcharge "
        "and keeps it. It needs a module that adds the surcharge to the document, "
        "such as Sale Payment Installments.",
    )

    def _is_surcharge(self):
        """Whether the option adds a surcharge to the document being paid."""
        self.ensure_one()
        return bool(
            self.interest_rate
            and self.interest_bearer == "customer"
            and self.interest_charged_by == "merchant"
        )

    @api.constrains("installments", "interest_rate")
    def _check_installments(self):
        for line in self:
            if line.installments < 2:
                raise ValidationError(
                    _(
                        "The single installment is always offered: options start "
                        "at two installments."
                    )
                )
            if line.interest_rate < 0:
                raise ValidationError(_("The interest cannot be negative."))

    @api.depends("installments", "interest_rate", "interest_bearer")
    def _compute_display_name(self):
        for line in self:
            if line.interest_rate and line.interest_bearer == "customer":
                line.display_name = _(
                    "%(count)sx (+%(rate)s%%)",
                    count=line.installments,
                    rate=line.interest_rate,
                )
            else:
                line.display_name = _("%(count)sx", count=line.installments)
