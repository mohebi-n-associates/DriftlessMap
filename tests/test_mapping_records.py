import unittest

import numpy as np

from driftlessmap.mapping_records import (
    CURRENT,
    NOT_RECORDED,
    REGISTRATION_CHANGED,
    REMAPPED,
    OTHER_SECTION,
    MappingLedger,
    MappingRecord,
    derivation,
    derivation_status,
    is_identifier,
    new_identifier,
    valid_derivation,
)
from driftlessmap.transactions import TransactionHistory, pack, unpack

FIRST = "a" * 64
SECOND = "b" * 64


def cells(n=3):
    return {"points": np.arange(2 * n, dtype=float).reshape(n, 2),
            "size": [5.0] * n, "symbol": ["o"] * n, "layer_index": [0] * n}


class MappingLedgerTests(unittest.TestCase):
    def setUp(self):
        self.section = new_identifier()
        self.ledger = MappingLedger()

    def test_mapping_a_unit_again_replaces_it(self):
        first = self.ledger.record(self.section, "cells", cells(), FIRST, "reviewed", "t1")
        again = self.ledger.record(self.section, "cells", cells(4), SECOND, "not reviewed", "t2")
        self.assertEqual(len(self.ledger), 1)
        self.assertEqual(again.unit_id, first.unit_id)
        self.assertEqual((first.revision, again.revision), (1, 2))
        self.assertNotEqual(again.source_digest, first.source_digest)
        self.assertIs(self.ledger.by_unit(first.unit_id), again)

    def test_probes_sections_and_kinds_are_separate_units(self):
        other = new_identifier()
        track = {"points": [[1.0, 2.0], [3.0, 4.0]]}
        a = self.ledger.record(self.section, "probe", track, FIRST, "reviewed", "t", probe="A")
        b = self.ledger.record(self.section, "probe", track, FIRST, "reviewed", "t", probe="B")
        c = self.ledger.record(other, "probe", track, FIRST, "reviewed", "t", probe="A")
        d = self.ledger.record(self.section, "contour", track, FIRST, "reviewed", "t")
        self.assertEqual(len({a.unit_id, b.unit_id, c.unit_id, d.unit_id}), 4)
        self.assertIs(self.ledger.get(self.section, "probe", "A"), a)
        with self.assertRaises(ValueError):
            self.ledger.record(self.section, "cells", cells(), FIRST, "r", "t", probe="A")
        with self.assertRaises(ValueError):
            self.ledger.record("section-1", "cells", cells(), FIRST, "r", "t")

    def test_kept_marks_are_validated_and_copied(self):
        source = cells()
        record = self.ledger.record(self.section, "cells", source, FIRST, "r", "t")
        source["points"][0, 0] = 99
        self.assertEqual(record.source["points"][0, 0], 0)
        bad = cells()
        bad["size"] = [1.0]
        with self.assertRaises(ValueError):
            self.ledger.record(self.section, "cells", bad, FIRST, "r", "t")
        with self.assertRaises(ValueError):
            self.ledger.record(self.section, "probe", {"points": [[np.nan, 1.0]]}, FIRST, "r", "t")
        with self.assertRaises(ValueError):
            self.ledger.record(self.section, "expression", {"mask": np.zeros(0)}, FIRST, "r", "t")

    def test_status_follows_registration_and_section(self):
        record = self.ledger.record(self.section, "drawing",
                                    {"points": [[0, 0], [1, 1]], "closed": True},
                                    FIRST, "reviewed", "t")
        self.assertEqual(record.status(self.section, FIRST), CURRENT)
        self.assertEqual(record.status(self.section, SECOND), REGISTRATION_CHANGED)
        self.assertEqual(record.status(new_identifier(), FIRST), OTHER_SECTION)

    def test_restamp_changes_only_the_section_and_fingerprint_given(self):
        track = {"points": [[1.0, 2.0], [3.0, 4.0]]}
        here = self.ledger.record(self.section, "probe", track, FIRST, "r", "t", probe="A")
        other = self.ledger.record(new_identifier(), "probe", track, FIRST, "r", "t", probe="A")
        moved = self.ledger.record(self.section, "cells", cells(), SECOND, "r", "t")
        self.assertEqual(self.ledger.restamp(self.section, FIRST, "c" * 64), 1)
        renewed = self.ledger.by_unit(here.unit_id)
        self.assertEqual((renewed.registration, renewed.revision), ("c" * 64, here.revision))
        self.assertEqual(self.ledger.by_unit(other.unit_id).registration, FIRST)
        self.assertEqual(self.ledger.by_unit(moved.unit_id).registration, SECOND)

    def test_parts_are_out_of_date_when_their_unit_is_mapped_again(self):
        record = self.ledger.record(self.section, "cells", cells(), FIRST, "r", "t")
        entries = derivation([record])
        self.assertEqual(valid_derivation(entries), entries)
        self.assertEqual(derivation_status(entries, self.ledger, self.section, FIRST), CURRENT)
        self.assertEqual(derivation_status(entries, self.ledger, self.section, SECOND),
                         REGISTRATION_CHANGED)
        # A part from a section that is no longer loaded stays current.
        self.assertEqual(derivation_status(entries, self.ledger, new_identifier(), SECOND),
                         CURRENT)
        self.ledger.record(self.section, "cells", cells(5), FIRST, "r", "t2")
        self.assertEqual(derivation_status(entries, self.ledger, self.section, FIRST), REMAPPED)
        self.assertEqual(derivation_status([], self.ledger, self.section, FIRST), NOT_RECORDED)
        self.ledger.forget(record.unit_id)
        self.assertEqual(derivation_status(entries, self.ledger, self.section, FIRST),
                         NOT_RECORDED)
        for bad in (None, "x", [["x", 1]], [[record.unit_id, 0]], [[record.unit_id, True]]):
            self.assertEqual(valid_derivation(bad), [], bad)

    def test_round_trip_and_damaged_records(self):
        mask = np.zeros((40, 50), dtype=np.uint8)
        mask[3:6, 4:9] = 1
        self.ledger.record(self.section, "expression", {"mask": mask}, FIRST, "reviewed", "t")
        self.ledger.record(self.section, "probe", {"points": [[1, 2], [3, 4]]}, SECOND,
                           "not reviewed", "t", probe="A")
        saved = self.ledger.to_list()
        restored, problems = MappingLedger.from_list(saved)
        self.assertEqual(problems, [])
        self.assertEqual({r.unit_id for r in restored.records()},
                         {r.unit_id for r in self.ledger.records()})
        np.testing.assert_array_equal(
            restored.get(self.section, "expression").source["mask"], mask)

        tampered = [dict(item) for item in saved]
        tampered[0]["source"] = {"mask": np.ones((40, 50), dtype=np.uint8)}
        tampered[1]["unit_id"] = "not-an-id"
        restored, problems = MappingLedger.from_list(tampered + ["junk"])
        self.assertEqual(len(restored), 0)
        self.assertEqual(len(problems), 3)
        self.assertEqual(MappingLedger.from_list(None)[1], [])
        self.assertTrue(MappingLedger.from_list({"a": 1})[1])

    def test_snapshot_is_independent(self):
        self.ledger.record(self.section, "cells", cells(), FIRST, "r", "t")
        snapshot = self.ledger.snapshot()
        self.ledger.record(self.section, "cells", cells(6), SECOND, "r", "t2")
        self.assertEqual(snapshot.get(self.section, "cells").revision, 1)
        self.assertTrue(is_identifier(new_identifier()))
        self.assertFalse(is_identifier("A" * 32))
        with self.assertRaises(ValueError):
            MappingRecord.from_dict(dict(self.ledger.to_list()[0], revision=0))


