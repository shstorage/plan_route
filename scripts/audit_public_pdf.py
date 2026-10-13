"""Read selected public PDF pages without adding a project dependency.

Run with ``uv run --with pypdf python scripts/audit_public_pdf.py``.
The /cN font in the inspected BHEL PDF stores ASCII code points offset by 29.
Decoded text must be checked against the source; this is not a generic OCR tool.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def main() -> None:
    from pypdf import PdfReader

    sys.stdout.reconfigure(errors="backslashreplace")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path(
            "data/benchmarks/public_source_cache/uppur-pe-ts-425-166-a001.pdf"
        ),
    )
    parser.add_argument("--pages", type=int, nargs="+", default=[83])
    args = parser.parse_args()
    reader = PdfReader(args.pdf)
    print(
        json.dumps(
            {
                "sha256": hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
                "pages": len(reader.pages),
            }
        )
    )
    for page in args.pages:
        raw = reader.pages[page - 1].extract_text()
        decoded = re.sub(r"/c(\d+)", lambda match: chr(int(match[1]) + 29), raw)
        print(f"PDF PAGE {page}\n{decoded}")


if __name__ == "__main__":
    main()
