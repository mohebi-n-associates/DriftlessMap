import tempfile
import unittest
from types import SimpleNamespace

from driftlessmap.document_state import DocumentState
from driftlessmap.export_workflow import export_all_results


class ExportWorkflowTests(unittest.TestCase):
    def test_project_copy_and_sections_are_exported_without_widgets(self):
        calls = []

        def save(**kwargs):
            calls.append(kwargs)
            return True

        engine = SimpleNamespace(
            document=DocumentState(), current_project_path=None,
            flush_plan_edits=lambda: calls.append('flush'), save_project_called=save,
            out_of_date_lines=lambda rows: [], unverified_lines=lambda rows: [],
            implants=SimpleNamespace(implants=lambda: []), probe_plans=[],
            export_sections=lambda folder: (['section.tif'], []),
            layer_ctrl=SimpleNamespace(layer_link=[]))
        with tempfile.TemporaryDirectory() as folder:
            paths, notes = export_all_results(engine, folder)
        self.assertEqual(calls[0], 'flush')
        self.assertTrue(calls[1]['as_copy'])
        self.assertEqual(paths[-1], 'section.tif')
        self.assertEqual(notes, [])
