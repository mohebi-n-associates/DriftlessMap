import unittest
import numpy as np
from driftlessmap.document_state import DocumentState, ObjectState
from driftlessmap.transactions import pack, unpack


class DocumentStateTests(unittest.TestCase):
    def test_documents_have_independent_object_state(self):
        first, second = DocumentState(), DocumentState()
        first.objects.obj_name.append('one')
        self.assertEqual(second.objects.obj_name, [])
        self.assertIs(first.objects.payload()['obj_name'], first.objects.obj_name)

    def test_model_add_remove_and_rename_need_no_widgets(self):
        state = ObjectState()
        a = state.add('first', 'probe piece', np.zeros((2, 3)), 'opaque', 'line')
        b = state.add('second', 'probe piece', np.ones((2, 3)), 'opaque', 'line')
        state.current_obj_index = 1
        state.remove_row(0)
        self.assertEqual(state.current_obj_index, 0)
        self.assertEqual(state.obj_id, [b])
        self.assertIsNone(state.index_of_id(a))
        state.obj_name[0] = 'renamed'
        self.assertEqual(state.payload()['obj_name'], ['renamed'])

    def test_distinct_equal_arrays_remain_independent(self):
        a = np.arange(100000)
        packed, size = pack([a, a.copy()])
        self.assertEqual(size, 2 * pack(a)[1])
        restored = unpack(packed)
        restored[0][0] = -1
        self.assertEqual(restored[1][0], 0)

    def test_identity_restore_preserves_gaps_and_monotonic_counter(self):
        state = ObjectState(obj_type=['probe piece', 'probe piece'])
        self.assertTrue(state.restore_identity({'obj_id': [4, 9], 'obj_count': 20}))
        self.assertEqual(state.index_of_id(9), 1)
        self.assertIsNone(state.index_of_id(7))
        self.assertEqual(state.obj_count, 20)
        self.assertFalse(state.restore_identity({'obj_id': [9, 9]}))
        self.assertEqual(state.obj_id, [4, 9])
        self.assertFalse(state.restore_identity({}))

    def test_history_deduplicates_arrays_and_restores_independent_snapshots(self):
        for size in (8, 100000):
            array = np.arange(size)
            single, one_size = pack(array)
            packed, shared_size = pack({'a': array, 'b': [array]})
            self.assertEqual(one_size, shared_size)
            restored = unpack(packed)
            self.assertIs(restored['a'], restored['b'][0])
            restored['a'][0] = -42
            self.assertEqual(array[0], 0)
            self.assertEqual(unpack(packed)['a'][0], 0)
            self.assertEqual(unpack(single)[0], 0)
