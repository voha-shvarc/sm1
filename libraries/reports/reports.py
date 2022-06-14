import csv

from jinja2 import Environment, FileSystemLoader
from dataclasses import dataclass, fields, asdict


@dataclass
class ReportItem:
    claim_type = None
    client = None
    blank_member_numbers = None
    blank_client_email = None
    blank_authorization_numbers = None
    processing_or_processed_row = None
    row_without_edit_button = None
    set_for_cash_pay = None
    verified_mark_as_worked = None


class Report:
    def __init__(self):
        self._env = Environment(
            loader=FileSystemLoader("template"),
            autoescape=True,
        )
        self.rows = []

    def render(self, template: str, **context) -> str:
        template = self._env.get_template(template)
        return template.render(**context)

    def to_html(self, template: str) -> str:
        return self.render(template, report=self.rows)

    def add_row(self, report_object: ReportItem):
        if report_object.processing_or_processed_row:
            report_object.processing_or_processed_row = 1
        else:
            report_object.processing_or_processed_row = 0

        if report_object.verified_mark_as_worked:
            report_object.verified_mark_as_worked = 1
        else:
            report_object.verified_mark_as_worked = 0

        if report_object.blank_authorization_numbers:
            report_object.blank_authorization_numbers = 1
        else:
            report_object.blank_authorization_numbers = 0

        if report_object.blank_member_numbers:
            report_object.blank_member_numbers = 1
        else:
            report_object.blank_member_numbers = 0

        if report_object.blank_client_email:
            report_object.blank_client_email = 1
        else:
            report_object.blank_client_email = 0
        self.rows.append(report_object)

    def html_report(self, filepath, template):
        filepath = filepath.with_suffix(".html")
        filepath.write_text(self.to_html(template), encoding="utf-8")

    def csv_report(self, filepath):
        with filepath.open("w", newline="") as file:
            fieldnames = [field.name for field in fields(ReportItem)]
            writer = csv.DictWriter(file, fieldnames)
            writer.writeheader()
            writer.writerows(map(asdict, self.rows))
