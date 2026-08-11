# Fine-Tuning a Loan Terms Assistant with QLoRA

Teach a 1.5B open model three habits: **cite the contract**, **refuse what isn't its job**,
and **admit when the documents are silent**. Trained on a free Colab T4.

| | |
|---|---|
| **Base model** | `Qwen/Qwen2.5-1.5B-Instruct` |
| **Method** | QLoRA — 4-bit frozen base, LoRA adapters in fp16 |
| **Dataset** | 88 train / 18 held-out, built from 5 real bank PDFs, every citation verified |
| **Hardware** | Free Colab T4 · ~15 min training |
| **Demo** | Gradio `share=True` |

---

## What's here

```
finetune/
├─ data/
│  ├─ docs/                     the 5 real bank PDFs (the source of truth)
│  ├─ train_original.jsonl      what we were given (43 rows)
│  ├─ eval_original.jsonl       what we were given (8 rows)
│  ├─ train.jsonl               ← built · 88 rows
│  └─ eval.jsonl                ← built · 18 rows, all three behaviours
├─ scripts/
│  ├─ build_dataset.py          repair citations, grow behaviours, split
│  ├─ verify_dataset.py         every citation checked against the real page
│  └─ before_after.py           scores base vs tuned on the held-out set
├─ notebooks/
│  └─ finetune_qlora.ipynb      the Colab notebook — this is the deliverable
├─ app/
│  └─ gradio_demo.py            standalone demo, with a BEFORE/AFTER mode
└─ evidence/                    screenshots and generated results go here
```

---

## The dataset, and what was wrong with the starting one

The provided `train.jsonl` was usable, but auditing it against the PDFs turned up three
problems worth fixing before training on it. **A fine-tuned model copies the habits in its
data** — train on wrong citations and you get a model that cites confidently and wrongly,
which is worse than one that doesn't cite at all.

### 1 · Two citations pointed at the table of contents

```
row 22  "What happens if I fail to meet the obligations…"   cited p.2
row 32  "What happens if a clause is unenforceable…"        cited p.2
```

Page 2 of the CIBC document is the contents list. A line like `Severability .......`
matches all the topic words while containing none of the rule:

| | |
|---|---|
| **p.2** | `Severability .......` ← the contents entry |
| **p.10** | *"If any part of this Agreement is determined by any court of competent jurisdiction to be illegal, unenforceable or invalid, that part will be severed…"* ← the clause |

Repaired to p.9 and p.10, both confirmed by reading the clause. `verify_dataset.py` now
detects contents pages (five or more dotted leader runs) and rejects them outright.

### 2 · Seven behavioural examples is not a behaviour

The starting file taught *refuse* from 4 rows and *not stated* from 3. A model learns a
rule from a pattern, not from three instances. Grown to **39 refusals** and **22
not-stated**, spanning:

- creative writing, general knowledge, maths, code
- advice and opinion — *"should I", "is this a good rate", "would you sign this"*
- other banks and other products
- prompt injection — *"ignore all previous instructions", "pretend the late fee is $500"*
- bulk transformation — *"translate the whole contract"*
- the same categories again in Uzbek

**The distinction that matters most:** an off-topic question gets *refused*; a question
that is genuinely about loan terms but absent from these five contracts gets *"Not stated
in the terms."* Confusing those two is the classic failure of a scoped assistant, so the
data teaches them separately and the eval measures them separately.

Every refusal uses **one exact string**, never paraphrased. Teach three wordings and the
model learns three wordings; teach one and it learns a rule.

### 3 · The eval set couldn't measure the graded behaviour

`eval_original.jsonl` was 8 rows, all "answered" — so it could not test refusal or
not-stated at all, which is 15 of the 100 marks. The new `eval.jsonl` holds out **9
answered / 5 refusal / 4 not-stated**, stratified, never seen in training.

### Verification

```bash
python scripts/build_dataset.py     # repair + augment + split
python scripts/verify_dataset.py    # exit 0 only if every citation is real
```

```
train.jsonl: 88 rows   answered=35  not_stated=19  refusal=34
  citations verified against the page: 35/35
eval.jsonl:  18 rows   answered=9   not_stated=4   refusal=5
  citations verified against the page: 9/9

Every citation points at a page that really contains the clause. ✅
```

**Word overlap is a screening tool, not a verdict.** It flagged one row where the CIBC
"dispute" definition scored 53 % on its own page while a governing-law sentence elsewhere
scored 60 %. Reading page 12 settled it — the definition and its exclusions are there. That
judgement is recorded in `VERIFIED_BY_HAND` with the reason, rather than lowering the
threshold, which would have silenced real problems along with that one.

---

## Running the fine-tune

