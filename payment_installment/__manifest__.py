# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Payment Installments",
    "summary": "Let the payer split a card payment into installments",
    "version": "18.0.1.0.0",
    "category": "Accounting/Payment Providers",
    "author": "KMEE, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/account-payment",
    "license": "AGPL-3",
    "maintainers": ["mileo"],
    "depends": ["payment"],
    "data": [
        "security/ir.model.access.csv",
        "security/payment_installment_security.xml",
        "views/payment_installment_plan_views.xml",
        "views/payment_provider_views.xml",
        "views/payment_transaction_views.xml",
        "views/payment_form_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_installment/static/src/js/payment_form.js",
        ],
        "web.assets_tests": [
            "payment_installment/static/tests/tours/**/*",
        ],
    },
    "installable": True,
}
