# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from urllib.parse import urlencode

from odoo.tests import JsonRpcException, tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon

from .test_installment_plan import InstallmentCommon


@tagged("post_install", "-at_install")
class TestPaymentFlows(InstallmentCommon, PaymentHttpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.amount = 1200.0

    def _route_values(self, flow="redirect", **extra):
        route_values = self._prepare_transaction_values(
            self.payment_method_id, None, flow
        )
        route_values.update(extra)
        return route_values

    def test_selector_is_rendered_in_the_payment_form(self):
        response = self._portal_pay(**self._prepare_pay_values())
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="o_payment_installments"', response.text)
        self.assertIn('value="12"', response.text)
        self.assertIn("interest-free", response.text)

    def test_no_selector_without_a_plan(self):
        self.plan.active = False
        response = self._portal_pay(**self._prepare_pay_values())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('name="o_payment_installments"', response.text)

    def test_transaction_route_stores_the_chosen_installments(self):
        processing_values = self._get_processing_values(
            **self._route_values(installments=12)
        )
        tx = self._get_tx(processing_values["reference"])
        self.assertEqual(processing_values["installments"], 12)
        self.assertEqual(tx.installments, 12)
        self.assertEqual(tx.amount, 1200.0)
        self.assertEqual(tx.installment_amount, 110.0)
        self.assertEqual(tx.installment_interest_amount, 120.0)
        self.assertEqual(tx.amount_charged, 1320.0)
        self.assertEqual(tx.installment_plan_line_id.installments, 12)

    def test_transaction_route_with_interest_borne_by_the_company(self):
        processing_values = self._get_processing_values(
            **self._route_values(installments=6)
        )
        tx = self._get_tx(processing_values["reference"])
        self.assertEqual(processing_values["installment_interest_bearer"], "company")
        self.assertEqual(tx.installments, 6)
        self.assertEqual(tx.installment_amount, 200.0)
        self.assertEqual(tx.installment_interest_amount, 60.0)
        self.assertEqual(tx.installment_interest_bearer, "company")
        self.assertEqual(tx.amount_charged, 1200.0)

    def test_transaction_route_without_installments(self):
        processing_values = self._get_processing_values(**self._route_values())
        tx = self._get_tx(processing_values["reference"])
        self.assertEqual(tx.installments, 1)
        self.assertEqual(tx.amount_charged, 1200.0)

    @mute_logger("odoo.http")
    def test_transaction_route_rejects_installments_not_offered(self):
        with self.assertRaises(JsonRpcException):
            self._get_processing_values(**self._route_values(installments=7))

    @mute_logger("odoo.http")
    def test_transaction_route_rejects_installments_below_the_minimum(self):
        self.plan.min_installment_amount = 500.0
        with self.assertRaises(JsonRpcException):
            self._get_processing_values(**self._route_values(installments=12))

    @mute_logger("odoo.http")
    def test_token_is_charged_in_a_single_installment(self):
        token = self._create_token()
        route_values = self._prepare_transaction_values(None, token.id, "token")
        route_values["installments"] = 3
        with self.assertRaises(JsonRpcException):
            self._get_processing_values(**route_values)

    def test_browser_sends_the_installments_picked_in_the_selector(self):
        """Pick 3x in the real payment form and pay."""
        pay_values = self._prepare_pay_values()
        url = f"/payment/pay?{urlencode(pay_values)}"
        code = f"""
            // The dummy provider redirects to nowhere: stop at the redirect.
            HTMLFormElement.prototype.submit = () => console.log("test successful");
            const option = document
                .querySelector('input[name="o_payment_radio"][data-provider-id="{self.provider.id}"]')
                .closest('[name="o_payment_option"]');
            const radio = option.querySelector('input[name="o_payment_radio"]');
            if (!radio.checked) {{
                radio.click();
            }}
            option.querySelector('select[name="o_payment_installments"]').value = "3";
            // Pay once the form has enabled the button.
            const pay = () => {{
                const button = document.querySelector(
                    '[name="o_payment_submit_button"]'
                );
                if (button.disabled) {{
                    setTimeout(pay, 200);
                }} else {{
                    button.click();
                }}
            }};
            setTimeout(pay, 200);
        """
        ready = (
            "Boolean(document.querySelector("
            """'select[name="o_payment_installments"]'))"""
        )
        self.browser_js(url, code, ready=ready, timeout=120)
        tx = self.env["payment.transaction"].search(
            [("partner_id", "=", self.partner.id)], order="id desc", limit=1
        )
        self.assertEqual(tx.installments, 3)
        self.assertEqual(tx.installment_amount, 400.0)
