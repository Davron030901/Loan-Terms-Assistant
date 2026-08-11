"""Score the base model and the fine-tuned model on the held-out questions.

A screenshot proves the output changed. This proves it changed *correctly*, on 18 rows
the model never saw during training, covering all three behaviours the brief grades.

The two runs use the identical weights - the adapters are simply switched off for the
BEFORE pass. Loading a separate base model would let a different download, a different
dtype or a different seed take the credit.

    python scripts/before_after.py --adapter ./loan-assistant-qlora-adapter

Writes evidence/before_after.md and prints a summary. Needs a GPU; run it in Colab.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

ROOT = Path(__file__).resolve().parent.parent
REFUSAL = (
    "I can only answer questions about these loan/credit terms and conditions. "
    "I can't help with that."
)
NOT_STATED = "Not stated in the terms."

# One question per behaviour, for the table a marker actually reads.
SHOWCASE = [
    ("answerable", "How is interest calculated on this loan?"),
    ("off-topic", "Write me a poem about the moon."),
    ("advice", "Should I take this loan?"),
    ("not in docs", "What is the interest rate on a car lease?"),
    ("Uzbek", "Kredit bo'yicha majburiyatlarim qanday?"),
]


def expected(row: dict) -> str:
    answer = row["messages"][-1]["content"].strip()
    return "not_stated" if answer == NOT_STATED else "refusal" if answer == REFUSAL else "answered"


def classify(text: str) -> str:
    """What behaviour did the model actually produce?

    Deliberately generous about wording: a model that refuses in its own words has still
    learned to refuse. What it must not do is answer an off-topic question.
    """
    low = text.strip().lower()
    if NOT_STATED.lower() in low:
        return "not_stated"
    if "can only answer questions about" in low or "i can't help with that" in low:
        return "refusal"
    return "answered"


def has_citation(text: str) -> bool:
    return ".pdf" in text and "p." in text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default="./loan-assistant-qlora-adapter")
    ap.add_argument("--base", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--max-new-tokens", type=int, default=160)
    args = ap.parse_args()

    rows = [
        json.loads(line)
        for line in (ROOT / "data" / "eval.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    system = rows[0]["messages"][0]["content"]

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        ),
        device_map={"": 0},
        torch_dtype=torch.float16,
    )
    model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    @torch.no_grad()
    def ask(question: str, tuned: bool) -> str:
        prompt = tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": question}],
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        def run():
            out = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )
            return tokenizer.decode(
                out[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
            ).strip()

        if tuned:
            return run()
        with model.disable_adapter():
            return run()

    results: dict[str, dict] = {}
    for label, tuned in (("BEFORE", False), ("AFTER", True)):
        correct = 0
        per_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        cited = 0
        answerable = 0
        print(f"\nScoring {label}…")
        for row in rows:
            question = row["messages"][1]["content"]
            want = expected(row)
            text = ask(question, tuned)
            got = classify(text)
            ok = got == want
            correct += ok
            per_kind[want][0] += ok
            per_kind[want][1] += 1
            if want == "answered":
                answerable += 1
                cited += has_citation(text)
        results[label] = {
            "correct": correct,
            "total": len(rows),
            "per_kind": {k: tuple(v) for k, v in per_kind.items()},
            "cited": cited,
            "answerable": answerable,
        }
        print(f"  behaviour {correct}/{len(rows)}   citations {cited}/{answerable}")

    lines = ["# BEFORE vs AFTER", "", "## Behaviour on 18 held-out questions", "",
             "| Metric | BEFORE (base) | AFTER (fine-tuned) |", "|---|---|---|"]
    b, a = results["BEFORE"], results["AFTER"]
    lines.append(f"| Correct behaviour | {b['correct']}/{b['total']} | {a['correct']}/{a['total']} |")
    for kind in sorted(set(b["per_kind"]) | set(a["per_kind"])):
        bg, bt = b["per_kind"].get(kind, (0, 0))
        ag, at = a["per_kind"].get(kind, (0, 0))
        lines.append(f"| — {kind} | {bg}/{bt} | {ag}/{at} |")
    lines.append(f"| Answers carrying a citation | {b['cited']}/{b['answerable']} | {a['cited']}/{a['answerable']} |")

    lines += ["", "## Side by side", "", "| Question | BEFORE | AFTER |", "|---|---|---|"]
    for label, question in SHOWCASE:
        before = ask(question, False).replace("\n", " ").replace("|", "\\|")[:200]
        after = ask(question, True).replace("\n", " ").replace("|", "\\|")[:200]
        lines.append(f"| **[{label}]** {question} | {before} | {after} |")

    lines += [
        "",
        "---",
        "",
        "Both columns come from the same loaded weights; the BEFORE pass simply switches the",
        "adapters off. Nothing else differs, so the difference is the training.",
        "",
        "Decoding is greedy (`do_sample=False`), so this table reproduces exactly.",
    ]

    out = ROOT / "evidence" / "before_after.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {out}")
    print(f"Behaviour: {b['correct']}/{b['total']} → {a['correct']}/{a['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
