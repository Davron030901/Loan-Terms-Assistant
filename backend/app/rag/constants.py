"""Deterministic domain vocabulary used to widen a query without calling an LLM."""

from __future__ import annotations

# Contracts and humans use different words for the same clause. Expanding the query with
# a handful of contract-native synonyms measurably improves recall, costs nothing, and
# stays fully auditable (no hidden model call).
SYNONYMS: dict[str, str] = {
    "late payment": "default overdue arrears penalty late charge",
    "interest": "rate APR annual percentage finance charge",
    "early repayment": "prepayment prepay settle early redemption",
    "fee": "charge cost commission expense",
    "penalty": "default charge liquidated damages",
    "cancel": "termination terminate rescind cooling off",
    "eligibility": "qualify eligible criteria requirements borrower",
    "instalment": "installment repayment schedule monthly payment",
}


def expand(question: str) -> str:
    lowered = question.lower()
    extras = [value for key, value in SYNONYMS.items() if key in lowered]
    return f"{question} {' '.join(extras)}".strip() if extras else question
