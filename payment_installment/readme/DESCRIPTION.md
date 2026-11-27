This module lets a payer split a card payment into installments, as is usual
in Brazil and in other countries.

It is the provider-independent part of the feature:

- installment plans, per provider and payment method, with the options offered
  (2x, 3x ... 12x), the interest of each option, who pays it and a minimum
  installment amount;
- an installment selector in the payment form (eCommerce checkout, customer
  portal, payment links);
- the number of installments, the interest and the amount charged, stored on
  the payment transaction.

Sending the number of installments to the gateway is the job of each provider
module.
