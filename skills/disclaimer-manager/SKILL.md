---
name: disclaimer-manager
description: Ensure required legal/attribution disclaimers (dataset licenses, source-code license headers, third-party model terms) are present wherever they're required. Use when creating or editing README/docs, adding a new dataset or pretrained model, generating a public-facing "about" page, or when the user asks about a disclaimer/license/attribution requirement. Not for general licensing questions unrelated to this project's assets.
---

# Disclaimer Manager

One skill, many disclaimers. The logic is fixed — find the right template, check whether its required text is present at its required location, insert it if missing. Each disclaimer's actual wording and placement rules live in their own template file under `templates/`, so adding a new disclaimer (a new dataset, a chosen source-code license, a third-party pretrained model's terms) never requires a new skill — just a new template.

## How to use

1. Check `templates/` for a file matching the asset in question (dataset name, license type, model name).
2. Read the template's HTML comment header for `target` (which file(s) it belongs in) and `placement` (docs-only vs. per-file header vs. runtime/UI).
3. Check whether the target file(s) already contain that disclaimer. If missing, insert it verbatim at the placement described — don't paraphrase legal/citation text.
4. If no template exists yet for the asset in question, ask for the source of the required wording (dataset's bundled README/LICENSE, model card, etc.) before inventing one — never guess at legal text.

## Current templates

| Template | Covers | Placement |
|---|---|---|
| `deepfashion-dataset.md` | DeepFashion (Consumer-to-shop Retrieval Benchmark) dataset restriction + citation | `README.md`, `.agents/memory-bank/projectDocs.md` — docs only |

## Adding a new template

Create `templates/<asset-name>.md` with an HTML comment header (`target`, `placement`, `trigger`) followed by the exact required disclaimer text. Then add a row to the table above.
