/** @odoo-module **/

import paymentForm from "@payment/js/payment_form";

paymentForm.include({
    /**
     * Send the number of installments picked by the payer along with the
     * transaction route params.
     *
     * @override method from @payment/js/payment_form
     * @private
     * @return {Object} The transaction route params.
     */
    _prepareTransactionRouteParams() {
        const transactionRouteParams = this._super(...arguments);
        const installments = this._getSelectedInstallments();
        if (installments > 1) {
            transactionRouteParams.installments = installments;
        }
        return transactionRouteParams;
    },

    /**
     * Read the installment selector of the checked payment option, if any.
     *
     * Tokens are always charged in a single installment.
     *
     * @private
     * @return {Number} The number of installments, 1 when there is no selector.
     */
    _getSelectedInstallments() {
        const radio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (!radio || this._getPaymentOptionType(radio) === "token") {
            return 1;
        }
        const select = this._getInlineForm(radio)?.querySelector(
            'select[name="o_payment_installments"]'
        );
        return select ? parseInt(select.value) || 1 : 1;
    },
});
