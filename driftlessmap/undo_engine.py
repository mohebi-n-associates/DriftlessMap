"""Undo and Redo for the engine: three histories ordered by one step number.

Mixed into ``DriftlessMap`` (extracted from ``app.py`` without changing
behaviour). Every recorded step takes a number from ``_next_edit_seq``:

* point edits (``point_action``, ``PointHistory``): probe, cell and contour
  point lists only, so a click is cheap and never evicts mapping steps;
* per-tool edits (``save_current_action``, ``action_list``/``action_id``):
  raster and pencil edits on a layer, at most six;
* mapping steps (``undoable``, ``TransactionHistory``): Map, Update mapping,
  Make parts, Build and plan edits, captured by the engine's
  ``_transaction_state`` and restored by ``_restore_transaction_state``.

Undo takes back the newest of the three histories' next steps
(``next_undo``), Redo the oldest undone one (``next_redo``).
"""

import copy
from contextlib import contextmanager
from functools import wraps

import numpy as np

from .project_io import padded_cell_count
from .state_digest import state_digest
from .transactions import unpack


def point_action(label, layers=None):
    """Record a point edit in the point history (2.9.3), including the first point.

    Only the point lists are kept (``DriftlessMap._point_state``), so a click
    stays cheap and never pushes mapping steps out of their history. With
    ``layers``, only edits on one of those selected layers are recorded here;
    others keep the per-tool history.
    """
    def decorate(method):
        @wraps(method)
        def recorded(self, *args, **kwargs):
            if self._transaction_depth or self._recording_points:
                return method(self, *args, **kwargs)
            if layers is not None:
                selected = self.layer_ctrl.current_layer_index
                if len(selected) != 1 or self.layer_ctrl.layer_link[selected[0]] not in layers:
                    return method(self, *args, **kwargs)
            return self._record_point_edit(label, method, args, kwargs)
        return recorded
    return decorate


