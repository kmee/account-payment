# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    installment_plan_ids = fields.Many2many(
        comodel_name="payment.installment.plan",
        relation="payment_installment_plan_journal_rel",
        column1="journal_id",
        column2="plan_id",
        string="Installment Plans",
    )

    def _get_installment_plan(self):
        """Return the installment plan of the payments of the journal, if any.

        The journal is what an online provider, a payment registered by hand
        and a point of sale payment method have in common.
        """
        self.ensure_one()
        return self.installment_plan_ids.filtered(
            lambda plan: plan.active
            and plan.company_id in (self.company_id, self.env["res.company"])
        )[:1]
