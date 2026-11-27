- The file layout is generic: the layouts of each acquirer are to be converted
  to it by their own modules.
- Point of sale payments do not open receivables yet: the session closing posts
  card payments in bulk.
- Only the company currency is handled.
- A chargeback is posted as a loss; taking the amount back from the customer is
  manual.
- A refund of the sale does not reverse the receivables of the acquirer.
- There is no closing report yet; `account.card.acquirer._get_balances` gives
  what is open.
