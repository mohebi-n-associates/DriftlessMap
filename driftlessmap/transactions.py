"""Bounded undo history for mapping, updating, making parts and building.

A transaction is the state an action can change, captured before it runs.
Undo restores it and keeps the state it replaced for redo; a new action
clears redo. The history holds at most ``max_steps`` transactions within
``budget_bytes``, dropping the oldest first. Large arrays (expression masks)
are stored zlib-compressed, so mostly empty full-slide masks stay small.

The history is GUI-free and never saved with a project: the engine captures
and restores the state, this module only keeps it.
"""

import copy
import zlib
from dataclasses import dataclass

import numpy as np

MAX_STEPS = 10
BUDGET_BYTES = 500 * 1024 * 1024
# Arrays at least this large are compressed; small point lists are kept as is.
COMPRESS_FROM_BYTES = 64 * 1024


class _Packed:
    """A compressed NumPy array."""

    __slots__ = ("dtype", "shape", "payload")

    def __init__(self, array):
        array = np.ascontiguousarray(array)
        self.dtype, self.shape = array.dtype, array.shape
        self.payload = zlib.compress(array.tobytes(), 1)

    def unpack(self):
        return np.frombuffer(zlib.decompress(self.payload), dtype=self.dtype).reshape(
            self.shape).copy()


def pack(value, _arrays=None):
    """A deep, compact copy of ``value`` and its size in bytes."""
    if _arrays is None:
        _arrays = {}
    if isinstance(value, np.ndarray):
        if id(value) in _arrays:
            return _arrays[id(value)], 0
        if value.nbytes >= COMPRESS_FROM_BYTES:
            packed = _Packed(value)
            _arrays[id(value)] = packed
            return packed, len(packed.payload)
        copied_array = value.copy()
        _arrays[id(value)] = copied_array
        return copied_array, value.nbytes
    if isinstance(value, dict):
        items, size = {}, 0
        for key, item in value.items():
            items[key], item_size = pack(item, _arrays)
            size += item_size
        return items, size
    if isinstance(value, (list, tuple)):
        items, size = [], 0
        for item in value:
            packed, item_size = pack(item, _arrays)
            items.append(packed)
            size += item_size
        return (tuple(items) if isinstance(value, tuple) else items), size
    copied = copy.deepcopy(value)
    return copied, 64


def unpack(value, _arrays=None):
    """Restore one independent state, retaining array aliases within it."""
    if _arrays is None:
        _arrays = {}
    if isinstance(value, (_Packed, np.ndarray)):
        if id(value) not in _arrays:
            _arrays[id(value)] = value.unpack() if isinstance(value, _Packed) else value.copy()
        return _arrays[id(value)]
    if isinstance(value, dict):
        return {key: unpack(item, _arrays) for key, item in value.items()}
    if isinstance(value, list):
        return [unpack(item, _arrays) for item in value]
    if isinstance(value, tuple):
        return tuple(unpack(item, _arrays) for item in value)
    return copy.deepcopy(value)


@dataclass
class Transaction:
    label: str           # names the action, e.g. "Map cells"
    state: object        # packed state from before the action (after, once undone)
    size: int
    seq: int = 0         # orders it against point steps (2.9.3)


