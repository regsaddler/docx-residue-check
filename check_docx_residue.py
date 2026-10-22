#!/usr/bin/env python3
"""Read-only DOCX review-residue check. Uses only the Python standard library.

Exit 0: no listed residue detected; 1: review findings; 2: cannot inspect.
Does not certify factual accuracy, appearance, all privacy, or PDF contents.
Metadata values stay out of stdout. An optional task-local JSON object maps
part:property keys to exact intentionally retained values after review.
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
SENSITIVE = {
    'docProps/core.xml': {'creator', 'lastModifiedBy', 'title', 'subject',
                          'description', 'keywords', 'category', 'contentStatus'},
    'docProps/app.xml': {'Company', 'Manager', 'HyperlinkBase', 'Template'},
}
REVISIONS = {'ins', 'del', 'moveFrom', 'moveTo', 'cellIns', 'cellDel', 'cellMerge',
             'moveFromRangeStart', 'moveFromRangeEnd', 'moveToRangeStart', 'moveToRangeEnd'}
FALSE = {'0', 'false', 'off'}


class _NoDTDTreeBuilder(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        # The parser recognizes declarations after decoding UTF-8/UTF-16.
        # A byte-pattern check alone misses declarations in UTF-16 parts.
        raise ValueError('Unsupported XML document type declaration')


def inspect(path, approved=None):
    approved = {} if approved is None else approved
    if not isinstance(approved, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                for k, v in approved.items()):
        raise ValueError('Approved metadata must map property keys to exact string values')
    findings = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate package part names')
        if 'word/document.xml' not in names:
            raise ValueError('Missing Word document part')
        for name in names:
            lower = name.lower()
            if lower.startswith('word/comments'):
                findings.append({'part': name, 'kind': 'comment_part'})
            if lower.startswith(('word/embeddings/', 'customxml/')) or 'vbaproject' in lower:
                findings.append({'part': name, 'kind': 'additional_content_requires_review'})
            if not name.endswith('.xml') or not name.startswith(('word/', 'docProps/')):
                continue
            data = z.read(name)
            # Do not expand document-supplied entities in this inspection helper.
            if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
                raise ValueError(f'Unsupported XML declaration in {name}')
            root = ET.fromstring(data, parser=ET.XMLParser(target=_NoDTDTreeBuilder()))
            if name == 'word/document.xml' and root.tag != '{' + W + '}document':
                raise ValueError('Unsupported WordprocessingML namespace or document root')
            if name in SENSITIVE:
                for element in root:
                    prop = element.tag.split('}')[-1]
                    value = element.text or ''
                    key = name + ':' + prop
                    if prop in SENSITIVE[name] and value.strip() and approved.get(key) != value:
                        findings.append({'part': name, 'kind': 'metadata_review', 'property': prop})
            if name == 'docProps/custom.xml':
                for element in root:
                    prop = element.get('name', '')
                    key = name + ':' + prop
                    value = ''.join(element.itertext())
                    if not prop or approved.get(key) != value:
                        findings.append({'part': name, 'kind': 'custom_metadata_review', 'property': prop})
            if name.startswith('word/'):
                for element in root.iter():
                    if not element.tag.startswith('{' + W + '}'):
                        continue
                    tag = element.tag.split('}')[-1]
                    enabled = element.get('{' + W + '}val', 'true').lower() not in FALSE
                    kind = None
                    if tag in REVISIONS or tag.endswith('PrChange'):
                        kind = 'tracked_revision'
                    elif tag in {'vanish', 'webHidden', 'specVanish'} and enabled:
                        kind = 'hidden_text_setting'
                    elif tag == 'trackRevisions' and enabled:
                        kind = 'tracking_enabled'
                    elif tag in {'commentRangeStart', 'commentRangeEnd', 'commentReference'}:
                        kind = 'comment_anchor'
                    if kind:
                        findings.append({'part': name, 'kind': kind, 'element': tag})
    # Repeated markers add no decision value. Preserve package location.
    findings = list({json.dumps(f, sort_keys=True): f for f in findings}.values())
    return {'status': 'REVIEW' if findings else 'NO_LISTED_RESIDUE', 'findings': findings,
            'limits': 'No content, layout, placeholder, comprehensive privacy, or PDF certification'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('docx', type=Path)
    ap.add_argument('--approved-metadata', type=Path)
    args = ap.parse_args()
    try:
        approved = json.loads(args.approved_metadata.read_text()) if args.approved_metadata else None
        result = inspect(args.docx, approved)
    except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError, RuntimeError) as exc:
        print(json.dumps({'status': 'UNVERIFIED', 'error': type(exc).__name__}))
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result['findings'] else 0


if __name__ == '__main__':
    sys.exit(main())
