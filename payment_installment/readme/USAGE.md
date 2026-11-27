On the payment form, the payer picks the payment method and then the number of
installments:

![Installment selector on the payment form](../static/description/payment_form.png)

The confirmation page shows how the payment was split:

![Payment confirmation](../static/description/payment_confirmation.png)

The transaction keeps what was chosen:

![Payment transaction](../static/description/payment_transaction.png)

When the interest is paid by the customer, the payer is charged the amount
plus the interest (*Amount Charged*); the amount of the transaction stays the
amount of the document being paid. When it is paid by the company, the option
is shown as interest-free and the interest is recorded on the transaction.

**For provider modules**

- set `support_installments` in `_compute_feature_support_fields`;
- read `installments` on the transaction when building the payment request;
- write `installments` and `amount_charged` if the gateway reports other
  values.
