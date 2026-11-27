A card payment is not always made through a payment provider connected to Odoo.
The customer may pay on a card terminal that stands on the counter, and someone
registers the payment afterwards, on the invoice.

This module brings the installments and the card data to the payments of
accounting, with the same fields as the online transactions:

- an installment plan can be linked to journals, so that it serves payments
  registered by hand;
- the payment registration wizard of the invoice asks for the number of
  installments, the acquirer reference (NSU), the authorization code and the
  card brand, when the journal has a plan;
- the payment created for an online transaction inherits what the transaction
  knows.

The payment keeps the amount of the invoice. Interest charged by the card
issuer is recorded for information only.
