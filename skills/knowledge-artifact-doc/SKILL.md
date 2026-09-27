---
name: knowledge-artifact-doc
description: Create a paired markdown reference doc + HTML Mermaid sequence-diagram artifact documenting an implementation/execution flow, for quick future reference. Use when asked to document "how X works", create a "sequence flow diagram", or produce a learning/reference doc for a pipeline, service, or feature that's been built or changed.
---

# Knowledge Artifact Doc

Produces the reference-material pattern this project settled on after several iterations: one markdown doc (brief, commands, tables — searchable, copy-pasteable) paired with one HTML artifact (Mermaid sequence diagram — faster to read visually than prose), plus a standalone local copy of that diagram so it's viewable without the published artifact link. Codifies the Mermaid rendering pitfalls this project hit and fixed, so they aren't re-discovered from scratch next time.

## Step 1 — Scope & location

If not already given, ask what implementation/flow to document and where the output should live. Default to a `Reference/Learning/<topic>/` folder if the project has one; otherwise check for an existing precedent folder before inventing a new location.

## Step 2 — One trio, not one per request

A single `<topic>-reference.md` + single `<topic>-sequence-flow.html` + single `<topic>-sequence-flow-standalone.html` (or just `<topic>.html`/`.md`/`-standalone.html` if it's the folder's only topic), covering the *current* state of the code. When re-documenting after a change, **update the existing trio in place** — edit the markdown, edit and republish the artifact, edit the standalone copy to match — rather than creating a new dated/numbered file (`v2`, `02-...`). Numbered files accumulating over time is the exact anti-pattern that previously required a cleanup pass in this project. The standalone file is a genuinely separate file from the artifact HTML (see Step 6) — both need editing when a diagram changes, not just one.

## Step 3 — Markdown doc contents

Model on a working example if one exists in the repo already. Otherwise include, roughly in this order: one-paragraph brief, module/responsibility table, data model or key-entity quick reference, one-time environment setup, run commands (every mode the code supports), env var table, verification commands, troubleshooting table (symptom → cause → fix), links to related docs (specs, other reference docs). Skip sections that don't apply rather than leaving placeholders.

## Step 4 — HTML artifact: Mermaid mechanics

These are the specific bugs this project hit; avoid re-deriving them by trial and error.

- **Render natively**: `<pre class="mermaid">...</pre>`. Do **not** add `<div class="mermaid">` plus a manually loaded `mermaid.min.js` `<script>` — the artifact host already renders `<pre class="mermaid">` without any library load, and mixing in a manual one caused a real parsing bug here.
- **The native renderer parses raw, un-decoded text.** A literal `;` breaks parsing anywhere, including inside a `note`/label line — use `<br/>` for line breaks instead. HTML entities containing a semicolon (`&nbsp;`, `&lt;`, `&gt;`) break it too — write plain text instead (`run_id`, not `&lt;run_id&gt;`).
- **Set an explicit theme for contrast.** Mermaid's SVG output uses fixed colors from its theme, not `currentColor`, so the page's CSS cannot style diagram text or lines. Prepend every `sequenceDiagram` block with:
  ```
  %%{init: {'theme': 'base', 'themeVariables': {
    'primaryColor': '#dbeafe', 'primaryTextColor': '#0f172a', 'primaryBorderColor': '#1d4ed8',
    'lineColor': '#1e293b', 'actorBkg': '#dbeafe', 'actorBorderColor': '#1d4ed8', 'actorTextColor': '#0f172a',
    'actorLineColor': '#334155', 'signalColor': '#1e293b', 'signalTextColor': '#0f172a',
    'labelBoxBkgColor': '#fef3c7', 'labelBoxBorderColor': '#b45309', 'labelTextColor': '#0f172a',
    'loopTextColor': '#0f172a', 'noteBkgColor': '#fef9c3', 'noteTextColor': '#0f172a', 'noteBorderColor': '#a16207',
    'activationBorderColor': '#1d4ed8', 'activationBkgColor': '#dbeafe', 'sequenceNumberColor': '#0f172a'
  }}}%%
  ```
  (Dark text on light backgrounds. Swap the hex values if the page has its own palette, but keep the same high-contrast intent.)
