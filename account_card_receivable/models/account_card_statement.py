# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import csv
import io
from collections import defaultdict
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount

LINE_TYPES = [
    ("settlement", "Settlement"),
    ("chargeback", "Chargeback"),
    ("adjustment", "Adjustment"),
]

# Columns of the generic file. Acquirer layouts are converted to it.
FILE_COLUMNS = (
    "type",
    "payment_date",
    "sale_date",
    "establishment",
    "reference",
    "authorization",
    "brand",
    "installment",
    "installment_count",
    "gross",
    "fee",
    "anticipation_fee",
    "net",
    "description",
)


def _to_float(value):
    value = (value or "").strip()
    if not value:
        return 0.0
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    return float(value)


def _to_date(value):
    value = (value or "").strip()
    if not value:
        return False
    for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise UserError(_("Date %s is not valid.", value))


class AccountCardStatement(models.Model):
    _name = "account.card.statement"
    _description = "Card Acquirer Statement"
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, default="/", readonly=True)
    acquirer_id = fields.Many2one(
        comodel_name="account.card.acquirer", required=True, check_company=True
    )
    company_id = fields.Many2one(
        related="acquirer_id.company_id", store=True, precompute=True
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    date = fields.Date(required=True, default=fields.Date.context_today)
    data_file = fields.Binary(string="File", attachment=True)
    filename = fields.Char()
    state = fields.Selection(
        selection=[("draft", "To Reconcile"), ("done", "Reconciled")],
        default="draft",
        required=True,
        copy=False,
    )
    line_ids = fields.One2many(
        comodel_name="account.card.statement.line", inverse_name="statement_id"
    )
    move_ids = fields.Many2many(
        comodel_name="account.move", string="Settlement Entries", copy=False
    )
    ignored_lines = fields.Integer(readonly=True, copy=False)
    amount_gross = fields.Monetary(compute="_compute_amounts")
    amount_fee = fields.Monetary(compute="_compute_amounts")
    amount_net = fields.Monetary(compute="_compute_amounts")
    unexplained_count = fields.Integer(
        compute="_compute_amounts",
        help="Lines that could not be reconciled and need to be looked at.",
    )

    @api.depends(
        "line_ids.gross_amount",
        "line_ids.fee_amount",
        "line_ids.anticipation_fee_amount",
        "line_ids.net_amount",
        "line_ids.state",
    )
    def _compute_amounts(self):
        for statement in self:
            lines = statement.line_ids
            statement.amount_gross = sum(lines.mapped("gross_amount"))
            statement.amount_fee = sum(lines.mapped("fee_amount")) + sum(
                lines.mapped("anticipation_fee_amount")
            )
            statement.amount_net = sum(lines.mapped("net_amount"))
            statement.unexplained_count = len(
                lines.filtered(lambda line: line.state not in ("matched", "reconciled"))
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("account.card.statement") or "/"
                )
        return super().create(vals_list)

    # === IMPORT === #

    def action_import_file(self):
        """Read the lines of the file, in the generic layout."""
        self.ensure_one()
        if not self.data_file:
            raise UserError(_("Choose a file to import."))
        content = base64.b64decode(self.data_file).decode("utf-8-sig")
        dialect = ";" if content.count(";") > content.count(",") else ","
        reader = csv.DictReader(io.StringIO(content), delimiter=dialect)
        missing = {"payment_date", "net"} - set(reader.fieldnames or [])
        if missing:
            raise UserError(
                _(
                    "The file has no column %(columns)s. Expected columns: "
                    "%(expected)s.",
                    columns=", ".join(sorted(missing)),
                    expected=", ".join(FILE_COLUMNS),
                )
            )
        establishment = self.acquirer_id.establishment_code
        values_list = []
        ignored = 0
        for row in reader:
            row_establishment = (row.get("establishment") or "").strip()
            if establishment and row_establishment and row_establishment != establishment:
                ignored += 1
                continue
            values_list.append(self._prepare_line_values(row))
        self.line_ids.filtered(lambda line: line.state != "reconciled").unlink()
        self.env["account.card.statement.line"].create(values_list)
        self.ignored_lines = ignored
        self.action_match()
        return True

    def _prepare_line_values(self, row):
        line_type = (row.get("type") or "settlement").strip().lower()
        if line_type not in dict(LINE_TYPES):
            raise UserError(_("Line type %s is not known.", line_type))
        return {
            "statement_id": self.id,
            "line_type": line_type,
            "payment_date": _to_date(row.get("payment_date")),
            "sale_date": _to_date(row.get("sale_date")),
            "establishment": (row.get("establishment") or "").strip(),
            "reference": (row.get("reference") or "").strip(),
            "authorization": (row.get("authorization") or "").strip(),
            "brand": (row.get("brand") or "").strip(),
            "installment": int(row.get("installment") or 1),
            "installment_count": int(row.get("installment_count") or 1),
            "gross_amount": _to_float(row.get("gross")),
            "fee_amount": _to_float(row.get("fee")),
            "anticipation_fee_amount": _to_float(row.get("anticipation_fee")),
            "net_amount": _to_float(row.get("net")),
            "description": (row.get("description") or "").strip(),
        }

    # === MATCH AND RECONCILE === #

    def action_match(self):
        for statement in self:
            statement.line_ids.filtered(
                lambda line: line.state != "reconciled"
            )._match()
        return True

    def action_reconcile(self):
        for statement in self:
            statement._reconcile()
        return True

    def _reconcile(self):
        """Post what the acquirer says it settled, up to today.

        Every amount of the statement goes somewhere: the gross amounts settle
        the receivables, the fees are an expense, chargebacks and adjustments
        go to their accounts, and the net of each day goes to the clearing
        account, where the bank statement will meet it. A line that cannot be
        explained is left out and stays to be looked at.
        """
        self.ensure_one()
        acquirer = self.acquirer_id
        today = fields.Date.context_today(self)
        lines = self.line_ids.filtered(
            lambda line: line.state == "matched" and line.payment_date <= today
        )
        if not lines:
            raise UserError(_("There is no matched line paid until today."))
        partner = acquirer.partner_id.id
        move_lines = []
        fees = defaultdict(float)
        anticipation = defaultdict(float)
        nets = defaultdict(float)
        for line in lines:
            nets[line.payment_date] += line.net_amount
            if line.line_type == "settlement":
                fees[line.payment_date] += line.fee_amount
                anticipation[line.payment_date] += line.anticipation_fee_amount
                move_lines.append(
                    {
                        "name": line._get_label(),
                        "account_id": acquirer.receivable_account_id.id,
                        "partner_id": partner,
                        "debit": 0.0,
                        "credit": line.gross_amount,
                        "card_acquirer_id": acquirer.id,
                        "card_payment_id": line.move_line_id.card_payment_id.id,
                        "card_acquirer_reference": line.reference,
                        "card_installment": line.move_line_id.card_installment,
                        "card_installment_count": line.move_line_id.card_installment_count,
                    }
                )
            else:
                account = line._get_adjustment_account()
                move_lines.append(
                    {
                        "name": line._get_label(),
                        "account_id": account.id,
                        "partner_id": partner,
                        "debit": -line.net_amount if line.net_amount < 0 else 0.0,
                        "credit": line.net_amount if line.net_amount > 0 else 0.0,
                    }
                )
        currency = self.currency_id
        for day in sorted(nets):
            for amounts, account, label in (
                (fees, acquirer.fee_account_id, _("Fees")),
                (
                    anticipation,
                    acquirer.anticipation_account_id or acquirer.fee_account_id,
                    _("Anticipation"),
                ),
            ):
                if not currency.is_zero(amounts[day]):
                    move_lines.append(
                        {
                            "name": f"{label} {acquirer.name} {day}",
                            "account_id": account.id,
                            "partner_id": partner,
                            "debit": amounts[day],
                            "credit": 0.0,
                        }
                    )
            net = currency.round(nets[day])
            if not currency.is_zero(net):
                move_lines.append(
                    {
                        "name": _(
                            "Settlement %(acquirer)s %(day)s",
                            acquirer=acquirer.name,
                            day=day,
                        ),
                        "account_id": acquirer.clearing_account_id.id,
                        "partner_id": partner,
                        "debit": net if net > 0 else 0.0,
                        "credit": -net if net < 0 else 0.0,
                        "date_maturity": day,
                    }
                )
        move = (
            self.env["account.move"]
            .sudo()
            .create(
                {
                    "move_type": "entry",
                    "journal_id": acquirer.journal_id.id,
                    "company_id": self.company_id.id,
                    "date": max(lines.mapped("payment_date")),
                    "ref": _("Statement %s", self.name),
                    "line_ids": [fields.Command.create(vals) for vals in move_lines],
                }
            )
        )
        move.action_post()
        credit_lines = move.line_ids.filtered(
            lambda aml: aml.account_id == acquirer.receivable_account_id
        )
        settlements = lines.filtered(lambda line: line.line_type == "settlement")
        for line, credit in zip(settlements, credit_lines, strict=True):
            (credit | line.move_line_id).reconcile()
        lines.state = "reconciled"
        settlements.move_line_id.card_payment_id._card_reconcile_rounding(acquirer)
        self.move_ids = [fields.Command.link(move.id)]
        if all(line.state == "reconciled" for line in self.line_ids):
            self.state = "done"
        return move


class AccountCardStatementLine(models.Model):
    _name = "account.card.statement.line"
    _description = "Card Acquirer Statement Line"
    _order = "payment_date, reference, installment, id"

    statement_id = fields.Many2one(
        comodel_name="account.card.statement",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(related="statement_id.company_id", store=True)
    currency_id = fields.Many2one(related="statement_id.currency_id")
    line_type = fields.Selection(
        selection=LINE_TYPES, required=True, default="settlement"
    )
    payment_date = fields.Date(required=True)
    sale_date = fields.Date()
    establishment = fields.Char()
    reference = fields.Char(
        help="Reference of the sale at the acquirer (NSU in Brazil)."
    )
    authorization = fields.Char()
    brand = fields.Char()
    installment = fields.Integer(default=1)
    installment_count = fields.Integer(default=1)
    gross_amount = fields.Monetary()
    fee_amount = fields.Monetary()
    anticipation_fee_amount = fields.Monetary(string="Anticipation Fee")
    net_amount = fields.Monetary(
        help="What goes to the bank for this line. Negative when the acquirer "
        "takes the amount back."
    )
    description = fields.Char()
    move_line_id = fields.Many2one(
        comodel_name="account.move.line", string="Receivable", readonly=True
    )
    expected_fee = fields.Monetary(readonly=True)
    fee_difference = fields.Monetary(
        readonly=True, help="Fee charged minus the fee of the contract."
    )
    state = fields.Selection(
        selection=[
            ("new", "New"),
            ("matched", "Matched"),
            ("amount_divergent", "Amount Differs"),
            ("not_found", "Not Found"),
            ("ambiguous", "Ambiguous"),
            ("invalid", "Invalid"),
            ("reconciled", "Reconciled"),
        ],
        default="new",
        required=True,
        readonly=True,
    )
    note = fields.Char(readonly=True)

    def _get_label(self):
        self.ensure_one()
        if self.line_type != "settlement":
            return self.description or dict(LINE_TYPES)[self.line_type]
        return _(
            "Ref. %(reference)s %(number)s/%(count)s",
            reference=self.reference or "-",
            number=self.installment,
            count=self.installment_count,
        )

    def _get_adjustment_account(self):
        self.ensure_one()
        acquirer = self.statement_id.acquirer_id
        account = acquirer.adjustment_account_id
        if self.line_type == "chargeback":
            account = acquirer.chargeback_account_id or account
        if not account:
            raise UserError(
                _(
                    "Set the adjustment account of acquirer %(acquirer)s to "
                    "reconcile the line %(line)s.",
                    acquirer=acquirer.display_name,
                    line=self._get_label(),
                )
            )
        return account

    def _is_balanced(self):
        """A settlement has to explain its own net amount."""
        self.ensure_one()
        return self.currency_id.is_zero(
            self.gross_amount
            - self.fee_amount
            - self.anticipation_fee_amount
            - self.net_amount
        )

    def _get_candidates(self, taken):
        """Return the open receivables the line may be settling.

        The reference of the acquirer alone is not enough: it may repeat
        between terminals and over time. The authorization code and the date of
        the sale narrow the search when both sides have them.
        """
        self.ensure_one()
        acquirer = self.statement_id.acquirer_id
        candidates = self.env["account.move.line"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("account_id", "=", acquirer.receivable_account_id.id),
                ("card_acquirer_id", "=", acquirer.id),
                ("card_acquirer_reference", "=", self.reference),
                ("parent_state", "=", "posted"),
                ("reconciled", "=", False),
                ("debit", ">", 0),
                ("id", "not in", taken.ids),
            ]
        )
        if self.authorization:
            by_authorization = candidates.filtered(
                lambda aml: aml.card_authorization_code == self.authorization
            )
            candidates = by_authorization or candidates.filtered(
                lambda aml: not aml.card_authorization_code
            )
        if self.sale_date:
            by_date = candidates.filtered(
                lambda aml: aml.card_sale_date == self.sale_date
            )
            candidates = by_date or candidates
        return candidates

    def _match(self):
        taken = self.env["account.move.line"]
        for line in self:
            values = {
                "move_line_id": False,
                "expected_fee": 0.0,
                "fee_difference": 0.0,
                "note": False,
            }
            currency = line.currency_id
            if line.line_type != "settlement":
                line.write({**values, "state": "matched"})
                continue
            if not line._is_balanced():
                line.write(
                    {
                        **values,
                        "state": "invalid",
                        "note": _("Gross amount minus fees differs from the net."),
                    }
                )
                continue
            if not line.reference:
                line.write(
                    {**values, "state": "not_found", "note": _("No reference.")}
                )
                continue
            candidates = line._get_candidates(taken)
            if len(candidates.card_payment_id) > 1:
                line.write(
                    {
                        **values,
                        "state": "ambiguous",
                        "note": _(
                            "Several sales have this reference: %(payments)s.",
                            payments=", ".join(
                                candidates.card_payment_id.mapped("display_name")
                            ),
                        ),
                    }
                )
                continue
            if len(candidates) == 1 and candidates.card_installment_count == 1:
                receivable = candidates
            else:
                receivable = candidates.filtered(
                    lambda aml: aml.card_installment == line.installment
                )[:1]
            if not receivable:
                line.write(
                    {
                        **values,
                        "state": "not_found",
                        "note": _("No open receivable with this reference."),
                    }
                )
                continue
            taken |= receivable
            acquirer = line.statement_id.acquirer_id
            notes = []
            expected_fee = acquirer._get_expected_fee(
                receivable.card_modality,
                receivable.card_payment_id.installments,
                line.gross_amount,
                receivable.card_brand_id,
            )
            fee_difference = currency.round(line.fee_amount - expected_fee)
            if expected_fee and not currency.is_zero(fee_difference):
                notes.append(
                    _(
                        "Fee %(charged)s, contract %(expected)s.",
                        charged=format_amount(self.env, line.fee_amount, currency),
                        expected=format_amount(self.env, expected_fee, currency),
                    )
                )
            state = "matched"
            difference = currency.round(line.gross_amount - receivable.amount_residual)
            if not currency.is_zero(difference):
                within_tolerance = (
                    receivable.card_installment_count > 1
                    and abs(difference) <= acquirer.amount_tolerance
                )
                if not within_tolerance:
                    state = "amount_divergent"
                notes.insert(
                    0,
                    _(
                        "Open %(open)s, settled %(gross)s.",
                        open=format_amount(
                            self.env, receivable.amount_residual, currency
                        ),
                        gross=format_amount(self.env, line.gross_amount, currency),
                    ),
                )
            line.write(
                {
                    "move_line_id": receivable.id,
                    "state": state,
                    "expected_fee": expected_fee,
                    "fee_difference": fee_difference if expected_fee else 0.0,
                    "note": " ".join(notes) or False,
                }
            )
