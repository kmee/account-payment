# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.payment.tests.common import PaymentCommon


class InstallmentCommon(PaymentCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        provider_class = type(cls.env["payment.provider"])
        compute_support = provider_class._compute_feature_support_fields

        def _compute_feature_support_fields(self):
            compute_support(self)
            self.filtered(lambda p: p.code == "none").update(
                {"support_installments": True}
            )

        cls.classPatch(
            provider_class,
            "_compute_feature_support_fields",
            _compute_feature_support_fields,
        )
        cls.provider.invalidate_recordset(["support_installments"])
        cls.plan = cls.env["payment.installment.plan"].create(
            {
                "name": "Up to 12x",
                "provider_ids": [Command.set(cls.provider.ids)],
                "payment_method_ids": [Command.set(cls.payment_method.ids)],
                "currency_id": cls.currency.id,
                "line_ids": [
                    Command.create({"installments": 2}),
                    Command.create({"installments": 3}),
                    Command.create(
                        {
                            "installments": 6,
                            "interest_percent": 5.0,
                            "interest_bearer": "company",
                        }
                    ),
                    Command.create({"installments": 12, "interest_percent": 10.0}),
                ],
            }
        )


@tagged("post_install", "-at_install")
class TestInstallmentPlan(InstallmentCommon):
    def _options(self, amount=1200.0, payment_method=None):
        return self.provider._get_installment_options(
            payment_method or self.payment_method, amount, self.currency
        )

    def test_options(self):
        options = {o["installments"]: o for o in self._options()}
        self.assertEqual(list(options), [1, 2, 3, 6, 12])
        self.assertEqual(options[1]["installment_amount"], 1200.0)
        self.assertEqual(options[3]["installment_amount"], 400.0)
        self.assertFalse(options[3]["interest_bearer"])
        self.assertIn("interest-free", options[3]["label"])

    def test_interest_paid_by_the_customer(self):
        option = self._options()[-1]
        self.assertEqual(option["total_amount"], 1320.0)
        self.assertEqual(option["installment_amount"], 110.0)
        self.assertEqual(option["interest_amount"], 120.0)
        self.assertEqual(option["interest_bearer"], "customer")

    def test_interest_paid_by_the_company(self):
        option = self._options()[3]
        self.assertEqual(option["total_amount"], 1200.0)
        self.assertEqual(option["installment_amount"], 200.0)
        self.assertEqual(option["interest_amount"], 60.0)
        self.assertEqual(option["interest_bearer"], "company")
        self.assertIn("interest-free", option["label"])

    def test_minimum_installment_amount(self):
        self.plan.min_installment_amount = 150.0
        self.assertEqual([o["installments"] for o in self._options()], [1, 2, 3, 6])
        self.plan.min_installment_amount = 5000.0
        self.assertEqual(self._options(), [])

    def test_plan_of_the_primary_method_applies_to_its_brands(self):
        brand = self.env["payment.method"].create(
            {
                "name": "Brand",
                "code": "brand_installment_test",
                "primary_payment_method_id": self.payment_method.id,
                "active": True,
            }
        )
        self.assertEqual(len(self._options(payment_method=brand)), 5)

    def test_no_options(self):
        other_method = self.env["payment.method"].create(
            {"name": "Other", "code": "other_installment_test", "active": True}
        )
        self.assertEqual(self._options(payment_method=other_method), [])
        with self.subTest("provider without installment support"):
            self.provider.support_installments = False
            self.assertEqual(self._options(), [])
            self.provider.invalidate_recordset(["support_installments"])
        with self.subTest("archived plan"):
            self.plan.active = False
            self.assertEqual(self._options(), [])
            self.plan.active = True
        with self.subTest("plan of another company"):
            self.plan.company_id = self.env["res.company"].create({"name": "Other"})
            self.assertEqual(self._options(), [])

    def test_option_lines(self):
        with self.assertRaises(ValidationError):
            self.plan.line_ids = [Command.create({"installments": 1})]
        with self.assertRaises(ValidationError):
            self.plan.line_ids = [
                Command.create({"installments": 9, "interest_percent": -1.0})
            ]
