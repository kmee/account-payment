Payments in a journal of the acquirer open the receivables by themselves. They
are listed in *Accounting > Customers > Card Receivables*.

To settle them, create a statement (*Accounting > Customers > Acquirer
Statements*), import the file or type the lines, and click *Match*. Each line
tells what was found. Click *Reconcile* to post the lines that are matched and
already paid.

The file is a CSV with the columns `type`, `payment_date`, `sale_date`,
`establishment`, `reference`, `authorization`, `brand`, `installment`,
`installment_count`, `gross`, `fee`, `anticipation_fee`, `net` and
`description`. `type` is `settlement`, `chargeback` or `adjustment`; a negative
`net` is an amount the acquirer takes back.

The net amounts wait in the clearing account, one line per day, to be matched
with the bank statement.
