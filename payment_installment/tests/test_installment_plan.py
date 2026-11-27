# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.common import PaymentCommon


class InstallmentCommon(PaymentCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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
                            "interest_rate": 5.0,
                            "interest_bearer": "company",
                        }
                    ),
                    Command.create({"installments": 12, "interest_rate": 10.0}),
                ],
            }
        )


@tagged("post_install", "-at_install")
class TestInstallmentPlan(InstallmentCommon):
    def _options(self, amount=1200.0):
        return self.provider._get_installment_options(
            amount, self.currency, self.payment_method
        )

    def test_options_start_with_the_single_installment(self):
        options = self._options()
        self.assertEqual([o["installments"] for o in options], [1, 2, 3, 6, 12])
        self.assertEqual(options[0]["installment_amount"], 1200.0)
        self.assertEqual(options[0]["interest_amount"], 0.0)

    def test_interest_free_option(self):
        option = self._options()[2]
        self.assertEqual(option["installment_amount"], 400.0)
        self.assertEqual(option["total_amount"], 1200.0)
        self.assertEqual(option["interest_amount"], 0.0)
        self.assertIn("interest-free", option["label"])

    def test_interest_paid_by_the_customer_is_added_to_the_total(self):
        option = self._options()[4]
        self.assertEqual(option["interest_bearer"], "customer")
        self.assertEqual(option["total_amount"], 1320.0)
        self.assertEqual(option["installment_amount"], 110.0)
        self.assertEqual(option["interest_amount"], 120.0)
        self.assertIn("total", option["label"])

    def test_interest_paid_by_the_company_is_interest_free_for_the_payer(self):
        option = self._options()[3]
        self.assertEqual(option["interest_bearer"], "company")
        self.assertEqual(option["total_amount"], 1200.0)
        self.assertEqual(option["installment_amount"], 200.0)
        self.assertEqual(option["interest_amount"], 60.0)
        self.assertIn("interest-free", option["label"])

    def test_surcharge_option_needs_a_document_that_can_take_it(self):
        self.plan.line_ids = [
            Command.create(
                {
                    "installments": 10,
                    "interest_rate": 8.0,
                    "interest_charged_by": "merchant",
                }
            )
        ]
        self.assertNotIn(10, [o["installments"] for o in self._options()])
        options = self.provider._get_installment_options(
            1200.0, self.currency, self.payment_method, allow_surcharge=True
        )
        option = next(o for o in options if o["installments"] == 10)
        self.assertEqual(option["interest_charged_by"], "merchant")
        self.assertEqual(option["total_amount"], 1296.0)
        self.assertEqual(option["installment_amount"], 129.6)

    def test_option_without_interest_has_no_bearer(self):
        self.assertFalse(self._options()[2]["interest_bearer"])

    def test_installment_is_rounded_with_the_currency(self):
        option = self._options(amount=100.0)[2]
        self.assertEqual(option["installment_amount"], 33.33)

    def test_minimum_installment_amount_hides_options(self):
        self.plan.min_installment_amount = 150.0
        self.assertEqual([o["installments"] for o in self._options()], [1, 2, 3, 6])
        # 12 x 110.00 is below the minimum, 6 x 200.00 is not.
        self.plan.min_installment_amount = 500.0
        self.assertEqual([o["installments"] for o in self._options()], [1, 2])

    def test_nothing_to_choose_when_only_one_installment_is_left(self):
        self.plan.min_installment_amount = 5000.0
        self.assertEqual(self._options(), [])

    def test_no_options_without_a_plan(self):
        self.plan.provider_ids = [Command.clear()]
        self.assertEqual(self._options(), [])

    def test_no_options_for_another_payment_method(self):
        other_method = self.env["payment.method"].create(
            {"name": "Other", "code": "other_installment_test", "active": True}
        )
        self.assertEqual(
            self.provider._get_installment_options(1200.0, self.currency, other_method),
            [],
        )

    def test_plan_of_the_primary_method_applies_to_its_brands(self):
        brand = self.env["payment.method"].create(
            {
                "name": "Brand",
                "code": "brand_installment_test",
                "primary_payment_method_id": self.payment_method.id,
                "active": True,
            }
        )
        self.assertEqual(self.provider._get_installment_plan(brand), self.plan)

    def test_archived_plan_is_not_offered(self):
        self.plan.active = False
        self.assertEqual(self._options(), [])

    def test_plan_of_another_company_is_not_offered(self):
        other_company = self.env["res.company"].create({"name": "Other company"})
        self.plan.company_id = other_company
        self.assertEqual(self._options(), [])

    def test_max_installments(self):
        self.assertEqual(self.plan.max_installments, 12)
        self.plan.line_ids.unlink()
        self.assertEqual(self.plan.max_installments, 1)

    def test_line_starts_at_two_installments(self):
        with self.assertRaises(ValidationError):
            self.plan.line_ids = [Command.create({"installments": 1})]

    def test_interest_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            self.plan.line_ids = [
                Command.create({"installments": 9, "interest_rate": -1.0})
            ]

    @mute_logger("odoo.sql_db")
    def test_one_line_per_number_of_installments(self):
        with self.assertRaises(Exception):  # noqa: B017
            with self.env.cr.savepoint():
                self.plan.line_ids = [Command.create({"installments": 3})]
                self.env.flush_all()
