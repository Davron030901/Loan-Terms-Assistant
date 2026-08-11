"""Standalone Gradio demo for the fine-tuned adapter.

The notebook launches a demo inline, which is fine for submitting a link. This file is
for when you want the demo to outlive the notebook session - a Hugging Face Space, a
second Colab, or a machine with a GPU.

    python app/gradio_demo.py --adapter ./loan-assistant-qlora-adapter --share

On a Hugging Face Space, set ADAPTER_ID to your uploaded adapter repo and run without
arguments.
"""

from __future__ import annotations

import argparse
import os

import gradio as gr
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

BASE_MODEL = os.environ.get("BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
ADAPTER_ID = os.environ.get("ADAPTER_ID", "./loan-assistant-qlora-adapter")

SYSTEM = (
    "You are a loan/credit Terms & Conditions assistant. You answer ONLY questions about "
    "the loan documents you were trained on. You cite the document and page. If something "
    "is not in the terms you say 'Not stated in the terms.' You refuse anything off-topic "
    "or advice."
)

EXAMPLES = [
    "How is interest calculated on this loan?",
    "What happens if I miss a payment?",
    "What are my obligations under this agreement?",
    "Write me a poem about the moon.",
    "Should I take this loan?",
    "What is the interest rate on a car lease?",
    "Kredit bo'yicha majburiyatlarim qanday?",
]


def load(adapter: str, base: str, four_bit: bool):
    """Load the frozen base and hang the trained adapter on it.

    4-bit keeps this inside a free T4 and matches how the adapter was trained. On a CPU
    box, pass --no-4bit: it is slow but it runs.
    """
    tokenizer = AutoTokenizer.from_pretrained(base)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    kwargs: dict = {"torch_dtype": torch.float16 if torch.cuda.is_available() else torch.float32}
    if four_bit and torch.cuda.is_available():
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        kwargs["device_map"] = {"": 0}

    model = AutoModelForCausalLM.from_pretrained(base, **kwargs)
    model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    return model, tokenizer


def build(model, tokenizer, compare: bool):
    @torch.no_grad()
    def generate(question: str, adapters_on: bool = True) -> str:
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with _adapters(model, adapters_on):
            out = model.generate(
                **inputs,
                max_new_tokens=200,
                do_sample=False,  # greedy, so a demo shown twice reads the same twice
                pad_token_id=tokenizer.pad_token_id,
            )
        return tokenizer.decode(
            out[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
        ).strip()

    def respond(message: str, history) -> str:
        if not message.strip():
            return "Ask me something about the loan documents."
        if not compare:
            return generate(message)
        # Side-by-side mode: the same weights answering with the adapters off, then on.
        # This is the BEFORE/AFTER evidence, live, rather than a screenshot.
        return (
            f"**BEFORE (base model)**\n\n{generate(message, adapters_on=False)}\n\n"
            f"---\n\n**AFTER (fine-tuned)**\n\n{generate(message, adapters_on=True)}"
        )

    return gr.ChatInterface(
        fn=respond,
        title="Loan Terms Assistant — Qwen2.5-1.5B fine-tuned with QLoRA",
        description=(
            "Answers questions about five real bank loan contracts with a document and page "
            "citation. Refuses off-topic questions and requests for advice. Says "
            "'Not stated in the terms.' when the contracts are silent."
            + ("\n\n**Comparison mode:** every answer is shown before and after training." if compare else "")
        ),
        examples=EXAMPLES,
    )


class _adapters:
    """Turn the adapters off for a single generation, so BEFORE and AFTER come from the
    identical weights - the only honest way to attribute a difference to training."""

    def __init__(self, model, enabled: bool):
        self.model, self.enabled = model, enabled
        self._ctx = None

    def __enter__(self):
        if not self.enabled:
            self._ctx = self.model.disable_adapter()
            self._ctx.__enter__()
        return self

    def __exit__(self, *exc):
        if self._ctx is not None:
            self._ctx.__exit__(*exc)
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default=ADAPTER_ID)
    ap.add_argument("--base", default=BASE_MODEL)
    ap.add_argument("--share", action="store_true", help="public link, ~72 hours")
    ap.add_argument("--compare", action="store_true", help="show BEFORE and AFTER together")
    ap.add_argument("--no-4bit", dest="four_bit", action="store_false")
    args = ap.parse_args()

    print(f"base    : {args.base}")
    print(f"adapter : {args.adapter}")
    model, tokenizer = load(args.adapter, args.base, args.four_bit)
    build(model, tokenizer, args.compare).launch(share=args.share)


if __name__ == "__main__":
    main()
