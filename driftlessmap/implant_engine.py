"""Engine side of implants: outlines, mapping, parts and building.

:class:`ImplantEngineMixin` is mixed into :class:`~driftlessmap.app.DriftlessMap`
so implants share its registration, mapping records, object list and undo.
The scientific work (fits and reports) is GUI-free in :mod:`implants`.

State, all saved with the project:

* ``implants`` -- the :class:`~driftlessmap.implants.ImplantBook`;
* ``implant_outlines`` -- the loaded section's outlines that are not mapped
  yet, ``{implant_id: {"points": [[x, y], ...], "point": [x, y] or None}}``.

Mapping an outline records it (kind ``fiber`` or ``prism``, the record's
``probe`` field naming the implant) and makes one part for that section at
once; mapping again replaces the record and the part. Parts and built
objects carry ``implant_id`` in their data, so identity never depends on
names.
"""

import copy
import csv
import re

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from . import implants as implant_model
from .implants import (
    FIBER,
    PRISM,
    TYPE_NAMES,
    AtlasFrame,
    ImplantBook,
    fit_fiber,
    fit_prism,
    resample_closed,
    validated_outline,
)
from .mapping_records import IMPLANT_KINDS, derivation
from .provenance import utc_now_iso
from .triangulation import transform_points_piecewise


def piece_type(kind):
    return "{} piece".format(kind)


def merged_type(kind):
    return "merged {}".format(kind)


def saved_outlines(value, book):
    """Validated live outlines from a project; invalid entries are dropped."""
    result = {}
    if not isinstance(value, dict):
        return result
    for implant_id, outline in value.items():
        if book.get(implant_id) is None or not isinstance(outline, dict):
            continue
        try:
            points = outline.get("points") or []
            points = np.asarray(points, dtype=float).reshape(-1, 2).tolist()
            point = outline.get("point")
            if point is not None:
                point = np.asarray(point, dtype=float).reshape(2)
                if not np.all(np.isfinite(point)):
                    continue
                point = point.tolist()
        except (TypeError, ValueError):
            continue
        if points or point is not None:
            result[implant_id] = {"points": points, "point": point}
    return result


