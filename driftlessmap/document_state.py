"""Document-owned object data, independent of Qt and rendering.

The legacy column payload stays readable. Widgets delegate their old attribute
names to this model while scientific callers migrate to the document directly.
Arrays are borrowed by payload(); retained snapshots must copy or pack them.
"""
from dataclasses import dataclass, field
from typing import Optional

from .mapping_records import valid_derivation

OBJECT_COLUMNS = ('obj_id', 'obj_name', 'obj_type', 'obj_data', 'obj_size',
                  'obj_opacity', 'obj_comp_mode', 'obj_drawing_mode',
                  'obj_derivation', 'obj_piece_derivation')


@dataclass
class ObjectState:
    obj_id: list = field(default_factory=list)
    obj_name: list = field(default_factory=list)
    obj_type: list = field(default_factory=list)
    obj_data: list = field(default_factory=list)
    obj_size: list = field(default_factory=list)
    obj_opacity: list = field(default_factory=list)
    obj_comp_mode: list = field(default_factory=list)
    obj_drawing_mode: list = field(default_factory=list)
    obj_derivation: list = field(default_factory=list)
    obj_piece_derivation: list = field(default_factory=list)
    obj_count: int = 0
    current_obj_index: Optional[int] = None

    def add(self, name, kind, data, mode, drawing_mode, derivation=None,
            piece_derivation=None, size=2, opacity=100):
        identity = self.obj_count
        merged = "merged" in kind
        values = (identity, name, kind, data, size if merged else [],
                  opacity if merged else [], mode if merged else [], drawing_mode,
                  valid_derivation(derivation),
                  [valid_derivation(item) for item in piece_derivation]
                  if isinstance(piece_derivation, (list, tuple)) else [])
        for column, value in zip(OBJECT_COLUMNS, values):
            getattr(self, column).append(value)
        self.obj_count += 1
        return identity

    def remove_row(self, index):
        if not 0 <= index < len(self.obj_id):
            raise IndexError(index)
        for name in OBJECT_COLUMNS:
            del getattr(self, name)[index]
        if self.current_obj_index is not None:
            if self.current_obj_index == index:
                self.current_obj_index = len(self.obj_id) - 1 if self.obj_id else None
            elif self.current_obj_index > index:
                self.current_obj_index -= 1

    def payload(self):
        return {**{name: getattr(self, name) for name in OBJECT_COLUMNS},
                'obj_count': self.obj_count, 'current_obj_index': self.current_obj_index}

    def restore_identity(self, payload):
        ids = payload.get('obj_id')
        if (not isinstance(ids, (list, tuple)) or len(ids) != len(self.obj_type)
                or any(type(i) is not int or i < 0 for i in ids)
                or len(set(ids)) != len(ids)):
            return False  # Legacy/invalid identities keep generated IDs.
        self.obj_id = list(ids)
        minimum = max(ids, default=-1) + 1
        count = payload.get('obj_count')
        self.obj_count = max(minimum, count) if type(count) is int else minimum
        return True

    def index_of_id(self, identity):
        try:
            return self.obj_id.index(identity)
        except ValueError:
            return None


@dataclass
class DocumentState:
    objects: ObjectState = field(default_factory=ObjectState)


def object_state_property(name):
    """Compatibility adapter: mutations still reach the single model owner."""
    return property(lambda control: getattr(control.state, name),
                    lambda control, value: setattr(control.state, name, value))
