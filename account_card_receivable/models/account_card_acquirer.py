# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

MODALITIES = [
    ("debit", "Debit"),
    ("credit", "Credit, single payment"),
    ("installment_merchant", "Credit in installments, financed by the company"),
    ("installment_issuer", "Credit in installments, financed by the issuer"),
    ("other", "Other"),
]


class AccountCardAcquirer(models.Model):
    _name = "account.card.acquirer"
    _description = "Card Acquirer"
    _order = "name"
    _check_company_auto = True

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        required=True,
        help="The acquirer, as the partner of the receivables.",
    )
    establishment_code = fields.Char(
        help="Number of the company at the acquirer. Statement lines of another "
        "establishment are left out when a file is imported.",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        required=True,
        check_company=True,
        domain="[('type', '=', 'general')]",
        help="Journal of the entries that open the receivables and settle them.",
    )
    payment_journal_ids = fields.One2many(
        comodel_name="account.journal",
        inverse_name="card_acquirer_id",
        string="Payment Journals",
        help="Payments registered in these journals are owed by the acquirer.",
    )
    receivable_account_id = fields.Many2one(
        comodel_name="account.account",
        required=True,
        check_company=True,
        domain="[('reconcile', '=', True), ('deprecated', '=', False)]",
        help="What the acquirer owes, one line per settlement expected.",
    )
    clearing_account_id = fields.Many2one(
        comodel_name="account.account",
        required=True,
        check_company=True,
        domain="[('reconcile', '=', True), ('deprecated', '=', False)]",
        help="Net amounts the acquirer says it paid, until they are matched with "
        "the bank statement.",
    )
    fee_account_id = fields.Many2one(
        comodel_name="account.account",
        required=True,
        check_company=True,
        domain="[('deprecated', '=', False)]",
    )
    anticipation_account_id = fields.Many2one(
        comodel_name="account.account",
        check_company=True,
        domain="[('deprecated', '=', False)]",
        help="Cost of receiving before the due date. The fee account is used "
        "when empty.",
    )
    adjustment_account_id = fields.Many2one(
        comodel_name="account.account",
        check_company=True,
        domain="[('deprecated', '=', False)]",
        help="Terminal rental and other amounts the acquirer charges or credits.",
    )
    chargeback_account_id = fields.Many2one(
        comodel_name="account.account",
        check_company=True,
        domain="[('deprecated', '=', False)]",
        help="Sales the acquirer took back. The adjustment account is used when "
        "empty.",
    )
    rounding_installment = fields.Selection(
        selection=[("first", "First installment"), ("last", "Last installment")],
        required=True,
        default="first",
        help="Installment that takes the cents left by the division.",
    )
    amount_tolerance = fields.Monetary(
        default=0.05,
        help="Difference accepted between an installment and what the acquirer "
        "paid for it. The acquirer may put the cents of the division on another "
        "installment: the sale as a whole still has to match.",
    )
    rule_ids = fields.One2many(
        comodel_name="account.card.acquirer.rule",
        inverse_name="acquirer_id",
        string="Fees and Settlement",
        copy=True,
    )

    def _get_rule(self, modality, installments=1, brand=None):
        """Return the contract rule of a payment: the most specific one."""
        self.ensure_one()
        rules = self.rule_ids.filtered(
            lambda rule: rule.modality == modality
            and rule.installments_from <= (installments or 1) <= rule.installments_to
            and (not rule.brand_ids or (brand and brand in rule.brand_ids))
        )
        return rules.sorted(lambda rule: (not rule.brand_ids, rule.sequence, rule.id))[
            :1
        ]

    def _get_settlements(self, modality, installments, amount, date, brand=None):
        """Split what the acquirer owes for a payment into settlements.

        :return: One `(number, count, amount, due date)` per settlement.
        :rtype: list[tuple]
        """
        self.ensure_one()
        installments = max(installments or 1, 1)
        rule = self._get_rule(modality, installments, brand)
        single = rule.single_settlement if rule else modality != "installment_merchant"
        count = 1 if single else installments
        first_due_days = rule.first_due_days if rule else 30
        interval_days = rule.interval_days if rule else 30
        currency = self.currency_id
        base = currency.round(amount / count)
        amounts = [base] * count
        rest = currency.round(amount - base * count)
        amounts[0 if self.rounding_installment == "first" else -1] += rest
        return [
            (
                index + 1,
                count,
                currency.round(value),
                date + timedelta(days=first_due_days + index * interval_days),
            )
            for index, value in enumerate(amounts)
        ]

    def _get_expected_fee(self, modality, installments, amount, brand=None):
        self.ensure_one()
        rule = self._get_rule(modality, installments, brand)
        return self.currency_id.round(amount * rule.fee_percent / 100) if rule else 0.0

    def _get_balances(self):
        """Return what is still open with the acquirer.

        :return: The balance of the receivable and of the clearing accounts.
        :rtype: dict
        """
        self.ensure_one()
        balances = {}
        for key, account in (
            ("receivable", self.receivable_account_id),
            ("clearing", self.clearing_account_id),
        ):
            lines = self.env["account.move.line"].search(
                [
                    ("company_id", "=", self.company_id.id),
                    ("account_id", "=", account.id),
                    ("partner_id", "=", self.partner_id.id),
                    ("parent_state", "=", "posted"),
                ]
            )
            balances[key] = self.currency_id.round(sum(lines.mapped("balance")))
        return balances


class AccountCardAcquirerRule(models.Model):
    _name = "account.card.acquirer.rule"
    _description = "Card Acquirer Fee and Settlement Rule"
    _order = "sequence, id"

    acquirer_id = fields.Many2one(
        comodel_name="account.card.acquirer",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    modality = fields.Selection(selection=MODALITIES, required=True, default="credit")
    installments_from = fields.Integer(required=True, default=1)
    installments_to = fields.Integer(required=True, default=1)
    brand_ids = fields.Many2many(
        comodel_name="payment.method",
        string="Card Brands",
        domain="[('is_primary', '=', False)]",
        help="Leave empty for a rule that applies to every brand.",
    )
    fee_percent = fields.Float(string="Fee (%)", digits=(16, 4))
    first_due_days = fields.Integer(
        default=30, help="Days between the sale and the first settlement."
    )
    interval_days = fields.Integer(
        default=30, help="Days between two settlements of the same sale."
    )
    single_settlement = fields.Boolean(
        compute="_compute_single_settlement",
        store=True,
        readonly=False,
        help="The acquirer pays the whole sale at once, whatever the number of "
        "installments the card holder pays: the usual case when the issuer "
        "finances the installments.",
    )

    @api.depends("modality")
    def _compute_single_settlement(self):
        for rule in self:
            rule.single_settlement = rule.modality != "installment_merchant"

    @api.constrains("installments_from", "installments_to")
    def _check_installments(self):
        for rule in self:
            if rule.installments_from < 1 or rule.installments_to < rule.installments_from:
                raise ValidationError(_("The range of installments is not valid."))