class UndoEngineMixin:
    """Mixed into ``DriftlessMap``; see the module docstring."""

    def save_current_action(self, current_tool, layer_link, data, layer_tb):
        if self._transaction_depth or self._recording_points:
            return  # The enclosing transaction or point step already owns this edit.
        # A new edit starts a new branch: undone point or mapping steps go.
        self.point_history.clear_redo()
        self.undo_history.clear_redo()
        if self.action_id != 0:
            del_index = np.arange(
                len(self.action_list) + self.action_id, len(self.action_list)
            )[::-1]
            for da_ind in del_index:
                del self.action_list[da_ind]
            self.action_id = 0
        # Snapshots are deep copies so later edits cannot rewrite history.
        current_action = {
            "tool": current_tool,
            "link": layer_link,
            "data": copy.deepcopy(data),
            "layer": None if layer_tb is None else np.array(layer_tb, copy=True),
            "seq": self._next_edit_seq(),
        }
        self.action_list.append(current_action)
        if len(self.action_list) > 6:
            del self.action_list[0]

    def redo_called(self):
        """Redo the step undone last: a point edit, a tool edit or a mapping step."""
        self.flush_plan_edits()
        kind, _label = self.next_redo()
        if kind == "point":
            return self._step_points(self.point_history.redo, "Redid")
        if kind != "tool":
            return self.redo_mapping_step()
        self.action_id += 1
        if self.action_id > 0:
            self.action_id -= 1
            return
        self.set_undo_redo_data()

    def undo_called(self):
        """Undo the newest step: a point edit, a tool edit or a mapping step.

        Every step is numbered when recorded (``_next_edit_seq``), so Undo
        takes back the newest of the three histories' next steps.
        """
        self.flush_plan_edits()
        kind, _label = self.next_undo()
        if kind == "point":
            return self._step_points(self.point_history.undo, "Undid")
        if kind != "tool":
            return self.undo_mapping_step()
        self.action_id -= 1
        if abs(self.action_id) >= len(self.action_list):
            self.action_id += 1
            return
        self.set_undo_redo_data()

    # ------------------------------------------------------- point history
    POINT_KEYS = ("img-probe", "img-cells", "cell_size", "cell_symbol", "cell_layer_index",
                  "cell_count")
    ATLAS_POINT_KEYS = ("atlas-probe", "atlas-cells", "cell_size", "cell_symbol",
                        "cell_layer_index", "cell_count", "atlas-contour")

    def _next_edit_seq(self):
        self._edit_seq += 1
        return self._edit_seq

    def _drop_points_past_horizon(self):
        """Forget point steps that a lost mapping step separates from now."""
        if self.undo_history.barrier:
            self.undo_history.barrier = False
            self._forget_point_history()
        else:
            self.point_history.drop_before(self.undo_history.horizon)

    def _forget_point_history(self):
        self.point_history.clear()
        self._history_epoch += 1

    def _point_state(self, copy_state=True):
        """The point lists a point step can change (never objects or masks)."""
        state = {"img": {key: self.working_img_data[key] for key in self.POINT_KEYS},
                 "atlas": {key: self.working_atlas_data[key] for key in self.ATLAS_POINT_KEYS}}
        return copy.deepcopy(state) if copy_state else state

    def _record_point_edit(self, label, method, args, kwargs):
        before = self._point_state()
        epoch = self._history_epoch
        self._recording_points = True
        try:
            result = method(self, *args, **kwargs)
        finally:
            self._recording_points = False
        # A mapping step inside the edit dropped the older history; keep it so.
        if epoch == self._history_epoch and \
                state_digest(self._point_state(copy_state=False)) != state_digest(before):
            if self.action_id != 0:   # undone tool edits cannot come back now
                del self.action_list[len(self.action_list) + self.action_id:]
                self.action_id = 0
            self.undo_history.clear_redo()
            self.point_history.record(self._next_edit_seq(), label, before)
            self.sync_mapping_undo_actions()
        return result

    def _set_point_state(self, state):
        self.working_img_data.update(state["img"])
        self.working_atlas_data.update(state["atlas"])
        for kind in ("probe", "cells"):
            self._show_section_marks(kind)
        for kind in ("probe", "cells", "contour"):
            self._show_atlas_marks(kind)
        self.tool_box.update_cell_count_label(self.working_img_data["cell_count"])
        self.refresh_kept_marks()

    def _step_points(self, step, verb):
        upcoming = (self.point_history.undo_step() if verb == "Undid"
                    else self.point_history.redo_step())
        self._set_point_state(step(self._point_state(copy_state=False)))
        self.sync_mapping_undo_actions()
        self.print_message("{} {}.".format(verb, upcoming.label.lower()), self.normal_color)
        return True

    def _tool_undo_seq(self):
        done = len(self.action_list) + self.action_id
        return self.action_list[done - 1].get("seq", 0) if done > 1 else None

    def _tool_redo_seq(self):
        if self.action_id >= 0:
            return None
        return self.action_list[len(self.action_list) + self.action_id].get("seq", 0)

    def next_undo(self):
        """``(kind, label)`` of what Undo takes back next: kind is "point",
        "tool" (a per-tool edit such as a pencil stroke), "mapping" or None."""
        point, tool = self.point_history.undo_step(), self._tool_undo_seq()
        mapping = self.undo_history.undo_transaction()
        candidates = [(step.seq, "point", step.label) for step in (point,) if step is not None]
        candidates += [(tool, "tool", "tool edit")] if tool is not None else []
        candidates += [(mapping.seq, "mapping", mapping.label)] if mapping is not None else []
        return max(candidates)[1:] if candidates else (None, None)

    def next_redo(self):
        """``(kind, label)`` of what Redo brings back next (see ``next_undo``)."""
        point, tool = self.point_history.redo_step(), self._tool_redo_seq()
        mapping = self.undo_history.redo_transaction()
        candidates = [(step.seq, "point", step.label) for step in (point,) if step is not None]
        candidates += [(tool, "tool", "tool edit")] if tool is not None else []
        candidates += [(mapping.seq, "mapping", mapping.label)] if mapping is not None else []
        return min(candidates)[1:] if candidates else (None, None)

    def forget_layer_actions(self, layer_link):
        """Drop undo history for a layer that no longer exists."""
        kept = [action for action in self.action_list if action["link"] != layer_link]
        if len(kept) != len(self.action_list):
            # Only a changed list resets the position: resetting it otherwise
            # silently brought undone tool edits back into reach (2.9.3).
            self.action_list = kept
            self.action_id = 0

    def set_undo_redo_data(self):
        current_action = self.action_list[self.action_id - 1]
        # Restore a copy so the snapshot survives further edits.
        current_data = copy.deepcopy(current_action["data"])
        layer_link = current_action["link"]
        current_tool = current_action["tool"]
        da_layer = current_action["layer"]
        if layer_link not in self.layer_ctrl.layer_link:
            return
        if current_tool in self.tool_box.checkable_btn_dict:
            self.tool_box.checkable_btn_dict[current_tool].setChecked(True)
        if "img" in layer_link:
            if layer_link == "img-process":
                self.image_view.processing_img = current_data["data"]
                self.image_view.img_stacks.set_data(self.image_view.processing_img)
            elif layer_link in ["img-mask", "img-virus"]:
                self.working_img_data[layer_link] = current_data["data"]
                self.image_view.img_stacks.image_dict[layer_link].setImage(
                    self.working_img_data[layer_link]
                )
            elif layer_link == "img-cells":
                self.working_img_data[layer_link] = current_data["data"]
                self.working_img_data["cell_size"] = current_data["size"]
                self.working_img_data["cell_symbol"] = current_data["symbol"]
                self.working_img_data["cell_layer_index"] = current_data["index"]
                self.working_img_data["cell_count"] = padded_cell_count(current_data["count"])
                self.image_view.img_stacks.image_dict[layer_link].setData(
                    pos=np.asarray(self.working_img_data[layer_link]),
                    symbol=self.working_img_data["cell_symbol"],
                )
                self.tool_box.update_cell_count_label(self.working_img_data["cell_count"])
            elif layer_link == "img-drawing":
                self.working_img_data[layer_link] = current_data["data"]
                if current_data["closed"]:
                    self.set_img_pencil_closed_style()
                else:
                    self.clear_img_pencil_closed_style()
                self.image_view.img_stacks.image_dict[layer_link].setData(
                    np.asarray(self.working_img_data[layer_link])
                )
            elif layer_link == "img-contour":
                self.working_img_data[layer_link] = current_data["data"]
                self.image_view.img_stacks.image_dict[layer_link].setData(
                    np.asarray(self.working_img_data[layer_link])
                )
            elif layer_link == "img-probe":
                self.working_img_data[layer_link] = current_data["data"]
                self.image_view.img_stacks.image_dict[layer_link].setData(
                    pos=np.asarray(self.working_img_data[layer_link])
                )
            else:
                return
        elif layer_link in ["atlas-slice", "atlas-mask"]:
            self._set_atlas_raster(layer_link, current_data["data"])
        elif layer_link == "atlas-probe":
            self.working_atlas_data[layer_link] = current_data["data"]
            self.atlas_view.working_atlas.image_dict[layer_link].setData(
                pos=np.asarray(self.working_atlas_data[layer_link])
            )
        else:
            return
        if da_layer is not None:
            da_index = self.layer_ctrl.layer_link.index(layer_link)
            self.layer_ctrl.layer_list[da_index].set_thumbnail_data(da_layer)

    @contextmanager
    def undoable(self, label):
        """Record the enclosed action for undo; nested actions join the outer one."""
        if self._transaction_depth:
            self._transaction_depth += 1
            try:
                yield
            finally:
                self._transaction_depth -= 1
            return
        if not self._flushing_plans:
            # A staged plan edit is its own step, before this one.
            self.flush_plan_edits()
        identities = {"obj_id": list(self.document.objects.obj_id),
                      "obj_count": self.document.objects.obj_count}
        before = self._transaction_signature()
        transaction = self.undo_history.prepare(label, self._transaction_state(copy_state=False),
                                                self._next_edit_seq())
        if transaction is None:
            self.print_message("{} is too large to undo (over the undo memory budget); it "
                               "will not be undoable.".format(label), self.reminder_color)
        self._transaction_depth = 1
        try:
            yield
        except Exception:
            if transaction is not None:
                self._restore_transaction_state(unpack(transaction.state))
            else:
                self.undo_history.clear()
                self._forget_point_history()
            self.sync_mapping_undo_actions()
            raise
        finally:
            self._transaction_depth = 0
        if self._transaction_signature() != before:
            if transaction is None:
                self.undo_history.clear()
                self._forget_point_history()
            else:
                self.undo_history.commit(transaction)
                self.point_history.clear_redo()
                self._drop_points_past_horizon()
            # The per-tool edit history refers to state this action replaced.
            self.action_list = []
            self.action_id = 0
            self.sync_mapping_undo_actions()

        else:
            # Rebuilding identical content is not a new scientific action.
            # Keep identities too, rather than dirtying the saved document.
            self.object_ctrl.restore_identity(identities)

    def sync_mapping_undo_actions(self):
        """Name the next undo and redo step in the Edit menu."""
        for action, label, verb in (
                (self.actionUndo_Mapping, self.undo_history.undo_label(), "Undo"),
                (self.actionRedo_Mapping, self.undo_history.redo_label(), "Redo")):
            action.setText("{} {}".format(verb, label) if label else
                           "{} Mapping Step".format(verb))
            action.setEnabled(label is not None)

    def undo_mapping_step(self):
        # A staged plan edit becomes a step first, so Undo takes it back and no
        # late timer brings it back afterwards (review R2 of 2.8.3).
        self.flush_plan_edits()
        return self._step_history(self.undo_history.undo, self.undo_history.undo_label(), "Undid")

    def redo_mapping_step(self):
        self.flush_plan_edits()
        return self._step_history(self.undo_history.redo, self.undo_history.redo_label(), "Redid")

    def _step_history(self, step, label, verb):
        if label is None:
            self.print_message("Nothing to {}.".format(verb.lower()[:-1] if verb == "Undid"
                                                         else "redo"), self.reminder_color)
            return False
        state = step(self._transaction_state(copy_state=False))
        self._restore_transaction_state(state)
        self.action_list = []
        self.action_id = 0
        self._drop_points_past_horizon()
        self.sync_mapping_undo_actions()
        self.print_message("{} {}.".format(verb, label), self.normal_color)
        return True
