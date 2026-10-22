# DOCX residue check

Find listed review residue in a local Word document before sharing it: comments,
tracked changes, hidden-text settings and metadata that needs a second look.

The checker reads the DOCX package and prints JSON. It does not modify the file
or send its contents over a network. It uses the Python standard library.

## Run it

Keep `check_docx_residue.py` in any local directory and run:

```sh
python3 check_docx_residue.py /path/to/document.docx
```

No installation or API key is required. This candidate is tested with Python 3.14.7
and 3.14.8.

| Exit code | Status | Meaning |
|---|---|---|
| `0` | `NO_LISTED_RESIDUE` | None of the checks below found review residue. |
| `1` | `REVIEW` | Inspect the listed document parts before sharing. |
| `2` | `UNVERIFIED` | The file could not be inspected. Do not treat this as a clean result. |

For example, a creator property that needs review produces a finding like:

```json
{
  "part": "docProps/core.xml",
  "kind": "metadata_review",
  "property": "creator"
}
```

Metadata values and body text are omitted from findings. Package-part names and
property names are printed; those names can themselves reveal information.

## What it checks

- Listed core and application metadata, plus custom properties.
- Comment parts and comment anchors.
- Tracked insertions, deletions, moves, table-cell revisions and property changes.
- Enabled hidden-text settings and change tracking.
- Embedded content, custom XML and Visual Basic for Applications (VBA) project
  part names that need review.

Malformed ZIP/XML, duplicate package-part names, a missing main document, an
unsupported main-document namespace and document type declarations in inspected
XML parts produce an unverified result.

## Intentionally retained metadata

After reviewing a specific property, an optional JSON file can allow its exact
value. For example:

```json
{
  "docProps/core.xml:creator": "Example Author"
}
```

```sh
python3 check_docx_residue.py document.docx --approved-metadata approved.json
```

An exception applies only to that property/value pair. It cannot dismiss comments,
tracked revisions or other finding types. Store exception files privately when
they contain personal or organizational metadata.

## Scope

`NO_LISTED_RESIDUE` is a limited inspection result, not permission to publish.
The checker does not assess body meaning, placeholders, visual appearance, all
private fields, external relationships, PDFs or compatibility with Word and
applicant tracking systems.

Before sharing, work on a copy of the document. Review its content in Word, use
Document Inspector where available, remove unwanted findings, then reinspect and
review the final saved copy. Microsoft recommends using a copy because removed
information may not be recoverable. Even Word's Hidden Text inspector misses
white text on a white background; a negative inspection result cannot establish
that all confidential content is absent. See
[Microsoft's hidden-information guidance](https://support.microsoft.com/en-us/office/collab-files/remove-hidden-data-and-personal-information-by-inspecting-documents-presentations-or-workbooks).

Word for Mac does not include Document Inspector. Its manual property editor
does not provide the same inspection coverage; do not treat property review as
a complete substitute. See [Microsoft's platform guidance](https://support.microsoft.com/en-us/office/inspect-document-b0088a7a-d482-4b87-b762-7c94c7c71e23).

ZIP/XML memory and time limits are not enforced. This is a local review helper
for documents you choose to inspect, not a hardened upload-processing service.

## Tests

```sh
python3 -B -m unittest discover -s tests -v
```

Tests create synthetic ZIP/XML packages in temporary directories. They cover
findings, exact metadata exceptions, malformed inputs, declaration rejection in
UTF-8 and UTF-16, exit statuses and preservation of input bytes. No real documents
or personal histories are included. These fixtures test inspection behavior;
they do not establish rendering compatibility with Word.
