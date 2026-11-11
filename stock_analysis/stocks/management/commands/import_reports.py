import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from stocks.report_import import import_record, prepare_record


class Command(BaseCommand):
    help = "Import stock reports from one JSON file or a directory of JSON files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Validate without database writes."
        )
        parser.add_argument(
            "--source",
            type=Path,
            help="JSON file or directory (default: company_jsons).",
        )

    def handle(self, *args, **options):
        source = options["source"] or Path(settings.BASE_DIR) / "company_jsons"
        files = [source] if source.is_file() else sorted(source.glob("*.json"))
        if not files:
            raise CommandError(f"No JSON files found at: {source}")
        parsed = created = skipped = invalid = 0
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise CommandError(f"Cannot read JSON file: {path}") from error
            if not isinstance(data, list):
                raise CommandError(f"Top-level JSON must be a list in {path}")
            for index, item in enumerate(data, 1):
                parsed += 1
                try:
                    prepared = prepare_record(item)
                except (
                    ValueError,
                    TypeError,
                    AttributeError,
                    ValidationError,
                ) as error:
                    invalid += 1
                    self.stderr.write(f"Invalid record {index} in {path}: {error}")
                    continue
                if not options["dry_run"]:
                    if import_record(prepared):
                        created += 1
                    else:
                        skipped += 1
        self.stdout.write(
            f"Done. Parsed={parsed} Created reports={created} Skipped reports={skipped} Invalid={invalid} Dry-run={options['dry_run']}"
        )
        if invalid:
            raise CommandError(
                f"{invalid} invalid record(s); valid records were {'validated' if options['dry_run'] else 'imported'}."
            )
