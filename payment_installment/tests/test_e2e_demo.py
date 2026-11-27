# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from urllib.parse import urlencode

from odoo import Command
from odoo.tests import tagged

from odoo.addons.payment.tests.http_common import PaymentHttpCommon


@tagged("post_install", "-at_install")
class TestEndToEndDemo(PaymentHttpCommon):
    """Pay a payment link in twelve installments with the demo provider.

    The demo provider of Odoo simulates a whole card payment, from the inline
    form to the confirmation page, so the test covers what a payer does. It is
    skipped when `payment_demo` is not installed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        module = cls.env["ir.module.module"]._get("payment_demo")
        cls.demo_installed = module.state == "installed"
        if not cls.demo_installed:
            return
        cls.provider = cls._prepare_provider(code="demo")
        cls.payment_method = cls.provider.payment_method_ids[:1]
        cls.amount = 1200.0
        cls.plan = cls.env["payment.installment.plan"].create(
            {
                "name": "Up to 12x",
                "provider_ids": [Command.set(cls.provider.ids)],
                "payment_method_ids": [Command.set(cls.payment_method.ids)],
                "currency_id": cls.currency.id,
                "line_ids": [
                    Command.create({"installments": 3}),
                    Command.create(
                        {
                            "installments": 6,
                            "interest_rate": 5.0,
                            "interest_bearer": "company",
                        }
                    ),
                    Command.create({"installments": 12, "interest_rate": 10.0}),
                ],
            }
        )

    def test_pay_in_twelve_installments(self):
        if not self.demo_installed:
            self.skipTest("payment_demo is not installed")
        self.enable_post_process_patcher = False
        pay_values = self._prepare_pay_values()
        self.start_tour(
            f"/payment/pay?{urlencode(pay_values)}", "payment_installment_demo"
        )
        tx = self.env["payment.transaction"].search(
            [("provider_id", "=", self.provider.id)], order="id desc", limit=1
        )
        self.assertEqual(tx.state, "done")
        self.assertEqual(tx.installments, 12)
        self.assertEqual(tx.amount, 1200.0)
        self.assertEqual(tx.installment_amount, 110.0)
        self.assertEqual(tx.installment_interest_amount, 120.0)
        self.assertEqual(tx.installment_interest_bearer, "customer")
        self.assertEqual(tx.amount_charged, 1320.0)
