/* Copyright 2026 KMEE
   License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl). */

import paymentForm from "@payment/js/payment_form";

paymentForm.include({
    /**
     * @override
     */
    _prepareTransactionRouteParams() {
        const transactionRouteParams = this._super(...arguments);
        const installments = this._getSelectedInstallments();
        if (installments > 1) {
            transactionRouteParams.installments = installments;
        }
        return transactionRouteParams;
    },

    _getSelectedInstallments() {
        const radio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (!radio || this._getPaymentOptionType(radio) === "token") {
            return 1;
        }
        const select = this._getInlineForm(radio)?.querySelector(
            'select[name="o_payment_installments"]'
        );
        return select ? parseInt(select.value, 10) || 1 : 1;
    },
});
