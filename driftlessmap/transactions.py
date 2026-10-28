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


def pack(value):
    """A deep, compact copy of ``value`` and its size in bytes."""
    if isinstance(value, np.ndarray):
        if value.nbytes >= COMPRESS_FROM_BYTES:
            packed = _Packed(value)
            return packed, len(packed.payload)
        return value.copy(), value.nbytes
    if isinstance(value, dict):
        items, size = {}, 0
        for key, item in value.items():
            items[key], item_size = pack(item)
            size += item_size
        return items, size
    if isinstance(value, (list, tuple)):
        items, size = [], 0
        for item in value:
            packed, item_size = pack(item)
            items.append(packed)
            size += item_size
        return (tuple(items) if isinstance(value, tuple) else items), size
    copied = copy.deepcopy(value)
    return copied, 64


def unpack(value):
    if isinstance(value, _Packed):
        return value.unpack()
    if isinstance(value, np.ndarray):
        return value.copy()
    if isinstance(value, dict):
        return {key: unpack(item) for key, item in value.items()}
    if isinstance(value, list):
        return [unpack(item) for item in value]
    if isinstance(value, tuple):
        return tuple(unpack(item) for item in value)
    return copy.deepcopy(value)


@dataclass
class Transaction:
    label: str           # names the action, e.g. "Map cells"
    state: object        # packed state from before the action (after, once undone)
    size: int


class TransactionHistory:
    def __init__(self, max_steps=MAX_STEPS, budget_bytes=BUDGET_BYTES):
        self.max_steps = int(max_steps)
        self.budget_bytes = int(budget_bytes)
        self._undo = []
        self._redo = []

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    def prepare(self, label, state):
        """Pack ``state`` for an action; None when it exceeds the budget."""
        packed, size = pack(state)
        if size > self.budget_bytes:
            return None
        return Transaction(label, packed, size)

    def commit(self, transaction):
        """Record a prepared transaction once its action has succeeded."""
        self._undo.append(transaction)
        self._redo.clear()
        self._trim()

    def _trim(self):
        while self._undo and (len(self._undo) > self.max_steps or self._used() > self.budget_bytes):
            self._undo.pop(0)

    def _remember_inverse(self, stack, label, state):
        transaction = self.prepare(label, state)
        if transaction is None:
            # A state we cannot retain is a history barrier in both directions.
            self.clear()
            return
        stack.append(transaction)
        while self._used() > self.budget_bytes or len(self._undo) + len(self._redo) > self.max_steps:
            # Keep the next step in the direction just taken, dropping the
            # farthest entries first. Both stacks share the same budget.
            other = self._undo if stack is self._redo else self._redo
            (other if other else stack).pop(0)

    def _used(self):
        return sum(t.size for t in self._undo) + sum(t.size for t in self._redo)

    def undo_label(self):
        return self._undo[-1].label if self._undo else None

    def redo_label(self):
        return self._redo[-1].label if self._redo else None

    def undo(self, current_state):
        """Return the state to restore, keeping ``current_state`` for redo."""
        if not self._undo:
            return None
        transaction = self._undo.pop()
        self._remember_inverse(self._redo, transaction.label, current_state)
        return unpack(transaction.state)

    def redo(self, current_state):
        if not self._redo:
            return None
        transaction = self._redo.pop()
        self._remember_inverse(self._undo, transaction.label, current_state)
        return unpack(transaction.state)
