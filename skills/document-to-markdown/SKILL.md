---
name: document-to-markdown
description: Convert various document formats (PDF, DOCX, TXT, LOG) into clean Markdown (.md) files for better readability by AI agents.
---

# Document to Markdown Converter Skill

This skill provides a programmatic utility to convert unstructured files like PDFs, Word Documents, and raw text logs into clean, structured Markdown (.md) files. This drastically improves the context retention and readability for AI agents and LLMs.

## How to Run the Converter

Invoke the Python converter script using the workspace Python interpreter:

```bash
python .agents/skills/document-to-markdown/scripts/convert_doc.py <input_file_path> [output_file_path]
```

* If `output_file_path` is not provided, it will automatically save a `.md` file with the same name in the same directory as the input file.

## Supported Formats
* **PDF (`.pdf`)**: Extracts text page-by-page, adds page headers, and formats it cleanly.
* **Word (`.docx`)**: Extracts paragraphs, lists, and headings, preserving basic layout.
* **Text (`.txt`, `.log`, `.rtf`, `.ini`, `.cfg`)**: Converts plain text to Markdown blocks.
