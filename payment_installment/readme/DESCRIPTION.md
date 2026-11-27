This module lets a payer split a card payment into installments, as is usual in
Brazil and in several other countries ("12x no cartao", "cuotas", "taksit").

It is the provider-independent part of the feature:

- installment plans, set per provider and payment method, with the options
  offered (2x, 3x, ... 12x), the interest of each option and a minimum
  installment amount;
- an installment selector in the payment form, shown wherever the form is used
  (eCommerce checkout, customer portal, payment links);
- the number of installments, the installment amount, the interest and the
  amount charged to the payer, stored on the payment transaction;
- the card brand, the acquirer reference (NSU) and the authorization code on the
  transaction, filled from what the provider reports.

Sending the number of installments to the gateway is the job of each provider
module, which reads it from the transaction.
