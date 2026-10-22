"""Synthetic package/CLI checks; no real document data or external services."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'check_docx_residue.py'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def document(body='', declaration=''):
    return declaration + f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'


class TestResidueCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'synthetic.docx'

    def package(self, parts=None):
        with zipfile.ZipFile(self.path, 'w') as z:
            for name, value in (parts or {'word/document.xml': document()}).items():
                z.writestr(name, value)

    def run_check(self, expected, approved=None):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        command = [sys.executable, '-B', str(SCRIPT), str(self.path)]
        if approved is not None:
            settings = Path(self.temp.name) / 'approved.json'
            settings.write_text(json.dumps(approved))
            command += ['--approved-metadata', str(settings)]
        result = subprocess.run(command, cwd=self.temp.name, text=True,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        self.assertEqual(result.stderr, '')
        data = json.loads(result.stdout)
        self.assertEqual(data['status'], {0: 'NO_LISTED_RESIDUE', 1: 'REVIEW',
                                         2: 'UNVERIFIED'}[expected])
        return data, result.stdout

    def test_clean_and_plain_utf16_are_read_without_mutation(self):
        for encoding in ('utf-8', 'utf-16', 'utf-16-le', 'utf-16-be'):
            with self.subTest(encoding=encoding):
                declaration = '<?xml version="1.0" encoding="' + (
                    'UTF-8' if encoding == 'utf-8' else 'UTF-16') + '"?>'
                self.package({'word/document.xml': document(declaration=declaration).encode(encoding)})
                self.run_check(0)

    def test_metadata_value_is_not_disclosed(self):
        self.package({'word/document.xml': document(), 'docProps/core.xml':
                      '<p xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>VALUE_MUST_STAY_PRIVATE</dc:creator></p>'})
        data, output = self.run_check(1)
        self.assertNotIn('VALUE_MUST_STAY_PRIVATE', output)
        self.assertEqual(data['findings'][0]['property'], 'creator')

    def test_exact_metadata_exception_and_mismatch(self):
        self.package({'word/document.xml': document(), 'docProps/core.xml':
                      '<p><creator>Example Author</creator></p>'})
        self.run_check(0, {'docProps/core.xml:creator': 'Example Author'})
        self.run_check(1, {'docProps/core.xml:creator': 'example author'})

    def test_metadata_exception_does_not_waive_comment_or_revision(self):
        self.package({'word/document.xml': document('<w:ins/><w:commentReference w:id="1"/>'),
                      'docProps/core.xml': '<p><creator>Example Author</creator></p>'})
        data, _ = self.run_check(1, {'docProps/core.xml:creator': 'Example Author'})
        self.assertEqual({x['kind'] for x in data['findings']}, {'tracked_revision', 'comment_anchor'})

    def test_comment_part_is_reported_without_body_anchor(self):
        self.package({'word/document.xml': document(), 'word/comments.xml': f'<w:comments xmlns:w="{W}"/>'})
        data, _ = self.run_check(1)
        self.assertIn('comment_part', {x['kind'] for x in data['findings']})

    def test_footer_revision_and_style_hidden_setting(self):
        self.package({'word/document.xml': document(),
                      'word/footer1.xml': f'<w:ftr xmlns:w="{W}"><w:del/></w:ftr>',
                      'word/styles.xml': f'<w:styles xmlns:w="{W}"><w:vanish/></w:styles>'})
        data, _ = self.run_check(1)
        self.assertEqual({x['part'] for x in data['findings']}, {'word/footer1.xml', 'word/styles.xml'})

    def test_disabled_hidden_and_tracking_settings_are_not_findings(self):
        self.package({'word/document.xml': document('<w:vanish w:val="off"/><w:webHidden w:val="0"/>'),
                      'word/settings.xml': f'<w:settings xmlns:w="{W}"><w:trackRevisions w:val="false"/></w:settings>'})
        self.run_check(0)

    def test_enabled_tracking_is_reported(self):
        self.package({'word/document.xml': document(),
                      'word/settings.xml': f'<w:settings xmlns:w="{W}"><w:trackRevisions/></w:settings>'})
        data, _ = self.run_check(1)
        self.assertEqual(data['findings'][0]['kind'], 'tracking_enabled')

    def test_embedded_and_custom_content_require_review(self):
        self.package({'word/document.xml': document(), 'word/embeddings/object.bin': b'fixture',
                      'customXml/item1.xml': '<fixture/>'})
        data, _ = self.run_check(1)
        self.assertEqual(len(data['findings']), 2)

    def test_custom_property_exact_exception(self):
        self.package({'word/document.xml': document(), 'docProps/custom.xml':
                      '<Properties><property name="Label"><value>Example</value></property></Properties>'})
        self.run_check(1)
        self.run_check(0, {'docProps/custom.xml:Label': 'Example'})

    def test_malformed_xml(self):
        self.package({'word/document.xml': '<broken'})
        self.run_check(2)

    def test_missing_document(self):
        self.package({'docProps/core.xml': '<p/>'})
        self.run_check(2)

    def test_unsupported_document_namespace(self):
        self.package({'word/document.xml': '<document/>'})
        self.run_check(2)

    def test_bad_zip(self):
        self.path.write_bytes(b'not a package')
        self.run_check(2)

    def test_duplicate_parts(self):
        self.package()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.path, 'a') as z:
                z.writestr('word/document.xml', document())
        self.run_check(2)

    def test_dtd_rejected_after_encoding_decode(self):
        for encoding in ('utf-8', 'utf-16', 'utf-16-le', 'utf-16-be'):
            with self.subTest(encoding=encoding):
                decl = '<?xml version="1.0" encoding="' + (
                    'UTF-8' if encoding == 'utf-8' else 'UTF-16') + '"?>'
                decl += '<!DOCTYPE document [<!ENTITY x "example">]>'
                self.package({'word/document.xml': document('<w:t>&x;</w:t>', decl).encode(encoding)})
                self.run_check(2)

    def test_invalid_approval_shape(self):
        self.package()
        self.run_check(2, {'docProps/core.xml:creator': 42})

    def test_external_relationship_is_an_explicit_scope_limit(self):
        self.package({'word/document.xml': document(), 'word/_rels/document.xml.rels':
                      '<Relationships><Relationship Type="attachedTemplate" Target="https://example.invalid/template" TargetMode="External"/></Relationships>'})
        self.run_check(0)


if __name__ == '__main__':
    unittest.main()
