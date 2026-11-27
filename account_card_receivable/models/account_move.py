# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models

from .account_card_acquirer import MODALITIES


class AccountMove(models.Model):
    _inherit = "account.move"

    card_payment_id = fields.Many2one(
        comodel_name="account.payment",
        string="Card Payment",
        readonly=True,
        copy=False,
        index="btree_not_null",
        help="Payment whose amount this entry moved to the acquirer.",
    )

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted.origin_payment_id._card_open_receivables()
        return posted


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    card_acquirer_id = fields.Many2one(
        comodel_name="account.card.acquirer", readonly=True, index="btree_not_null"
    )
    card_payment_id = fields.Many2one(
        comodel_name="account.payment", readonly=True, index="btree_not_null"
    )
    card_modality = fields.Selection(selection=MODALITIES, readonly=True)
    card_installment = fields.Integer(readonly=True)
    card_installment_count = fields.Integer(readonly=True)
    card_acquirer_reference = fields.Char(readonly=True, index="btree_not_null")
    card_authorization_code = fields.Char(readonly=True)
    card_brand_id = fields.Many2one(comodel_name="payment.method", readonly=True)
    card_sale_date = fields.Date(readonly=True)
