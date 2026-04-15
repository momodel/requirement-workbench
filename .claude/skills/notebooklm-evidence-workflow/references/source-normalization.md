# Source Normalization

## XLSX

Do not treat `.xlsx` as a native NotebookLM source in this project.

First extract:

- workbook and sheet names
- table headers
- representative sample rows
- row and column counts
- obvious business terms, code fields, and amount columns

Then generate a markdown or text summary that NotebookLM can read.

## 飞书纪要

Supported first-release paths:

- pasted transcript text
- exported DOCX
- exported PDF
- exported markdown or text

If the source is not already in a NotebookLM-friendly format, normalize it to text first.

## General Rule

If meaning depends on structure more than prose, preserve the structure in markdown rather than flattening everything into a paragraph.