class TransactionHistoryTests(unittest.TestCase):
    def test_undo_and_redo_never_keep_an_oversized_inverse(self):
        history = TransactionHistory(budget_bytes=1000)
        history.commit(history.prepare("small", np.zeros(10, dtype=np.uint8)))
        restored = history.undo(np.arange(10000, dtype=np.uint8))
        self.assertEqual(restored.shape, (10,))
        self.assertLessEqual(history._used(), history.budget_bytes)
        self.assertIsNone(history.redo_label())
        history.commit(history.prepare("small", np.zeros(10, dtype=np.uint8)))
        history.undo(np.ones(10, dtype=np.uint8))
        self.assertEqual(history.redo(np.arange(10000, dtype=np.uint8)).shape, (10,))
        self.assertLessEqual(history._used(), history.budget_bytes)
        self.assertIsNone(history.undo_label())

    def test_undo_and_redo_restore_whole_states(self):
        history = TransactionHistory()
        state = {"cells": [[1.0, 2.0]], "parts": ["cells - piece"]}
        history.commit(history.prepare("Map cells", state))
        self.assertEqual(history.undo_label(), "Map cells")
        after = {"cells": [], "parts": ["cells - piece", "cells - piece"]}
        restored = history.undo(after)
        self.assertEqual(restored, state)
        self.assertIsNone(history.undo_label())
        self.assertEqual(history.redo_label(), "Map cells")
        self.assertEqual(history.redo(restored), after)
        self.assertIsNone(TransactionHistory().undo({}))
        self.assertIsNone(TransactionHistory().redo({}))

    def test_a_new_action_clears_redo(self):
        history = TransactionHistory()
        history.commit(history.prepare("Map cells", {"a": 1}))
        history.undo({"a": 2})
        history.commit(history.prepare("Build probe A", {"a": 3}))
        self.assertIsNone(history.redo_label())
        self.assertEqual(history.undo_label(), "Build probe A")

    def test_steps_and_budget_bound_the_history(self):
        history = TransactionHistory(max_steps=3)
        for index in range(5):
            history.commit(history.prepare("step {}".format(index), {"i": index}))
        labels = []
        while history.undo_label():
            labels.append(history.undo_label())
            history.undo({})
        self.assertEqual(labels, ["step 4", "step 3", "step 2"])

        noise = np.random.default_rng(0).integers(0, 255, 400_000, dtype=np.uint8)
        small = TransactionHistory(budget_bytes=1_000_000)
        self.assertIsNone(small.prepare("too large", {"mask": np.concatenate([noise] * 3)}))
        small.commit(small.prepare("first", {"mask": noise}))
        small.commit(small.prepare("second", {"mask": noise}))
        small.commit(small.prepare("third", {"mask": noise}))
        self.assertEqual(small.undo_label(), "third")
        small.undo({})
        self.assertEqual(small.undo_label(), "second")
        small.undo({})
        self.assertIsNone(small.undo_label())

    def test_empty_masks_are_stored_compressed_and_exactly(self):
        mask = np.zeros((4000, 3000), dtype=np.uint8)
        mask[100:200, 300:400] = 255
        packed, size = pack({"mask": mask, "points": [[1.0, 2.0]]})
        self.assertLess(size, mask.nbytes // 50)
        restored = unpack(packed)
        np.testing.assert_array_equal(restored["mask"], mask)
        self.assertEqual(restored["points"], [[1.0, 2.0]])


if __name__ == "__main__":
    unittest.main()
