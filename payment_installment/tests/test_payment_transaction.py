# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .test_installment_plan import InstallmentCommon

MAPPING_PATH = (
    "odoo.addons.payment_installment.models.payment_transaction"
    ".PaymentTransaction._get_installment_notification_mapping"
)


@tagged("post_install", "-at_install")
class TestPaymentTransaction(InstallmentCommon):
    def test_single_installment_by_default(self):
        tx = self._create_transaction("redirect")
        self.assertEqual(tx.installments, 1)
        self.assertEqual(tx.installment_amount, tx.amount)
        self.assertEqual(tx.amount_charged, tx.amount)
        self.assertFalse(tx.installment_interest_amount)

    def test_installments_decided_elsewhere_are_recorded_as_given(self):
        """A sales channel reports ten installments no plan offers."""
        tx = self._create_transaction("redirect", amount=1000.0, installments=10)
        self.assertEqual(tx.installments, 10)
        self.assertEqual(tx.installment_amount, 100.0)
        self.assertEqual(tx.amount_charged, 1000.0)

    def test_interest_charged_by_the_provider_is_kept_apart(self):
        tx = self._create_transaction(
            "redirect",
            amount=1000.0,
            installments=10,
            installment_interest_amount=50.0,
        )
        self.assertEqual(tx.amount, 1000.0)
        self.assertEqual(tx.installment_interest_bearer, "customer")
        self.assertEqual(tx.amount_charged, 1050.0)
        self.assertEqual(tx.installment_amount, 105.0)

    def test_interest_borne_by_the_company_is_not_charged_to_the_payer(self):
        tx = self._create_transaction(
            "redirect",
            amount=1000.0,
            installments=10,
            installment_interest_amount=50.0,
            installment_interest_bearer="company",
        )
        self.assertEqual(tx.amount_charged, 1000.0)
        self.assertEqual(tx.installment_amount, 100.0)
        self.assertEqual(tx.installment_interest_amount, 50.0)

    def test_surcharge_is_already_part_of_the_amount(self):
        """The document total includes the surcharge: nothing is charged on top."""
        tx = self._create_transaction(
            "redirect",
            amount=1320.0,
            installments=12,
            installment_interest_amount=120.0,
            installment_interest_bearer="customer",
            installment_interest_charged_by="merchant",
        )
        self.assertEqual(tx.amount_charged, 1320.0)
        self.assertEqual(tx.installment_amount, 110.0)

    def test_checked_values_of_an_offered_option(self):
        values = self.env["payment.transaction"]._get_checked_installment_values(
            self.provider, self.payment_method, 1200.0, self.currency, 12
        )
        self.assertEqual(values["installments"], 12)
        self.assertEqual(values["installment_amount"], 110.0)
        self.assertEqual(values["installment_interest_amount"], 120.0)
        self.assertEqual(values["installment_interest_bearer"], "customer")
        self.assertEqual(values["amount_charged"], 1320.0)
        self.assertEqual(
            values["installment_plan_line_id"],
            self.plan.line_ids.filtered(lambda line: line.installments == 12).id,
        )

    def test_checked_values_reject_an_option_not_offered(self):
        with self.assertRaises(ValidationError):
            self.env["payment.transaction"]._get_checked_installment_values(
                self.provider, self.payment_method, 1200.0, self.currency, 7
            )

    def test_processing_values_carry_the_installments(self):
        tx = self._create_transaction("redirect", installments=3)
        self.assertEqual(tx._get_processing_values()["installments"], 3)

    def test_notification_without_mapping_changes_nothing(self):
        tx = self._create_transaction("redirect")
        self.assertEqual(tx._extract_installment_values({"installments": 6}), {})

    def test_notification_values_follow_the_provider_mapping(self):
        brand = self.env["payment.method"].create(
            {
                "name": "Brand",
                "code": "brand_installment_test",
                "primary_payment_method_id": self.payment_method.id,
                "active": True,
            }
        )
        tx = self._create_transaction("redirect", amount=1000.0)
        mapping = {
            "installments": "installments",
            "installment_amount": "transaction_details.installment_amount",
            "amount_charged": "transaction_details.total_paid_amount",
            "acquirer_reference": "nsu",
            "authorization_code": "authorization_code",
            "card_brand_code": "payment_method_id",
        }
        notification_data = {
            "installments": 6,
            "transaction_details": {
                "installment_amount": 175.0,
                "total_paid_amount": 1050.0,
            },
            "nsu": 123456,
            "authorization_code": "A1B2C3",
            "payment_method_id": "brand_installment_test",
        }
        with patch(MAPPING_PATH, return_value=mapping):
            tx._process_notification_data(notification_data)
        self.assertEqual(tx.installments, 6)
        self.assertEqual(tx.installment_amount, 175.0)
        self.assertEqual(tx.amount_charged, 1050.0)
        self.assertEqual(tx.installment_interest_amount, 50.0)
        self.assertEqual(tx.installment_interest_bearer, "customer")
        self.assertEqual(tx.acquirer_reference, "123456")
        self.assertEqual(tx.authorization_code, "A1B2C3")
        self.assertEqual(tx.card_brand_id, brand)

    def test_notification_missing_paths_are_ignored(self):
        tx = self._create_transaction("redirect", amount=1000.0)
        mapping = {
            "installments": "payment.installments",
            "amount_charged": "payment.total",
        }
        with patch(MAPPING_PATH, return_value=mapping):
            tx._process_notification_data({"payment": "not a dict"})
        self.assertEqual(tx.installments, 1)
        self.assertEqual(tx.amount_charged, 1000.0)
