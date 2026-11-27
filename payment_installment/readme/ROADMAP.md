- The interest is recorded on the transaction but not posted to the accounts:
  no journal entry is created for it, whoever pays it.
- A surcharge kept by the merchant, which changes the total of the sales order
  or invoice, is not handled here: it needs a line on the document before the
  transaction is created.
- A saved card (token) is always charged in a single installment.
- Providers whose own widget lets the payer choose the installments (Mercado
  Pago bricks, for instance) do not use the selector of this module, only the
  fields of the transaction.
- No provider mapping is shipped: each provider module declares its own.
- The plan is the same for every card brand. A plan per brand needs a brand
  selector, or the brand detected from the card number.
