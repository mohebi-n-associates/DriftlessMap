"""Planned probes in the engine (see ``probe_planning_design.md``).

``ProbePlanEngineMixin`` (mixed into ``DriftlessMap``) keeps the project's
``PlanBook``, reads plans against the loaded volume atlas and builds each plan
into ordinary merged-probe objects named ``"<probe> plan"`` (``"<probe> plan
shank N"``) with the engine's own ``calculate_probe_info``, so the Region
table, exports and 3D view treat a plan like any built probe. The objects
carry ``plan_of`` and the plan they were built from.
"""

import os

import numpy as np

from .mapping_records import BUILD_CHANGED, CURRENT
from .probe_plans import (
    DEFAULT_DEPTH_UM,
    PlanAtlas,
    PlanBook,
    ProbePlan,
    coordinate_line,
    plan_from_entry_depth,
    plan_readout,
    region_centre,
    regions_along,
    shank_lines,
    surface_entry,
)
from .probe_utiles import calculate_probe_info, probe_error_message

PLAN_SUFFIX = " plan"


def plan_object_name(probe, shank=None, shanks=1):
    name = probe + PLAN_SUFFIX
    return "{} shank {}".format(name, shank + 1) if shanks > 1 else name


class ProbePlanEngineMixin:
    def _init_probe_plans(self):
        self.probe_plans = PlanBook()
        self._plan_atlas = None
        self._plan_atlas_key = None
        self._plan_metadata = None
        self._plan_metadata_key = None
        self.plan_previews = {}     # probe -> plan being edited, drawn in its place
        self.plan_colours = {}      # probe -> colour of its track on the atlas

    # ---------------------------------------------------------------- atlas
    def _atlas_key(self):
        view = self.atlas_view
        return (self.volume_atlas_path, id(view.atlas_label), view.vox_size_um,
                None if view.origin_3d is None else tuple(np.asarray(view.origin_3d).tolist()))

    def plan_atlas(self):
        """The loaded volume atlas as a ``PlanAtlas``, or None without one."""
        view = self.atlas_view
        if (self.current_atlas != "volume" or view.atlas_label is None
                or view.origin_3d is None):
            return None
        key = self._atlas_key()
        if key != self._plan_atlas_key:
            label_data, error = self._merge_label_volume()
            if error is not None:
                return None
            self._plan_atlas = PlanAtlas(label_data, view.label_info, view.vox_size_um,
                                         view.origin_3d)
            self._plan_atlas_key = key
        return self._plan_atlas

    def _plan_atlas_metadata(self):
        key = self._atlas_key()
        if key != self._plan_metadata_key or self._plan_metadata is None:
            metadata, error = self.get_probe_atlas_metadata()
            if error is not None:
                return None, error
            self._plan_metadata, self._plan_metadata_key = metadata, key
        return self._plan_metadata, None

    def plan_atlas_name(self):
        path = self.volume_atlas_path
        return os.path.basename(os.path.normpath(path)) if path else ""

    # ---------------------------------------------------------------- plans
    def probe_plan(self, probe):
        return self.probe_plans.get(probe)

    def current_probe_settings(self):
        return self.probe_settings.get_settings()

    def default_probe_plan(self, probe):
        """A vertical plan to start from: 1 mm right of Bregma (closer to the
        midline when the brain is narrower), ``DEFAULT_DEPTH_UM`` below the
        surface, or just above the bottom of the tissue when that is shallower."""
        settings = self.current_probe_settings()
        offsets = None
        if settings.get("probe_type") == 1 and self.multi_shanks:
            offsets = list(settings.get("multi_shanks") or []) or None
        plan = ProbePlan(probe, [1000.0, 0.0, -DEFAULT_DEPTH_UM], probe_settings=settings,
                         shank_offsets_um=offsets)
        atlas = self.plan_atlas()
        if atlas is None:
            return plan
        bottom = -atlas.bregma[2] * atlas.vox_um
        for ml in (1000.0, 500.0, 250.0, 0.0):
            entry, _inside = surface_entry(atlas, [ml, 0.0, bottom], plan.direction)
            if entry is None:
                continue
            runs = regions_along(atlas, entry, np.asarray(entry) + plan.direction
                                 * DEFAULT_DEPTH_UM)
            depth = DEFAULT_DEPTH_UM
            outside = [run for run in runs if run["id"] == 0]
            if outside:
                # Stop one voxel short of where the tissue ends.
                depth = outside[0]["start_um"] - atlas.vox_um
            if depth > 0:
                return plan_from_entry_depth(plan, entry, depth)
        return plan

    def probe_plan_readout(self, probe_or_plan):
        plan = (probe_or_plan if isinstance(probe_or_plan, ProbePlan)
                else self.probe_plans.get(probe_or_plan))
        atlas = self.plan_atlas()
        if plan is None or atlas is None:
            return None
        return plan_readout(plan, atlas)

    def plan_coordinate_line(self, probe):
        plan = self.probe_plans.get(probe)
        readout = self.probe_plan_readout(plan) if plan else None
        if readout is None:
            return None
        return coordinate_line(plan, readout, self.plan_atlas_name())

    def region_centre_um(self, region_id, side=None):
        atlas = self.plan_atlas()
        return None if atlas is None else region_centre(atlas, region_id, side=side)

    def set_probe_plan(self, plan, colour=None):
        """Store ``plan`` and build it; returns ``(ok, message)``."""
        if colour is not None:
            self.plan_colours[plan.probe] = tuple(colour[:3])
        with self.undoable("Edit {} plan".format(plan.probe)):
            self.probe_plans.set(plan)
            return self._build_plan(plan.probe, colour)

    def remove_probe_plan(self, probe):
        """Forget ``probe``'s plan and delete its planned objects."""
        indexes = self.plan_objects(probe)
        if indexes:
            self.object_ctrl.delete_objects(indexes)
        return self.probe_plans.remove(probe)

    def rename_probe_plan(self, old, new):
        o = self.object_ctrl
        for index in self.plan_objects(old):
            name = o.obj_name[index]
            new_name = new + name[len(old):]
            o.obj_name[index] = new_name
            o.obj_list[index].text_btn.setText(new_name)
            data = o.obj_data[index]
            data["plan_of"] = new
            data["pieces_names"] = [new_name]
            if isinstance(data.get("plan"), dict):
                data["plan"]["probe"] = new
        self.probe_plans.rename(old, new)

    def clear_atlas_probe_marks(self):
        """Forget probe points clicked on the atlas (after they set a plan)."""
        self.working_atlas_data["atlas-probe"].clear()
        working = self.atlas_view.working_atlas
        working.image_dict["atlas-probe"].clear()
        working.image_dict["atlas-trajectory"].clear()
        working.remove_pre_trajectories_vis_lines()
        if "atlas-probe" in self.layer_ctrl.layer_link:
            self.remove_single_link_related("atlas-probe")

    def atlas_probe_marks_um(self):
        """The probe points clicked on the atlas, Bregma-relative in um."""
        points = np.asarray(self.working_atlas_data["atlas-probe"] or [], dtype=float)
        if not len(points):
            return np.zeros((0, 3))
        vox = self.atlas_view.get_3d_data_from_2d_view(points.reshape(-1, 2),
                                                       self.atlas_display)
        return np.asarray(vox, dtype=float) * float(self.atlas_view.vox_size_um)

    def plan_objects(self, probe=None):
        """Indexes of the objects built from ``probe``'s plan (any plan if None)."""
        o = self.object_ctrl
        found = []
        for index, data in enumerate(o.obj_data):
            if isinstance(data, dict) and data.get("plan_of") is not None \
                    and (probe is None or data.get("plan_of") == probe):
                found.append(index)
        return found

    def plan_build_status(self, index):
        """CURRENT or BUILD_CHANGED for an object built from a plan; None otherwise."""
        data = self.object_ctrl.obj_data[index]
        if not isinstance(data, dict) or data.get("plan_of") is None:
            return None
        plan = self.probe_plans.get(data["plan_of"])
        if plan is None or plan.to_dict() != data.get("plan"):
            return BUILD_CHANGED
        return CURRENT

    def show_plan_on_atlas(self, probe):
        """Move the atlas pages through the plan's tip; False without a plan."""
        plan = self.probe_plans.get(probe)
        atlas = self.plan_atlas()
        if plan is None or atlas is None:
            return False
        point = atlas.to_vox(plan.tip_um)
        view = self.atlas_view
        for control, page in ((view.spage_ctrl, point[0]), (view.cpage_ctrl, point[1]),
                              (view.hpage_ctrl, point[2])):
            control.set_val(int(np.clip(round(page), 0, control.page_slider.maximum())))
        return True

    # ---------------------------------------------------------------- build
    def _build_plan(self, probe, colour=None):
        plan = self.probe_plans.get(probe)
        o = self.object_ctrl
        earlier = self.plan_objects(probe)
        if plan is None:
            return False, "{} has no plan.".format(probe)
        atlas = self.plan_atlas()
        if atlas is None:
            return False, "Load a volume atlas to plan a probe."
        readout = plan_readout(plan, atlas)
        if readout["entry_um"] is None or readout["depth_um"] < atlas.vox_um:
            if earlier:
                o.delete_objects(earlier)
            return False, readout["warnings"][-1]
        metadata, error = self._plan_atlas_metadata()
        if error is not None:
            return False, error
        settings = plan.probe_settings or self.current_probe_settings()
        lines = shank_lines(plan, readout, atlas)
        built = []
        for shank, line in enumerate(lines):
            name = plan_object_name(probe, shank, len(lines))
            try:
                info, error_index = calculate_probe_info(
                    [line], [name], atlas.labels, atlas.label_info, atlas.vox_um,
                    settings, bool(self.tool_box.merge_sites), atlas.bregma, 0,
                    plan.normal, True, metadata)
            except self.MERGE_ERRORS as exc:
                return False, "{} could not be built: {}.".format(name, exc)
            if error_index != 0:
                return False, "{} could not be built: {}.".format(
                    name, probe_error_message(error_index))
            info["plan_of"] = probe
            info["plan"] = plan.to_dict()
            built.append((name, info))
        if earlier:
            o.delete_objects(earlier)
        for name, info in built:
            o.add_object(name, "merged probe", object_data=info,
                         object_mode=self.obj_display_mode)
            if colour is not None:
                self._colour_object(len(o.obj_name) - 1, colour)
        o.current_obj_index = len(o.obj_name) - 1
        return True, "Planned {}.".format(probe)

    def _colour_object(self, index, colour):
        from PyQt6.QtGui import QColor

        o = self.object_ctrl
        colour = QColor(*colour[:3])
        o.obj_list[index].set_icon_style(colour)
        o.sig_color_changed.emit((index, (colour.red(), colour.green(), colour.blue(), 255)))

    # --------------------------------------------------------------- export
    PLAN_COLUMNS = ("probe", "atlas", "entry_ap_mm", "entry_ml_mm", "entry_dv_mm",
                    "depth_mm", "tip_ap_mm", "tip_ml_mm", "tip_dv_mm", "ap_tilt_deg",
                    "ml_tilt_deg", "roll_deg", "contacts_face", "probe_type", "shanks",
                    "regions", "warnings", "coordinates")

    def plan_table_rows(self):
        """One row per plan (millimetres from Bregma; ML + is the animal's right)."""
        rows = []
        atlas_name = self.plan_atlas_name()
        for plan in self.probe_plans.plans():
            readout = self.probe_plan_readout(plan) or {}
            entry = readout.get("entry_um")
            depth = readout.get("depth_um")

            def mm(values, axis):
                return "" if values is None else round(values[axis] / 1000.0, 4)

            rows.append({
                "probe": plan.probe, "atlas": atlas_name,
                "entry_ap_mm": mm(entry, 1), "entry_ml_mm": mm(entry, 0),
                "entry_dv_mm": mm(entry, 2),
                "depth_mm": "" if depth is None else round(depth / 1000.0, 4),
                "tip_ap_mm": mm(plan.tip_um, 1), "tip_ml_mm": mm(plan.tip_um, 0),
                "tip_dv_mm": mm(plan.tip_um, 2),
                "ap_tilt_deg": round(plan.ap_tilt_deg, 3),
                "ml_tilt_deg": round(plan.ml_tilt_deg, 3),
                "roll_deg": round(plan.roll_deg, 3),
                "contacts_face": readout.get("face", ""),
                "probe_type": (plan.probe_settings or {}).get("probe_type_name", ""),
                "shanks": len(plan.shank_offsets_um or [0]),
                "regions": " | ".join("{} {:.0f}-{:.0f} um".format(
                    r["acronym"], r["start_um"], r["end_um"])
                    for r in readout.get("regions") or [] if r["id"] != 0),
                "warnings": " ".join(readout.get("warnings") or []),
                "coordinates": (coordinate_line(plan, readout, atlas_name)
                                if readout else ""),
            })
        return rows

    def export_probe_plans(self, path):
        import csv

        with open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.PLAN_COLUMNS)
            writer.writeheader()
            writer.writerows(self.plan_table_rows())
        return path

    # ---------------------------------------------------------- persistence
    def _load_probe_plans(self, p_dict):
        self.probe_plans, problems = PlanBook.from_list(p_dict.get("probe_plans"))
        if problems:
            self.print_message("{} probe plan(s) could not be restored: {}".format(
                len(problems), "; ".join(problems)), self.reminder_color)
