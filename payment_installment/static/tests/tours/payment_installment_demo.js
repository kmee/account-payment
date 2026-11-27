/** @odoo-module **/

import {registry} from "@web/core/registry";

registry.category("web_tour.tours").add("payment_installment_demo", {
    steps: () => [
        {
            content: "Choose the demo provider",
            trigger: 'input[name="o_payment_radio"][data-provider-code="demo"]',
            run: "click",
        },
        {
            content: "Pick twelve installments",
            trigger:
                '[name="o_payment_option"]:has(input[data-provider-code="demo"]) select[name="o_payment_installments"]',
            run: "select 12",
        },
        {
            content: "Fill the card of the demo provider",
            trigger: 'input[name="customer_input"]',
            run: "edit 4242424242424242",
        },
        {
            content: "Pay",
            trigger: 'button[name="o_payment_submit_button"]:not([disabled])',
            run: "click",
        },
        {
            content: "The payment is confirmed",
            trigger: 'div[name="o_payment_status_alert"].alert-success',
        },
        {
            content: "The payer sees the installments on the confirmation page",
            trigger: '[name="o_payment_installment_summary"]:contains("12 installments")',
        },
    ],
});
