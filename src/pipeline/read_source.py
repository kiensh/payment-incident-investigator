"""Isolated stdlib archive reader. Run with python -I, never from download folders."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import stat
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

MEMBER_NAME = "digital_wallet_transactions.csv"
REQUIRED_COLUMNS = {
    "idx", "transaction_id", "user_id", "transaction_date", "product_category", "product_name",
    "merchant_name", "product_amount", "transaction_fee", "cashback", "loyalty_points",
    "payment_method", "transaction_status", "merchant_id", "device_type", "location",
}


def inspect_archive(path: Path, expected_sha256: str) -> dict[str, Any]:
    if path.stat().st_size > 5_000_000:
        raise ValueError("source archive exceeds size limit")
    archive_bytes = path.read_bytes()
    archive_hash = hashlib.sha256(archive_bytes).hexdigest()
    if archive_hash != expected_sha256:
        raise ValueError("source archive checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != MEMBER_NAME:
            raise ValueError("archive must contain exactly the expected CSV, without other files")
        member = members[0]
        name = PurePosixPath(member.filename)
        if name.is_absolute() or ".." in name.parts or stat.S_ISLNK(member.external_attr >> 16):
            raise ValueError("unsafe archive member")
        if member.file_size > 20_000_000 or member.flag_bits & 1:
            raise ValueError("oversized or encrypted source member")
        contents = archive.read(member)  # CRC checked by ZipFile; never extract or execute.
    reader = csv.DictReader(io.StringIO(contents.decode("utf-8-sig"), newline=""))
    if reader.fieldnames is None or set(reader.fieldnames) != REQUIRED_COLUMNS or len(reader.fieldnames) != len(REQUIRED_COLUMNS):
        raise ValueError("unexpected source CSV schema")
    rows = list(reader)
    if not rows or len(rows) > 100_000:
        raise ValueError("source row count out of bounds")
    merchant_names: dict[str, set[str]] = defaultdict(set)
    transaction_ids = Counter(row.get("transaction_id", "") for row in rows)
    invalid: list[dict[str, Any]] = []
    validated: list[dict[str, str]] = []
    null_counts: Counter[str] = Counter()
    for line, row in enumerate(rows, start=2):
        errors = []
        if None in row or any(value is None for value in row.values()):
            invalid.append({"csv_line": line, "issues": ["row field count differs from schema"]})
            continue
        for key, value in row.items():
            if not value.strip():
                null_counts[key] += 1
                errors.append(f"empty {key}")
        try:
            UUID(row["transaction_id"])
        except ValueError:
            errors.append("invalid transaction_id")
        if transaction_ids[row["transaction_id"]] != 1:
            errors.append("duplicate transaction_id")
        try:
            datetime.strptime(row["transaction_date"], "%Y-%m-%d %H:%M")
        except ValueError:
            errors.append("invalid transaction_date")
        for field in ("product_amount", "transaction_fee", "cashback"):
            try:
                number = Decimal(row[field])
                exponent = number.as_tuple().exponent
                if (not number.is_finite() or number < 0 or number > Decimal("1000000000000")
                        or (field == "product_amount" and number == 0)
                        or (isinstance(exponent, int) and exponent < -8) or len(row[field]) > 64):
                    errors.append(f"invalid {field}")
            except InvalidOperation:
                errors.append(f"invalid {field}")
        for field in ("idx", "loyalty_points"):
            try:
                if int(row[field]) < 0:
                    errors.append(f"invalid {field}")
            except ValueError:
                errors.append(f"invalid {field}")
        if row["transaction_status"] not in {"Successful", "Failed", "Pending"}:
            errors.append("unknown transaction_status")
        merchant_names[row["merchant_id"]].add(row["merchant_name"])
        if errors:
            invalid.append({"csv_line": line, "issues": errors})
        else:
            validated.append(row)
    ambiguous = {key: sorted(names) for key, names in sorted(merchant_names.items()) if len(names) > 1}
    quality = {
        "archive_sha256": archive_hash,
        "archive_bytes": len(archive_bytes),
        "csv_sha256": hashlib.sha256(contents).hexdigest(),
        "csv_bytes": len(contents),
        "member": MEMBER_NAME,
        "columns": reader.fieldnames,
        "row_count": len(rows),
        "valid_row_count": len(validated),
        "invalid_rows": invalid,
        "duplicate_transaction_id_count": sum(count - 1 for count in transaction_ids.values() if count > 1),
        "empty_value_counts": {key: null_counts[key] for key in sorted(REQUIRED_COLUMNS)},
        "status_counts": dict(sorted(Counter(row["transaction_status"] for row in validated).items())),
        "payment_method_counts": dict(sorted(Counter(row["payment_method"] for row in validated).items())),
        "merchant_id_count": len(merchant_names),
        "ambiguous_merchant_id_count": len(ambiguous),
        "ambiguous_merchants": ambiguous,
        "explicit_currency_column": False,
        "currency_unknown_rows": len(validated),
        "source_timezone": None,
        "timezone_unspecified_rows": len(validated),
        "source_lifecycle_columns": [],
        "source_limitations": [
            "Synthetic coarse transaction rows do not contain authorization/capture histories, webhook deliveries, or root causes.",
            "Merchant IDs can refer to unrelated merchant names; no identity merge is performed.",
            "Currency and timezone are absent and remain unknown in source context.",
        ],
    }
    return {"rows": validated, "quality": quality}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(inspect_archive(args.archive, args.expected_sha256), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
