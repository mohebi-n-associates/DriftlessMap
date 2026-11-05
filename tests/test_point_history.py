"""Point edits keep their own cheap history, ordered with mapping steps (2.9.3)."""

import unittest

from driftlessmap.transactions import PointHistory, TransactionHistory


class PointHistoryTests(unittest.TestCase):
    def test_undo_and_redo_swap_states_and_keep_copies(self):
        history = PointHistory()
        before = {"img": {"img-probe": [[1.0, 2.0]]}}
        history.record(1, "Mark probe point", before)
        before["img"]["img-probe"].append([9.0, 9.0])     # later edits cannot reach it
        current = {"img": {"img-probe": [[1.0, 2.0], [3.0, 4.0]]}}
        self.assertEqual(history.undo(current), {"img": {"img-probe": [[1.0, 2.0]]}})
        self.assertEqual(history.redo_step().seq, 1)
        self.assertEqual(history.redo({"img": {"img-probe": [[1.0, 2.0]]}}), current)
        self.assertIsNone(history.redo_step())

    def test_a_new_step_ends_redo_and_the_oldest_steps_go_first(self):
        history = PointHistory(max_steps=3)
        for seq in range(1, 5):
            history.record(seq, "step {}".format(seq), {"n": seq})
        self.assertEqual([s.seq for s in history._undo], [2, 3, 4])
        history.undo({"n": 5})
        history.record(6, "step 6", {"n": 4})
        self.assertIsNone(history.redo_step())

    def test_steps_older_than_a_lost_mapping_step_are_dropped(self):
        mapping = TransactionHistory(max_steps=2)
        points = PointHistory()
        points.record(1, "point", {"n": 1})
        for seq in (2, 3, 4):
            mapping.commit(mapping.prepare("map {}".format(seq), {"n": seq}, seq))
        points.record(5, "point", {"n": 5})
        self.assertEqual(mapping.horizon, 2)              # "map 2" left the history
        points.drop_before(mapping.horizon)
        self.assertEqual([s.seq for s in points._undo], [5])
        # Undo keeps a step's number for redo.
        mapping.undo({"n": 6})
        self.assertEqual(mapping.redo_transaction().seq, 4)


if __name__ == "__main__":
    unittest.main()