class TransactionHistory:
    def __init__(self, max_steps=MAX_STEPS, budget_bytes=BUDGET_BYTES):
        self.max_steps = int(max_steps)
        self.budget_bytes = int(budget_bytes)
        self._undo = []
        self._redo = []
        # Steps numbered below this are gone: newer than none of what is left
        # (2.9.3). The engine drops point steps older than a dropped step.
        self.horizon = 0
        self.barrier = False   # set when undo/redo had to clear everything

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    def _drop(self, stack):
        self.horizon = max(self.horizon, stack.pop(0).seq)

    def prepare(self, label, state, seq=0):
        """Pack ``state`` for an action; None when it exceeds the budget."""
        packed, size = pack(state)
        if size > self.budget_bytes:
            return None
        return Transaction(label, packed, size, seq)

    def commit(self, transaction):
        """Record a prepared transaction once its action has succeeded."""
        self._undo.append(transaction)
        self._redo.clear()
        self._trim()

    def _trim(self):
        while self._undo and (len(self._undo) > self.max_steps or self._used() > self.budget_bytes):
            self._drop(self._undo)

    def _remember_inverse(self, stack, label, state, seq=0):
        transaction = self.prepare(label, state, seq)
        if transaction is None:
            # A state we cannot retain is a history barrier in both directions.
            self.barrier = True
            self.clear()
            return
        stack.append(transaction)
        while self._used() > self.budget_bytes or len(self._undo) + len(self._redo) > self.max_steps:
            # Keep the next step in the direction just taken, dropping the
            # farthest entries first. Both stacks share the same budget.
            other = self._undo if stack is self._redo else self._redo
            self._drop(other if other else stack)

    def _used(self):
        return sum(t.size for t in self._undo) + sum(t.size for t in self._redo)

    def clear_redo(self):
        """A new edit starts a new branch: what was undone cannot come back."""
        self._redo.clear()

    def labels(self):
        """(undo labels, redo labels), the next step first."""
        return ([t.label for t in reversed(self._undo)], [t.label for t in reversed(self._redo)])

    def undo_transaction(self):
        return self._undo[-1] if self._undo else None

    def redo_transaction(self):
        return self._redo[-1] if self._redo else None

    def undo_label(self):
        return self._undo[-1].label if self._undo else None

    def redo_label(self):
        return self._redo[-1].label if self._redo else None

    def undo(self, current_state):
        """Return the state to restore, keeping ``current_state`` for redo."""
        if not self._undo:
            return None
        transaction = self._undo.pop()
        self._remember_inverse(self._redo, transaction.label, current_state, transaction.seq)
        return unpack(transaction.state)

    def redo(self, current_state):
        if not self._redo:
            return None
        transaction = self._redo.pop()
        self._remember_inverse(self._undo, transaction.label, current_state, transaction.seq)
        return unpack(transaction.state)


POINT_MAX_STEPS = 200


@dataclass
class PointStep:
    seq: int             # orders this step against the per-tool history
    label: str
    state: dict          # the point lists from before the step (after, once undone)


class PointHistory:
    """Undo for single point edits (2.9.3): marking and erasing probe points,
    cells and atlas contour points.

    Each step keeps only the point lists, never objects or masks, so a click
    stays cheap however large the project is, and point steps never push
    Map, Build or other mapping steps out of their own bounded history.
    Point and mapping steps share one numbering, so Undo takes back whichever
    is newest; point steps older than a mapping step that left the history
    are dropped with it (``TransactionHistory.horizon``).
    """

    def __init__(self, max_steps=POINT_MAX_STEPS):
        self.max_steps = int(max_steps)
        self._undo = []
        self._redo = []

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    def clear_redo(self):
        self._redo.clear()

    def record(self, seq, label, before):
        self._undo.append(PointStep(seq, label, copy.deepcopy(before)))
        self._redo.clear()
        del self._undo[:-self.max_steps]

    def drop_before(self, seq):
        """Forget steps numbered below ``seq`` (a mapping step between them is gone)."""
        self._undo = [step for step in self._undo if step.seq > seq]
        self._redo = [step for step in self._redo if step.seq > seq]

    def undo_step(self):
        return self._undo[-1] if self._undo else None

    def redo_step(self):
        return self._redo[-1] if self._redo else None

    def labels(self):
        return ([s.label for s in reversed(self._undo)], [s.label for s in reversed(self._redo)])

    def undo(self, current):
        """Return the state to restore, keeping ``current`` for redo."""
        step = self._undo.pop()
        self._redo.append(PointStep(step.seq, step.label, copy.deepcopy(current)))
        return copy.deepcopy(step.state)

    def redo(self, current):
        step = self._redo.pop()
        self._undo.append(PointStep(step.seq, step.label, copy.deepcopy(current)))
        return copy.deepcopy(step.state)
