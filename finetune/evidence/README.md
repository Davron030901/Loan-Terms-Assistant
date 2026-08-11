# Evidence

Save the submission screenshots here.

| File | What it must show |
|---|---|
| `01_before_after_table.png` | The BEFORE vs AFTER table from notebook step 8 — at least an answerable question, an off-topic one, and one not in the documents |
| `02_behaviour_score.png` | The held-out score, base → tuned, broken down by behaviour |
| `03_training_loss.png` | The training log — proof the fine-tune ran and finished on Colab |
| `04_gradio_demo.png` | The live demo answering a question, citation visible |
| `05_refusal_live.png` | The demo refusing "Write me a poem about the moon." |
| `06_not_stated_live.png` | The demo answering "Not stated in the terms." |

`before_after.md` is written here automatically by `scripts/before_after.py`.

## A note on the screenshots

Take them **after** training finishes in the same session. The BEFORE column has to come
from `model.disable_adapter()` on the same loaded weights — a screenshot of a separate
base-model run does not prove the difference came from your training.
