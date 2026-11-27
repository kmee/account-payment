# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Account Payment Installments",
    "summary": "Installments and card data on payments registered in accounting",
    "version": "18.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "KMEE, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/account-payment",
    "license": "AGPL-3",
    "maintainers": ["mileo"],
    "depends": ["account_payment", "payment_installment"],
    "data": [
        "security/ir.model.access.csv",
        "views/account_journal_views.xml",
        "views/account_payment_views.xml",
        "views/payment_installment_plan_views.xml",
        "wizards/account_payment_register_views.xml",
    ],
    "installable": True,
}
