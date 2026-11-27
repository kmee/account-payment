# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Card Receivable",
    "summary": "Receivables from card acquirers and their settlement statements",
    "version": "18.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "KMEE, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/account-payment",
    "license": "AGPL-3",
    "maintainers": ["mileo"],
    "depends": ["account_payment_installment"],
    "data": [
        "security/ir.model.access.csv",
        "security/account_card_receivable_security.xml",
        "data/ir_sequence_data.xml",
        "views/account_card_acquirer_views.xml",
        "views/account_card_statement_views.xml",
        "views/account_journal_views.xml",
        "views/account_move_line_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
