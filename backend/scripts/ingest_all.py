"""CLI: turn the real bank PDFs into a searchable, page-accurate index.

    python -m scripts.ingest_all --all --recreate
    python -m scripts.ingest_all --doc cibc_personal
"""

from __future__ import annotations

import argparse
import sys

from app.rag import registry
from app.rag.ingest import ingest_all, ingest_document


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest loan documents into Qdrant Cloud.")
    parser.add_argument("--all", action="store_true", help="ingest every registered document")
    parser.add_argument("--doc", help=f"one of: {', '.join(registry.document_ids())}")
    parser.add_argument("--recreate", action="store_true", help="rebuild the collection first")
    args = parser.parse_args()

    if not args.all and not args.doc:
        parser.error("choose --all or --doc <doc_id>")

    reports = ingest_all(recreate=args.recreate) if args.all else [ingest_document(args.doc)]

    print(f"\n{'doc_id':<16}{'pages':>7}{'chunks':>8}{'seconds':>9}")
    print("-" * 40)
    for r in reports:
        print(f"{r.doc_id:<16}{r.pages:>7}{r.chunks:>8}{r.seconds:>9.1f}")
    print("-" * 40)
    print(f"{'TOTAL':<16}{sum(r.pages for r in reports):>7}{sum(r.chunks for r in reports):>8}")
    print("\nThe documents are ready. Do not run ingestion and the API against a rebuild at once.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
