When a customer pays by card, the money is not in the bank: the card acquirer
owes it, pays it later, sometimes in several settlements, and keeps a fee. This
module follows the money from the payment to the bank, so that every account in
between ends at zero.

- **Receivables from the acquirer.** A payment registered in a journal of an
  acquirer is moved to the acquirer: one receivable per settlement the acquirer
  will make, each with its due date. It works the same for an online
  transaction and for a payment registered by hand, and each payment opens its
  own receivables, for its own amount.
- **Settlement rules.** Per kind of payment (debit, credit, installments
  financed by the company, installments financed by the issuer), range of
  installments and card brand: the fee of the contract, the days to the first
  settlement, the interval, and whether the acquirer pays the sale at once.
- **Acquirer statements.** The statement of the acquirer is imported and
  matched with the receivables by reference, authorization code and date of the
  sale. Settlements, anticipation fees, chargebacks and adjustments each go to
  their account, and the net of each day goes to a clearing account, where the
  bank statement meets it.
- **Nothing is forced.** A line whose amounts do not add up, a reference found
  on two sales or an amount that differs are left out and shown, instead of
  being reconciled with a difference.