class ImplantEngineMixin:
    def _init_implants(self):
        self.implants = ImplantBook()
        self.implant_outlines = {}

    # ------------------------------------------------------------- listing
    def implant_objects(self, implant_id, built=None):
        """Indexes of the parts (``built=False``), built objects (True) or both."""
        o = self.object_ctrl
        result = []
        for index, (kind, data) in enumerate(zip(o.obj_type, o.obj_data)):
            if not isinstance(data, dict) or data.get("implant_id") != implant_id:
                continue
            is_built = kind.startswith("merged ")
            if built is None or built == is_built:
                result.append(index)
        return result

    def implant_report(self, implant_id):
        built = self.implant_objects(implant_id, built=True)
        return self.object_ctrl.obj_data[built[-1]].get("report") if built else None

    def implant_outline(self, implant_id):
        return self.implant_outlines.get(implant_id, {"points": [], "point": None})

    def _object_group_names(self):
        return {self.object_ctrl.piece_group(name) for name in self.object_ctrl.obj_name}

    # -------------------------------------------------------------- editing
    def add_implant(self, kind, name=None, specs=None):
        taken = self._object_group_names() - {i.name for i in self.implants.implants()}
        if name and " ".join(str(name).split()) in taken:
            raise ValueError("There is already an object called {}.".format(name))
        implant = self.implants.add(kind, name=name, specs=specs, taken=taken)
        self.print_message("Added {} ({}).".format(implant.name, implant.type_name),
                           self.normal_color)
        return implant

    def rename_implant(self, implant_id, name):
        old = self.implants.get(implant_id)
        taken = self._object_group_names() - {i.name for i in self.implants.implants()}
        if " ".join(str(name).split()) in taken:
            raise ValueError("There is already an object called {}.".format(name))
        implant = self.implants.rename(implant_id, name)
        o = self.object_ctrl
        for index in self.implant_objects(implant_id):
            rest = o.obj_name[index][len(old.name):]
            o.obj_name[index] = implant.name + rest
            o.obj_list[index].text_btn.setText(o.obj_name[index])
            if isinstance(o.obj_data[index], dict) and "implant_name" in o.obj_data[index]:
                o.obj_data[index]["implant_name"] = implant.name
        return implant

    def set_implant_specs(self, implant_id, specs):
        implant = self.implants.set_specs(implant_id, specs)
        if self.implant_objects(implant_id, built=True):
            self.print_message("Build {} again to use the new settings.".format(implant.name),
                               self.reminder_color)
        return implant

    def delete_implant(self, implant_id):
        implant = self.implants.get(implant_id)
        if implant is None:
            return False
        with self.undoable("Delete {}".format(implant.name)):
            indexes = self.implant_objects(implant_id)
            if indexes:
                self.object_ctrl.delete_objects(indexes)
            for record in list(self.mapping_ledger.records()):
                if record.kind in IMPLANT_KINDS and record.probe == implant_id:
                    self.mapping_ledger.forget(record.unit_id)
                    self.editing_units.discard(record.unit_id)
            self.implant_outlines.pop(implant_id, None)
            self.implants.remove(implant_id)
        self.refresh_kept_marks()
        return True

    def set_implant_outline(self, implant_id, points):
        """Set (or, with no points, clear) an implant's outline on this section."""
        if self.implants.get(implant_id) is None:
            raise ValueError("Unknown implant.")
        entry = self.implant_outlines.setdefault(implant_id, {"points": [], "point": None})
        entry["points"] = [] if points is None or len(points) == 0 else \
            validated_outline(points).tolist()
        self._drop_empty_outline(implant_id)

    def set_implant_point(self, implant_id, point):
        """Set (or clear, with None) the tip / bottom-edge point on this section."""
        if self.implants.get(implant_id) is None:
            raise ValueError("Unknown implant.")
        entry = self.implant_outlines.setdefault(implant_id, {"points": [], "point": None})
        if point is not None:
            point = np.asarray(point, dtype=float).reshape(2)
            if not np.all(np.isfinite(point)):
                raise ValueError("The point must be finite.")
            point = point.tolist()
        entry["point"] = point
        self._drop_empty_outline(implant_id)

    def _drop_empty_outline(self, implant_id):
        entry = self.implant_outlines.get(implant_id)
        if entry is not None and not entry["points"] and entry["point"] is None:
            del self.implant_outlines[implant_id]

    # -------------------------------------------------------------- mapping
    def map_implant(self, implant_id):
        """Map an implant's outline on this section; returns ``(ok, message)``.

        Records the outline and makes the section's part at once; mapping the
        same implant on the same section again replaces both. Undoable.
        """
        implant = self.implants.get(implant_id)
        if implant is None:
            return False, "Choose an implant first."
        outline = self.implant_outlines.get(implant_id)
        if not outline or not outline["points"]:
            return False, "Draw the outline of {} on this section first.".format(implant.name)
        source = {"points": np.asarray(outline["points"], dtype=float),
                  "point": np.asarray([outline["point"]] if outline["point"] is not None
                                      else np.zeros((0, 2)), dtype=float)}
        with self.undoable("Map {}".format(implant.name)):
            ok, message = self._map_implant_source(implant, source)
            if ok:
                self.implant_outlines.pop(implant_id, None)
        return ok, message

    def _implant_registration(self):
        if self.current_atlas != "volume" or self.atlas_view.origin_3d is None:
            return None, "Implants are mapped onto the volume atlas; load it first."
        if not self.h2a_transferred:
            self.transfer_to_atlas_clicked()
            if not self.h2a_transferred:
                return None, ("The section could not be warped onto the atlas. Place or "
                              "check the landmarks in the Register step.")
        self.atlas_tri_data = list(
            self.atlas_view.working_atlas.image_dict["tri_pnts"].data["pos"])
        registration = self._build_triangulation_registration()
        if registration is None:
            return None, "The registration is not valid; check the landmarks."
        return registration, None

    def _map_implant_source(self, implant, source):
        registration, error = self._implant_registration()
        if error:
            return False, error
        outline = resample_closed(validated_outline(source["points"]))
        point = np.asarray(source["point"], dtype=float).reshape(-1, 2)
        mapped, valid, _t = transform_points_piecewise(
            np.vstack([outline, point]), registration, "histology_to_atlas")
        if not np.all(valid):
            return False, ("Part of the outline of {} lies outside the registration mesh; "
                           "add landmarks around it or redraw it.".format(implant.name))
        outline3 = self.atlas_view.get_3d_data_from_2d_view(
            np.asarray(mapped[:len(outline)]), self.atlas_display)
        point3 = (self.atlas_view.get_3d_data_from_2d_view(
            np.asarray(mapped[len(outline):]), self.atlas_display)[0]
            if len(point) else None)

        fingerprint = self.current_registration_fingerprint()
        self.mapping_review_state = self.registration_review_state()
        record = self.mapping_ledger.record(
            self.section_id, implant.kind, source, fingerprint, self.mapping_review_state,
            utc_now_iso(), probe=implant.implant_id)
        self.editing_units.discard(record.unit_id)

        o = self.object_ctrl
        earlier = [index for index in self.implant_objects(implant.implant_id, built=False)
                   if any(unit == record.unit_id for unit, _rev in o.obj_derivation[index])]
        if earlier:
            o.delete_objects(earlier)
        part = {
            "implant_id": implant.implant_id,
            "implant_name": implant.name,
            "kind": implant.kind,
            "outline": np.asarray(outline3, dtype=float),
            "point": None if point3 is None else np.asarray(point3, dtype=float).tolist(),
            "section_plane": self.atlas_display,
            "section_id": self.section_id,
        }
        o.add_object("{} - piece".format(implant.name), piece_type(implant.kind),
                     object_data=part, object_mode=self.obj_display_mode,
                     derivation=derivation([record]))
        self.refresh_kept_marks()
        note = "" if self.mapping_review_state == "reviewed" else \
            " The registration is not reviewed; the mapping is recorded as not reviewed."
        return True, "Mapped {} on this section.{}".format(implant.name, note)

    def _update_implant_mapping(self, record):
        implant = self.implants.get(record.probe)
        if implant is None:
            self.print_message("That implant no longer exists.", self.error_message_color)
            return None
        ok, message = self._map_implant_source(implant, record.source)
        self.print_message(message, self.normal_color if ok else self.error_message_color)
        if not ok:
            return None
        return self.mapping_ledger.by_unit(record.unit_id)

    def _edit_implant_marks(self, record):
        implant = self.implants.get(record.probe)
        if implant is None:
            self.print_message("That implant no longer exists.", self.error_message_color)
            return False
        if self.implant_outline(implant.implant_id)["points"]:
            self.print_message("Map or clear the outline of {} on this section before editing "
                               "the mapped one.".format(implant.name), self.error_message_color)
            return False
        point = record.source.get("point")
        self.implant_outlines[implant.implant_id] = {
            "points": np.asarray(record.source["points"], dtype=float).tolist(),
            "point": np.asarray(point, dtype=float).reshape(-1, 2)[0].tolist()
            if point is not None and np.size(point) else None,
        }
        self.editing_units.add(record.unit_id)
        self.refresh_kept_marks()
        self.print_message("The outline of {} is editable again. Map it to replace the "
                           "earlier mapping.".format(implant.name), self.normal_color)
        return True

    def implant_record_name(self, record):
        implant = self.implants.get(record.probe) if record.kind in IMPLANT_KINDS else None
        return implant.name if implant is not None else TYPE_NAMES.get(record.kind, record.kind)

    # ------------------------------------------------------------- building
    def build_implant(self, implant_id):
        """Fit an implant to all its mapped sections; returns ``(ok, message)``. Undoable."""
        implant = self.implants.get(implant_id)
        if implant is None:
            return False, "Choose an implant first."
        with self.undoable("Build {}".format(implant.name)):
            return self._build_implant(implant)

    def _implant_frame(self):
        label_data, error = self._merge_label_volume()
        if error is not None:
            return None, error
        return AtlasFrame(label_data, self.atlas_view.label_info, self.atlas_view.origin_3d,
                          self.atlas_view.vox_size_um, self.volume_atlas_axis_info), None

    def _build_implant(self, implant):
        o = self.object_ctrl
        if not self.implant_objects(implant.implant_id):
            return False, "Map {} on at least one section first.".format(implant.name)
        frame, error = self._implant_frame()
        if error is not None:
            return False, error
        # Rebuild from every section: restore the parts of an earlier build.
        for index in sorted(self.implant_objects(implant.implant_id, built=True), reverse=True):
            o.current_obj_index = index
            o.unmerge_objects()
        self._drop_superseded_pieces(piece_type(implant.kind))
        indexes = self.implant_objects(implant.implant_id, built=False)
        pieces = [o.obj_data[index] for index in indexes]
        fit = fit_fiber if implant.kind == FIBER else fit_prism
        try:
            report = fit(pieces, implant.specs, frame)
        except self.MERGE_ERRORS as exc:
            return False, "{} could not be built: {}. The parts were kept.".format(
                implant.name, exc)
        info = {
            "object_type": implant.kind,
            "implant_id": implant.implant_id,
            "implant_name": implant.name,
            "data": pieces,
            "pieces_names": [o.obj_name[index] for index in indexes],
            "report": report,
        }
        for index in indexes:
            # Parts are filed under the implant's current name for building.
            o.obj_name[index] = "{} - piece".format(implant.name)
        self._commit_merged_objects(indexes, [(implant.name, merged_type(implant.kind), info)])
        built = self.implant_objects(implant.implant_id, built=True)
        colour = QColor(*implant.colour)
        for index in built:
            o.obj_list[index].set_icon_style(colour)
            o.sig_color_changed.emit((index, (colour.red(), colour.green(), colour.blue(), 255)))
        if built:
            o.current_obj_index = built[-1]
        warnings = len(report["warnings"])
        return True, "Built {}{}.".format(
            implant.name, " with {} warning{}".format(warnings, "" if warnings == 1 else "s")
            if warnings else "")

    def imported_implant_problem(self, object_dict):
        """Why an imported fiber or prism object cannot be used, or None."""
        kind = object_dict.get("type")
        if not is_implant_type(kind):
            return None
        if not kind.startswith("merged "):
            return "implant parts are not imported; export the built implant"
        data = object_dict.get("data")
        try:
            report = data["report"]
            implant_model.validated_specs(report["kind"], report["specs"])
            implant_model._pieces(data["data"])
            implant_model.model_segments(report["model"])
        except (KeyError, TypeError, ValueError, IndexError):
            return "not a valid DriftlessMap implant"
        if report["kind"] != kind.split(" ")[1]:
            return "not a valid DriftlessMap implant"
        return None

    def adopt_imported_implant(self, object_dict):
        """List an imported fiber or prism as an implant of this project."""
        if not is_implant_type(object_dict.get("type")):
            return None
        data = object_dict["data"]
        report = data["report"]
        existing = self.implants.get(data.get("implant_id"))
        if existing is not None and existing.kind == report["kind"]:
            return existing
        name = object_dict.get("name") or None
        taken = self._object_group_names()
        try:
            implant_model.check_name(name or "")
            if self.implants.by_name(name) is not None:
                name = None
        except ValueError:
            name = None
        implant = self.implants.add(report["kind"], name=name, specs=report["specs"],
                                    taken=taken)
        data["implant_id"] = implant.implant_id
        data["implant_name"] = implant.name
        for piece in data["data"]:
            piece["implant_id"] = implant.implant_id
        object_dict["name"] = implant.name
        return implant

    def export_implant_table(self, path):
        """Write one CSV row per built implant and probe; returns the number of rows.

        Probes get a summary row (tip, entry depth, tilt); their per-site
        results stay in the probe exports.
        """
        rows = []
        for implant in self.implants.implants():
            report = self.implant_report(implant.implant_id)
            if report is not None:
                rows.append(implant_model.csv_row(implant.name, report))
        rows.extend(self._probe_table_rows())
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=implant_model.CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    def _probe_table_rows(self):
        o = self.object_ctrl
        built = [(o.obj_name[i], o.obj_data[i]) for i in range(len(o.obj_type))
                 if o.obj_type[i] == "merged probe" and isinstance(o.obj_data[i], dict)
                 and "reconstruction" in o.obj_data[i]]
        if not built:
            return []
        frame, error = self._implant_frame()
        if error is not None:
            return []
        rows = []
        for name, data in built:
            # "Probe 1 shank 2" was mapped as "Probe 1".
            probe = re.sub(r" shank \d+$", "", name)
            sections = sum(1 for record in self.mapping_ledger.records()
                           if record.kind == "probe" and record.probe == probe)
            try:
                rows.append(implant_model.probe_csv_row(name, data["reconstruction"], frame,
                                                        sections or ""))
            except (KeyError, TypeError, ValueError):
                continue        # an older probe without usable reconstruction metadata
        return rows

    # ----------------------------------------------------- undo and projects
    def _implant_state(self):
        return {"implants": self.implants.to_list(),
                "implant_outlines": copy.deepcopy(self.implant_outlines)}

    def _restore_implant_state(self, state):
        self.implants, _problems = ImplantBook.from_list(state.get("implants"))
        self.implant_outlines = saved_outlines(state.get("implant_outlines"), self.implants)

    def _implant_signature(self):
        return (repr(self.implants.to_list()),
                repr(sorted(self.implant_outlines.items())))

    def _load_implants(self, p_dict):
        self.implants, problems = ImplantBook.from_list(p_dict.get("implants"))
        self.implant_outlines = saved_outlines(p_dict.get("implant_outlines"), self.implants)
        if problems:
            self.print_message("{} implant(s) could not be restored: {}".format(
                len(problems), "; ".join(problems)), self.reminder_color)

    # --------------------------------------------------------- kept outlines
    def refresh_kept_outlines(self, records):
        """Draw the loaded section's mapped implant outlines, dashed."""
        item = getattr(self, "_kept_outlines_item", None)
        if item is None:
            item = self._kept_outlines_item = pg.PlotDataItem(
                pen=pg.mkPen(255, 255, 255, 200, width=2, style=Qt.PenStyle.DashLine),
                connect="finite")
            item.setZValue(5)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.image_view.img_stacks.vb.addItem(item)
        loops = []
        for record in records:
            points = np.asarray(record.source["points"], dtype=float)
            loops.append(np.vstack([points, points[:1], [[np.nan, np.nan]]]))
        data = np.vstack(loops) if loops else np.zeros((0, 2))
        item.setData(data[:, 0], data[:, 1])


def is_implant_type(object_type):
    return object_type in {piece_type(k) for k in (FIBER, PRISM)} | \
        {merged_type(k) for k in (FIBER, PRISM)}

