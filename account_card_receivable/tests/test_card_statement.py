# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import CardReceivableCommon


@tagged("post_install", "-at_install")
class TestCardStatement(CardReceivableCommon):
    def test_adjustments_and_chargebacks_explain_the_deposit(self):
        """The acquirer deducts a terminal rental and takes a sale back: the
        deposit is lower, and every cent of the difference has an account."""
        invoice = self._invoice(1000.0)
        self._pay(invoice, acquirer_reference="200001")
        day = self.sale_date + timedelta(days=30)
        statement = self._statement(
            self._settlement_lines("200001", [1000.0], 3.0)
            + [
                {
                    "line_type": "adjustment",
                    "payment_date": day,
                    "net_amount": -50.0,
                    "description": "Terminal rental",
                },
                {
                    "line_type": "chargeback",
                    "payment_date": day,
                    "reference": "199999",
                    "net_amount": -200.0,
                    "description": "Chargeback of an older sale",
                },
            ]
        )
        self.assertEqual(set(statement.line_ids.mapped("state")), {"matched"})
        statement.action_reconcile()
        banked = self._bank_deposits()
        self.assertEqual(banked, 720.0)
        self.assertEqual(self._balance(self.adjustment_account), 50.0)
        self.assertEqual(self._balance(self.chargeback_account), 200.0)
        for account in (self.receivable_account, self.clearing_account):
            self.assertEqual(self._balance(account), 0.0)
        self.assertEqual(banked + 30.0 + 50.0 + 200.0, invoice.amount_total)

    def test_anticipation_fee_has_its_own_amount(self):
        invoice = self._invoice(600.0)
        self._pay(invoice, installments=3, acquirer_reference="200002")
        lines = self._settlement_lines("200002", [200.0] * 3, 4.0)
        for line in lines:
            # Everything paid on the first date, at a cost.
            line.update(
                {
                    "payment_date": self.sale_date + timedelta(days=30),
                    "anticipation_fee_amount": 2.0,
                    "net_amount": line["net_amount"] - 2.0,
                }
            )
        statement = self._statement(lines)
        statement.action_reconcile()
        banked = self._bank_deposits()
        self.assertEqual(banked, 570.0)
        self.assertEqual(self._balance(self.fee_account), 30.0)
        self.assertEqual(self._balance(self.receivable_account), 0.0)
        self.assertEqual(self._balance(self.clearing_account), 0.0)

    def test_line_that_does_not_explain_its_net_is_left_out(self):
        invoice = self._invoice(300.0)
        self._pay(invoice, acquirer_reference="200003")
        other = self._invoice(100.0)
        self._pay(other, acquirer_reference="200004")
        lines = self._settlement_lines("200003", [300.0], 3.0)
        lines += self._settlement_lines("200004", [100.0], 3.0)
        lines[1]["net_amount"] = 96.0  # gross 100, fee 3
        statement = self._statement(lines)
        self.assertEqual(statement.line_ids.mapped("state"), ["matched", "invalid"])
        self.assertEqual(statement.unexplained_count, 1)
        statement.action_reconcile()
        self.assertEqual(statement.state, "draft")
        self.assertEqual(statement.line_ids.mapped("state"), ["reconciled", "invalid"])
        self.assertEqual(self._balance(self.receivable_account), 100.0)

    def test_amount_that_differs_is_not_reconciled(self):
        invoice = self._invoice(300.0)
        self._pay(invoice, acquirer_reference="200005")
        statement = self._statement(self._settlement_lines("200005", [250.0], 3.0))
        self.assertEqual(statement.line_ids.state, "amount_divergent")
        with self.assertRaises(UserError):
            statement.action_reconcile()

    def test_reference_that_is_not_in_odoo(self):
        statement = self._statement(self._settlement_lines("299999", [10.0], 3.0))
        self.assertEqual(statement.line_ids.state, "not_found")

    def test_same_reference_on_two_sales_needs_the_authorization(self):
        first = self._invoice(300.0)
        self._pay(first, acquirer_reference="200006", authorization_code="AAA111")
        second = self._invoice(400.0)
        self._pay(second, acquirer_reference="200006", authorization_code="BBB222")
        statement = self._statement(self._settlement_lines("200006", [400.0], 3.0))
        self.assertEqual(statement.line_ids.state, "ambiguous")
        statement = self._statement(
            self._settlement_lines("200006", [400.0], 3.0, authorization="BBB222")
            + self._settlement_lines("200006", [300.0], 3.0, authorization="AAA111")
        )
        self.assertEqual(statement.line_ids.mapped("state"), ["matched", "matched"])
        statement.action_reconcile()
        banked = self._bank_deposits()
        self.assertClosed(first | second, banked, fees=21.0)

    def test_fee_that_differs_from_the_contract_is_shown(self):
        invoice = self._invoice(1000.0)
        self._pay(invoice, acquirer_reference="200007")
        statement = self._statement(self._settlement_lines("200007", [1000.0], 3.5))
        line = statement.line_ids
        self.assertEqual(line.state, "matched")
        self.assertEqual(line.expected_fee, 30.0)
        self.assertEqual(line.fee_difference, 5.0)
        self.assertTrue(line.note)

    def test_import_of_the_generic_file(self):
        invoice = self._invoice(600.0)
        self._pay(invoice, installments=3, acquirer_reference="200008")
        self.acquirer.establishment_code = "E1"
        rows = [
            "type;payment_date;sale_date;establishment;reference;"
            "installment;installment_count;gross;fee;net"
        ]
        for number in range(3):
            day = self.sale_date + timedelta(days=30 * (number + 1))
            rows.append(
                f"settlement;{day:%d/%m/%Y};{self.sale_date};E1;200008;"
                f"{number + 1};3;200,00;8,00;192,00"
            )
        rows.append("settlement;01/01/2026;;E2;777;1;1;10,00;0,30;9,70")
        statement = self.env["account.card.statement"].create(
            {
                "acquirer_id": self.acquirer.id,
                "data_file": base64.b64encode("\n".join(rows).encode()),
            }
        )
        statement.action_import_file()
        self.assertEqual(len(statement.line_ids), 3)
        self.assertEqual(statement.ignored_lines, 1)
        self.assertEqual(set(statement.line_ids.mapped("state")), {"matched"})
        self.assertEqual(statement.amount_net, 576.0)
        statement.action_reconcile()
        banked = self._bank_deposits()
        self.assertClosed(invoice, banked, fees=24.0)

    def test_file_without_the_required_columns(self):
        statement = self.env["account.card.statement"].create(
            {
                "acquirer_id": self.acquirer.id,
                "data_file": base64.b64encode(b"a;b\n1;2"),
            }
        )
        with self.assertRaises(UserError):
            statement.action_import_file()