- **Pin `pre.mermaid`'s background to a light color in both page themes** — `background: #f9f9f9` under plain `body` selectors *and* under `[data-theme="dark"]` (or the `prefers-color-scheme: dark` media query). The theme directive above assumes a light card behind the diagram; letting dark mode go near-black clashes with it.
- **Show real internal structure when it's part of what the reader needs.** If documenting an entry point whose internals matter (e.g. `main()` calling out to helper functions), draw those calls rather than collapsing the entry point into one opaque box.

## Step 5 — Verify before publishing (fast path by default)

Each `npx @mermaid-js/mermaid-cli` invocation launches headless Chromium — it's the slowest step in this whole skill by a wide margin (roughly as long as everything else combined when it's called 3-4 times). Don't pay that cost more than once per diagram.

- **Always do**: extract every `sequenceDiagram` block (including its `%%{init}%%` line) to a temp `.mmd` file and render each to SVG in **one Bash call** covering all diagrams:
  ```bash
  npx -y @mermaid-js/mermaid-cli -i diagram1.mmd -o diagram1.svg
  npx -y @mermaid-js/mermaid-cli -i diagram2.mmd -o diagram2.svg
  ```
  A clean exit + a non-trivial `<text>` count (`grep -o "<text" diagram.svg | wc -l`) confirms the syntax parses and something real got drawn. This is the check that actually catches the semicolon/entity bugs below — keep it, every time.
- **Skip by default**: rendering to PNG and eyeballing it with `Read`. That step exists to catch bad contrast, and it's already solved — the `%%{init}%%` block in Step 4 is a known-good, copy-pasted constant at this point. Re-rendering PNGs to re-confirm a theme that hasn't changed is paying the slowest step in the skill for zero new information.
- **Only render PNGs when** you've changed a color in the theme block, or something about a specific diagram's layout looks suspicious from the SVG's text count alone (e.g. far fewer `<text>` elements than the source has labels).

This alone roughly halves the verification cost for the common case (2 SVG renders instead of 2 SVG + 2 PNG).

## Step 6 — Publish the artifact, then build the standalone copy

Publish the artifact HTML via the `Artifact` tool (a favicon is required only on first publish; republishing the same file path updates it in place). Cross-link markdown ↔ artifact HTML from each other's top — e.g. an "also available as" line in the markdown, and a "view the full command reference" link in the HTML.

**The Mermaid diagram in the artifact-published file only renders at the published artifact URL, never by opening that `.html` file locally.** The `<pre class="mermaid">` native-rendering runtime is injected by the artifact hosting page itself when it serves that URL — it is not bundled into the file on disk. Opening that exact file directly (an IDE preview, `open file.html`, a Live Server extension, anything that isn't the `claude.ai/code/artifact/...` link) shows the raw `%%{init}%%`/`sequenceDiagram` source as plain text. **Do not try to fix this by adding a Mermaid `<script>` to that same file** — it already gets one injected at publish time, and a second one risks a real double-render conflict; this is exactly why the standalone copy below is a separate file.

Then write the standalone copy: take the artifact HTML's content (title, styles, all `<pre class="mermaid">` blocks, everything below the container) and wrap it in a complete document — `<!DOCTYPE html><html><head><meta charset="utf-8">...<title>...</title><style>...</style></head><body>...<script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js"></script><script>mermaid.initialize({startOnLoad:true});</script></body></html>` (the artifact-published file itself has none of these wrapper tags — that omission is what lets the artifact host wrap it safely). Verify the exact CDN version resolves (a `WebFetch` HEAD-equivalent check, or just fetch the URL) before relying on it — cdnjs doesn't mirror every version tag Claude's own injected runtime uses; `10.9.1` is confirmed working, checked at the time this skill was written. Name it `<topic>-sequence-flow-standalone.html` alongside the artifact-published `<topic>-sequence-flow.html`.

## Step 7 — Update the folder's index

If the target folder has an `INDEX.md`/`README.md`, update its entry for this trio (or add one) rather than letting it drift out of sync — a stale index describing files that no longer exist, or missing ones that do, is exactly the kind of context rot this pattern exists to prevent. List both the artifact URL and the standalone file, and say plainly which one to open directly (the standalone file) versus which one only renders via its published link (the artifact HTML).

This step and any cross-link edit into a governing spec (Step 6's "cross-link the two files" plus a pointer from the spec back to the learning folder) are independent writes to different files — fire them as parallel tool calls in one turn rather than one after another.
