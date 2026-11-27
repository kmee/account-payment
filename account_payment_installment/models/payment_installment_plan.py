# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PaymentInstallmentPlan(models.Model):
    _inherit = "payment.installment.plan"

    journal_ids = fields.Many2many(
        comodel_name="account.journal",
        relation="payment_installment_plan_journal_rel",
        column1="plan_id",
        column2="journal_id",
        string="Journals",
        domain="[('type', 'in', ('bank', 'cash', 'credit'))]",
        check_company=True,
        help="Journals whose payments can be registered in installments with "
        "this plan, when no payment provider is involved: a card terminal that "
        "is not connected to Odoo, for instance.",
    )