1. Open `notebooks/finetune_qlora.ipynb` in [Google Colab](https://colab.research.google.com/)
2. **Runtime → Change runtime type → T4 GPU** (nothing works without this)
3. Upload `data/train.jsonl` and `data/eval.jsonl`
4. Run every cell top to bottom

### The settings, and why

| Setting | Value | Reason |
|---|---|---|
| `bnb_4bit_compute_dtype` | `float16` | A T4 is Turing — it has **no bf16**. Copying a bf16 config from a newer-GPU tutorial is the most common way this dies on step 1. |
| `bnb_4bit_quant_type` | `nf4` | Beats plain int4 for normally-distributed weights |
| `bnb_4bit_use_double_quant` | `True` | Quantises the quantisation constants; ~0.4 GB back |
| LoRA `r` / `alpha` | 16 / 32 | Teaching a *format*, not adding knowledge — small is plenty |
| `target_modules` | attention **+ MLP** | Attention-only is cheaper but adapts format less reliably |
| `learning_rate` | 2e-4 | LoRA tolerates ~10× a full fine-tune's rate |
| `num_train_epochs` | 3 | 88 rows needs several passes; more and it memorises the questions |
| `optim` | `paged_adamw_8bit` | Paged: survives a memory spike instead of crashing |
| `gradient_checkpointing` | `True` | Recompute activations — slower, much less memory |
| `padding_side` | `right` | Left padding corrupts causal-LM targets |
| `do_sample` | `False` | Greedy, so the BEFORE/AFTER table reproduces exactly |

**If it runs out of memory,** read only the first red line. `batch_size` → 1, then
`max_seq_length` → 768. **If it says "cannot import" or "unexpected keyword",** that's a
library version, not your code: Runtime → Restart session, run from the top.

---

## BEFORE vs AFTER

Both columns come from the **same loaded weights** — the BEFORE pass simply switches the
adapters off with `model.disable_adapter()`. Loading a second copy of the base model would
let a different download or dtype take the credit for the difference.

Beyond the screenshot, `scripts/before_after.py` scores both on the 18 held-out rows and
reports behaviour accuracy per category plus how many answers carried a citation. A
screenshot shows *that* it changed; the score shows *whether it changed correctly*.

---

## Fine-tuning vs RAG

**Fine-tuning changes the model. RAG changes the model's input.**

Fine-tuning adjusts weights so the model has different *habits* — here, to cite in a fixed
shape, to refuse in one exact sentence, to say "Not stated in the terms." rather than
improvise. Those habits are baked in and cost nothing at inference: no database, no search,
no extra latency. But the model has no lookup of the documents. It has absorbed their
*style*, not their *contents*, and it will happily produce a citation that is well-formed
and wrong — because at inference time nothing checks it.

RAG leaves the weights untouched and does the work at question time: search the documents,
paste the matching clauses into the prompt, and instruct the model to answer only from
them. The citation can be verified against what was actually retrieved, and swapping a PDF
means re-indexing, not re-training. The cost is a retrieval stack on the critical path, and
an answer that is only as good as the search that fed it.

**The honest summary: fine-tuning teaches behaviour, retrieval supplies facts.** They fix
different problems and the interesting systems use both — a fine-tuned model that reliably
refuses and cites, answering over clauses that retrieval just fetched and can prove. For a
document that states an interest rate, I would not ship fine-tuning alone: a wrong number
stated confidently is exactly the failure that matters, and only retrieval plus a
verification step can rule it out.

*(Write this in your own words for submission — a marker can tell.)*

---

## Submission checklist

- [ ] `data/train.jsonl` — 88 rows, built from the real PDFs
- [ ] `notebooks/finetune_qlora.ipynb` — outputs left visible
- [ ] Screenshot: **BEFORE vs AFTER** table, at least 3 questions
      (one answerable, one off-topic, one not-in-docs)
- [ ] Screenshot: behaviour score, base → tuned
- [ ] The public Gradio link (or a short screen recording)
- [ ] Your paragraph on fine-tuning vs RAG

Save screenshots into `evidence/`.

### Where the marks are

| Checked | Points | Where |
|---|---:|---|
| Dataset from the real PDFs, grounded, with refusal & not-stated | 25 | `data/train.jsonl` · `scripts/verify_dataset.py` proves every citation |
| QLoRA fine-tune runs and finishes on free Colab | 20 | `notebooks/finetune_qlora.ipynb`, T4-safe throughout |
| Clear BEFORE vs AFTER | 20 | notebook step 8 · `scripts/before_after.py` |
| Tuned model behaves correctly | 15 | held-out score across all three behaviours |
| Live demo link | 10 | notebook step 10 · `app/gradio_demo.py` |
| Can explain fine-tuning vs RAG | 10 | above — rewrite in your own words |

---

## Limitations, stated plainly

- **The model does not look anything up.** It has learned the *shape* of a citation, not a
  mapping from claim to page. It can produce `(cibc_personal_loan.pdf, p.7)` for a clause
  on page 9, and nothing at inference time will catch that.
- **88 rows is a small dataset.** Enough to install a behaviour, not enough to cover five
  contracts thoroughly. Expect confident answers on topics the training set touched and
  weaker ones elsewhere.
- **Uzbek is under-represented** — one document of five. The behaviour transfers; the
  fluency is thinner.
- **A 1.5B model is small.** It was chosen to fit a free T4. Behaviour is what we are
  teaching, and behaviour is learnable at this size; nuanced legal reasoning is not.
- **Not financial or legal advice.** It quotes a contract. Read the original.
