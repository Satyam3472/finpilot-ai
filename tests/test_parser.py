import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

from finance_agent.parser import parse_statement


class StatementParserTest(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(folder) / "statement.csv"

    def parse_csv(self, rows, header="date,description,debit,credit"):
        self.path.write_text(header + "\n" + rows, encoding="utf-8")
        return parse_statement(self.path)

    def test_csv_aliases_and_normalization(self):
        result = self.parse_csv(
            '02-Oct-2026,  ZOMATO ORDER  ,"1,234.56",,TX-1\n'
            '15/10/2026,SALARY,0,"1,20,000",TX-2\n',
            " Transaction_Date ,NARRATION,Withdrawal,Deposit,Reference_ID",
        )
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["total_rows"], 2)
        debit, credit = result["records"]
        self.assertEqual(debit, {
            "transaction_date": "2026-10-02", "description": "ZOMATO ORDER",
            "type": "expense", "amount_minor": 123456, "currency": "INR",
            "reference_id": "TX-1",
        })
        self.assertEqual(credit["type"], "income")
        self.assertEqual(credit["amount_minor"], 12000000)

    def test_invalid_and_ambiguous_dates(self):
        for value in ("2026-02-30", "04/05/2026", "10/22/2026"):
            with self.subTest(value=value):
                error = self.parse_csv(f"{value},Example,1,\n")["errors"][0]
                self.assertEqual(error["row"], 2)
                self.assertIn("date", error["error"])

    def test_invalid_amounts_do_not_become_zero(self):
        for value in ("oops", "-5", "0.001", "NaN", "1,23", "1e3"):
            with self.subTest(value=value):
                result = self.parse_csv(f'2026-10-01,Example,"{value}",10\n')
                self.assertFalse(result["records"])
                self.assertIn("Debit", result["errors"][0]["error"])

    def test_rejects_conflicts_zero_and_empty_description(self):
        result = self.parse_csv(
            "2026-10-03,  ,1,\n2026-10-04,Conflict,1,2\n2026-10-05,Zero,0,0\n"
        )
        self.assertFalse(result["records"])
        self.assertEqual([item["row"] for item in result["errors"]], [2, 3, 4])
        self.assertIn("Description", result["errors"][0]["error"])
        self.assertIn("positive", result["errors"][1]["error"])

    def test_missing_and_duplicate_headers(self):
        with self.assertRaisesRegex(ValueError, "Missing required column: credit"):
            self.parse_csv("", "date,description,debit")
        with self.assertRaisesRegex(ValueError, "Multiple columns match date"):
            self.parse_csv("", "date,transaction_date,description,debit,credit")

    def test_unsupported_extension(self):
        with self.assertRaisesRegex(ValueError, r"\.csv or \.xlsx"):
            parse_statement(self.path.with_suffix(".pdf"))

    def test_labeled_sensitive_data_is_rejected_without_echoing_it(self):
        result = self.parse_csv("2026-10-01,TRANSFER ACCOUNT NO: 123456789,10,\n")
        self.assertFalse(result["records"])
        self.assertIn("account identifiers", result["errors"][0]["error"])
        self.assertNotIn("123456789", str(result))

    def test_parser_limits(self):
        with patch("finance_agent.parser.MAX_ROWS", 1):
            with self.assertRaisesRegex(ValueError, "row limit"):
                self.parse_csv("2026-10-01,A,1,\n2026-10-02,B,2,\n")
        with patch("finance_agent.parser.MAX_FILE_BYTES", 10):
            with self.assertRaisesRegex(ValueError, "file limit"):
                self.parse_csv("2026-10-01,A,1,\n")

    def test_xlsx_date_cells_and_rejection_of_formulas_and_errors(self):
        path = self.path.with_suffix(".xlsx")
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(("date", "description", "debit", "credit"))
        sheet.append((date(2026, 10, 2), "UBER TRIP", 20.50, None))
        sheet.append((date(2026, 10, 3), "Salary", None, 500))
        sheet.append((date(2026, 10, 4), "Formula", 20, "=1+1"))
        sheet.append((date(2026, 10, 5), "#DIV/0!", 20, None))
        workbook.save(path)
        workbook.close()

        result = parse_statement(path)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["records"][0]["transaction_date"], "2026-10-02")
        self.assertEqual(result["records"][0]["amount_minor"], 2050)
        self.assertEqual(result["records"][1]["type"], "income")
        self.assertEqual([error["row"] for error in result["errors"]], [4, 5])
