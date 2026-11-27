# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    card_acquirer_id = fields.Many2one(
        comodel_name="account.card.acquirer",
        check_company=True,
        help="Payments registered in this journal are owed by this acquirer, "
        "which pays them later, net of its fees.",
    )
    card_modality = fields.Selection(
        selection=[("credit", "Credit"), ("debit", "Debit"), ("other", "Other")],
        default="credit",
        help="Kind of the payments of this journal that are not in installments.",
    )
