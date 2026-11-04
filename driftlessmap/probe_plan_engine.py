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
    propose_plans,
    target_coverage,
    Craniotomy,
    CraniotomyBook,
    arm_from_tilts,
    bregma_lambda_scale,
    clearance_warning,
    clearances,
    craniotomy_warning,
    fit_craniotomy,
    validated_surgery_settings,
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
from .probe_plans import (
    FIBER,
    PRISM,
    device_lines,
    imaging_summary,
    planned_model,
    region_summary,
)
from .implants import describe_specs
from .probe_hardware import hardware_model
from .probe_utiles import calculate_probe_info, probe_error_message

PLAN_SUFFIX = " plan"
# A staged plan edit is stored and built once edits settle for this long, or at
# once before anything reads or replaces the document (review R2 of 2.8.3).
PLAN_SETTLE_MS = 500


def plan_focus_um(plan):
    """Where Show on atlas puts the pages: a probe's tip; inside a fiber just
    above its tip, and inside a prism beside its imaging face, so every page
    cuts it (the tip lies on the device's surface)."""
    tip = np.asarray(plan.tip_um, dtype=float)
    if plan.is_probe:
        return tip
    up = -plan.direction
    if plan.kind == PRISM:
        from .implants import prism_rise

        depth = plan.specs["depth_um"]
        height = min(0.75 * max(depth * prism_rise(plan.specs), 100.0),
                     plan.specs["length_um"] / 2.0)
        return tip + up * height - plan.normal * min(depth / 4.0, height * 0.5)
    return tip + up * min(plan.specs["diameter_um"] / 2.0, 250.0)


def implant_plan_lines(plan, readout, type_name):
    """A planned fiber or prism's report, as lines of text (its object's
    information window)."""
    def triple(values):
        return "AP {:+.3f} · ML {:+.3f} · DV {:+.3f} mm".format(
            values[1] / 1000.0, values[0] / 1000.0, values[2] / 1000.0)

    lines = ["Planned {} (from Bregma; ML + is the animal's right, DV + dorsal).".format(
        type_name.lower())]
    if readout.get("entry_um") is not None:
        lines.append("Entry: {}".format(triple(readout["entry_um"])))
        lines.append("Depth: {:.3f} mm along the {}".format(readout["depth_um"] / 1000.0,
                                                           plan.kind))
    lines.append("{}: {} · in {}".format(
        "Bottom of the imaging face" if plan.kind == PRISM else "Tip",
        triple(readout["tip_um"]), readout["tip_region"][1]))
    lines.append("Tilt: {}".format(readout.get("tilt", "")))
    if plan.kind == PRISM:
        lines.append("Imaging face looks {}".format(readout.get("face", "")))
        if readout.get("imaging"):
            lines.append("Face looks into: {}".format(imaging_summary(readout, limit=8)))
    regions = region_summary(readout, limit=8)
    if regions:
        lines.append("Along the axis: {}".format(regions))
    lines += ["⚠ " + warning for warning in readout.get("warnings") or []]
    return lines


def plan_object_name(probe, shank=None, shanks=1):
    name = probe + PLAN_SUFFIX
    return "{} shank {}".format(name, shank + 1) if shanks > 1 else name


class ProbePlanEngineMixin:
    def _init_probe_plans(self):
        self.probe_plans = PlanBook()
        self.craniotomies = CraniotomyBook()
        self.surgery_settings = validated_surgery_settings(None)
        self._plan_atlas = None
        self._plan_atlas_key = None
        self._plan_metadata = None
        self._plan_metadata_key = None
        # probe -> staged edit, shown and counted as unsaved work; stored and
        # built by flush_plan_edits (on settling, or before save, export, undo,
        # another action or a section switch); dropped when the document is
        # replaced.
        self.plan_previews = {}
        self.plan_candidates = {}   # probe -> proposal under inspection (display only)
        self.plan_colours = {}      # probe -> colour of its track on the atlas
        # A planned Neuropixels probe's base, flex, headstage and dovetail are
        # drawn (2.8.6); a display choice, not saved with the project.
        self.show_probe_hardware = True
        self._flushing_plans = False
        from PyQt6.QtCore import QTimer

        self._plan_settle = QTimer(self)
        self._plan_settle.setSingleShot(True)
        self._plan_settle.timeout.connect(self.flush_plan_edits)

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

    def implant_plan(self, implant_id):
        """The plan of a fiber or prism, or None."""
        implant = self.implants.get(implant_id)
        plan = self.probe_plans.get(implant.name) if implant is not None else None
        return plan if plan is not None and plan.implant_id == implant_id else None

    def default_implant_plan(self, implant_id):
        """A vertical plan for a fiber or prism to start from, placed as a probe's
        (``default_probe_plan``); a prism goes no deeper than its length allows
        and its imaging face looks the way its settings say."""
        implant = self.implants.get(implant_id)
        if implant is None:
            raise ValueError("unknown implant")
        probe = self.default_probe_plan(implant.name)
        plan = ProbePlan(implant.name, probe.tip_um, kind=implant.kind, specs=implant.specs,
                         implant_id=implant.implant_id)
        atlas = self.plan_atlas()
        if implant.kind == FIBER and atlas is not None:
            # Keep the ferrule 0.5 mm above the brain.
            readout = plan_readout(plan, atlas)
            limit = implant.specs["fiber_length_um"] - 500.0
            if readout["entry_um"] is not None and readout["depth_um"] > limit:
                plan = plan_from_entry_depth(plan, readout["entry_um"], max(limit, 250.0))
        if implant.kind == PRISM:
            side = 1.0 if plan.tip_um[0] >= 0 else -1.0
            # Roll: 0 faces anterior, 90 the animal's right.
            roll = {"anterior": 0.0, "posterior": 180.0,
                    "lateral": 90.0 if side > 0 else 270.0,
                    "medial": 270.0 if side > 0 else 90.0}[implant.specs.get("face", "lateral")]
            plan = plan.copy(roll_deg=roll)
            if atlas is not None:
                readout = plan_readout(plan, atlas)
                limit = implant.specs["length_um"] - 500.0
                if readout["entry_um"] is not None and readout["depth_um"] > limit:
                    plan = plan_from_entry_depth(plan, readout["entry_um"], max(limit, 500.0))
        return plan

    def probe_plan_readout(self, probe_or_plan, others=True):
        """The plan's readout plus the surgery checks (since 2.8.2): arm angles,
        its craniotomy, the closest other planned probe and the Bregma-Lambda
        scale. ``others=False`` leaves out the other probes (faster)."""
        plan = (probe_or_plan if isinstance(probe_or_plan, ProbePlan)
                else self.probe_plans.get(probe_or_plan))
        atlas = self.plan_atlas()
        if plan is None or atlas is None:
            return None
        readout = plan_readout(plan, atlas)
        readout["arm"] = arm_from_tilts(plan.ap_tilt_deg, plan.ml_tilt_deg)
        craniotomy = self.craniotomies.get(plan.craniotomy) if plan.craniotomy else None
        readout["craniotomy"] = craniotomy.to_dict() if craniotomy else None
        warning = craniotomy_warning(craniotomy, readout["entry_um"])
        if warning:
            readout["warnings"].append(warning)
        readout["closest"] = None
        if others:
            pairs = [pair for pair in self.plan_clearances(replace=plan)
                     if plan.probe in pair["probes"]]
            readout["closest"] = pairs[0] if pairs else None
            warning = clearance_warning(plan.probe, pairs)
            if warning:
                readout["warnings"].append(warning)
        readout["scale"] = self.surgery_scale()
        if readout["scale"] is None:
            readout["warnings"].append(
                "Bregma-Lambda scaling is set, but the atlas's Bregma-Lambda distance is "
                "unknown: no coordinates for the animal are given (enter the atlas's "
                "distance in Surgery > Bregma-Lambda distance).")
        readout["targets"] = target_coverage(plan, readout, atlas)
        readout["model"] = planned_model(plan, readout, atlas.vox_um)
        readout["hardware"] = hardware_model(plan, atlas.vox_um) \
            if self.show_probe_hardware else None
        return readout

    # ------------------------------------------------------------ proposals
    def propose_probe_plans(self, probe, request, progress=None):
        """Ranked proposals for ``probe`` (see ``probe_plans.propose_plans``),
        searched on a worker thread; ``(proposals, reasons)``. The probe's
        design, roll, bank and craniotomy are kept; each proposed plan
        carries the request's targets and regions to avoid."""
        from .background import run_in_background

        plan = self.probe_plans.get(probe) or self.default_probe_plan(probe)
        atlas = self.plan_atlas()
        if atlas is None:
            return [], ["Load a volume atlas to propose a plan."]
        base = plan.copy(targets=request.targets, avoid=request.avoid)
        if progress is not None:
            # The caller shows progress and may stop the search (in steps).
            return propose_plans(atlas, request, base, progress=progress)
        proposals, reasons = run_in_background(
            self, "Searching for probe plans...", propose_plans, atlas, request, base)
        return proposals, reasons

    def current_plans(self, replace=None):
        """Every plan, the ones being edited in place of their stored version."""
        plans = {plan.probe: plan for plan in self.probe_plans.plans()}
        plans.update(self.plan_previews)
        if replace is not None:
            plans[replace.probe] = replace
        return [plans[name] for name in sorted(plans)]

    def plan_clearances(self, replace=None):
        """Closest approach of every pair of planned probes (see ``clearances``)."""
        atlas = self.plan_atlas()
        if atlas is None:
            return []
        return clearances([(plan, plan_readout(plan, atlas))
                           for plan in self.current_plans(replace)])

    # -------------------------------------------------------------- surgery
    def surgery_scale(self):
        """Atlas-to-animal scale: 1.0 when no animal distance is set (unscaled
        by choice), None when one is set but the atlas's distance is unknown
        (the scale is unavailable, not 1.0; review R3 of 2.8.3)."""
        settings = self.surgery_settings
        if not settings.get("bregma_lambda_um"):
            return 1.0
        reference = settings.get("atlas_bregma_lambda_um") or self.atlas_bregma_lambda_um()
        if not reference:
            return None
        try:
            return bregma_lambda_scale(settings["bregma_lambda_um"], reference)
        except ValueError:
            return None

    def atlas_bregma_lambda_um(self):
        """The atlas's own Bregma-Lambda distance when it records Lambda, else None."""
        view = self.atlas_view
        lam = getattr(view, "atlas_lambda", None)
        if lam is None or view.origin_3d is None:
            return None
        return float(np.linalg.norm(np.asarray(lam, float) - np.asarray(view.origin_3d, float))
                     * view.vox_size_um)

    def set_surgery_settings(self, bregma_lambda_um=None, atlas_bregma_lambda_um=None):
        with self.undoable("Set Bregma-Lambda"):
            self.surgery_settings = validated_surgery_settings(
                {"bregma_lambda_um": bregma_lambda_um,
                 "atlas_bregma_lambda_um": atlas_bregma_lambda_um})
        return self.surgery_settings

    def add_craniotomy(self, centre_um, diameter_um, name=None):
        from .mapping_records import new_identifier

        with self.undoable("Add craniotomy"):
            craniotomy = Craniotomy(new_identifier(), name or self.craniotomies.new_name(),
                                    centre_um, diameter_um)
            return self.craniotomies.add(craniotomy)

    def edit_craniotomy(self, craniotomy_id, name=None, centre_um=None, diameter_um=None):
        old = self.craniotomies.get(craniotomy_id)
        if old is None:
            return None
        new = Craniotomy(craniotomy_id, name if name is not None else old.name,
                         centre_um if centre_um is not None else old.centre_um,
                         diameter_um if diameter_um is not None else old.diameter_um)
        with self.undoable("Edit {}".format(old.name)):
            return self.craniotomies.add(new)

    def remove_craniotomy(self, craniotomy_id):
        """Forget a craniotomy; plans through it keep their place, without it."""
        craniotomy = self.craniotomies.get(craniotomy_id)
        if craniotomy is None:
            return None
        with self.undoable("Remove {}".format(craniotomy.name)):
            for plan in self.probe_plans.plans():
                if plan.craniotomy == craniotomy_id:
                    self.probe_plans.set(plan.copy(craniotomy=None))
                    self._build_plan(plan.probe, self.plan_colours.get(plan.probe))
            return self.craniotomies.remove(craniotomy_id)

    def fit_craniotomy_to_plans(self, craniotomy_id):
        """Centre and size the craniotomy to hold the entries of its plans;
        returns the craniotomy, or None when no plan goes through it."""
        craniotomy = self.craniotomies.get(craniotomy_id)
        atlas = self.plan_atlas()
        if craniotomy is None or atlas is None:
            return None
        entries = []
        for plan in self.probe_plans.plans():
            if plan.craniotomy != craniotomy_id:
                continue
            readout = plan_readout(plan, atlas)
            if readout["entry_um"] is not None:
                # Every shank, or the rim of a fiber or the footprint of a prism.
                entries.extend(np.asarray(readout["entry_um"]) + offset
                               for _name, offset, _raised in device_lines(plan, outline=True))
        if not entries:
            return None
        centre, diameter = fit_craniotomy(entries)
        return self.edit_craniotomy(craniotomy_id, centre_um=centre, diameter_um=diameter)

    def plan_coordinate_line(self, probe):
        plan = self.probe_plans.get(probe)
        readout = self.probe_plan_readout(plan) if plan else None
        if readout is None:
            return None
        return coordinate_line(plan, readout, self.plan_atlas_name())

    def region_centre_um(self, region_id, side=None):
        atlas = self.plan_atlas()
        return None if atlas is None else region_centre(atlas, region_id, side=side)

    # --------------------------------------------------------- staged edits
    def stage_probe_plan(self, plan, colour=None):
        """Show ``plan`` at once; it is stored and built when edits settle."""
        plan.validate()
        self.plan_previews[plan.probe] = plan
        if colour is not None:
            self.plan_colours[plan.probe] = tuple(colour[:3])
        self._plan_settle.start(PLAN_SETTLE_MS)

    def flush_plan_edits(self):
        """Store and build every staged edit now (one undo step each).

        Returns ``[(ok, message)]``, one per edit that changed a plan.
        """
        if self._flushing_plans:
            return []
        self._plan_settle.stop()
        results = []
        self._flushing_plans = True
        try:
            while self.plan_previews:
                probe, plan = next(iter(self.plan_previews.items()))
                del self.plan_previews[probe]
                if plan != self.probe_plans.get(probe):
                    results.append(self.set_probe_plan(plan, self.plan_colours.get(probe)))
        finally:
            self._flushing_plans = False
        return results

    def discard_plan_edits(self):
        """Forget staged edits (the document they belong to is being replaced)."""
        self._plan_settle.stop()
        self.plan_previews.clear()
        self.plan_candidates.clear()

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
        point = atlas.to_vox(plan_focus_um(plan))
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
        if not plan.is_probe:
            return self._build_implant_plan(plan, colour, earlier)
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
            if shank == 0:
                # Drawn once, with the first shank (probe_hardware).
                info["hardware"] = hardware_model(plan, atlas.vox_um)
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

    def _build_implant_plan(self, plan, colour, earlier):
        """A planned fiber or prism as a ``merged fiber``/``merged prism`` object
        named ``"<name> plan"``; its data carries the plan and a report with
        the display model, but no ``implant_id``, so it is never taken for the
        implant built from sections."""
        from .implants import TYPE_NAMES

        readout = self.probe_plan_readout(plan, others=False)
        o = self.object_ctrl
        name = plan_object_name(plan.probe)
        info = {
            "object_type": plan.kind,
            "plan_of": plan.probe,
            "plan": plan.to_dict(),
            "data": [],
            "pieces_names": [name],
            "report": {"kind": plan.kind, "specs": dict(plan.specs), "planned": True,
                       "model": readout["model"],
                       "lines": implant_plan_lines(plan, readout,
                                                   TYPE_NAMES[plan.kind])},
        }
        if earlier:
            o.delete_objects(earlier)
        o.add_object(name, "merged " + plan.kind, object_data=info,
                     object_mode=self.obj_display_mode)
        implant = self.implants.get(plan.implant_id)
        colour = colour or (implant.colour if implant is not None else None)
        if colour is not None:
            self._colour_object(len(o.obj_name) - 1, colour)
        o.current_obj_index = len(o.obj_name) - 1
        return True, "Planned {}.".format(plan.probe)

    def set_probe_hardware_shown(self, shown):
        """Show or hide planned probes' hardware in 3D and on the atlas views."""
        self.show_probe_hardware = bool(shown)
        for item in getattr(self, "object_3d_list", []):
            hardware = getattr(item, "hardware", None)
            if hardware is not None:
                hardware.setVisible(self.show_probe_hardware)
        if getattr(self, "plan_overlay", None) is not None:
            self.plan_overlay.refresh()

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
                    "bank", "window_top_mm", "window_bottom_mm", "window_sites_in_brain",
                    "window_regions", "arm_azimuth_deg", "arm_elevation_deg", "craniotomy",
                    "closest_probe", "closest_mm", "bregma_lambda_scale", "animal_entry_ap_mm",
                    "animal_entry_ml_mm", "animal_entry_dv_mm", "animal_depth_mm", "regions",
                    "warnings", "coordinates", "device", "device_settings", "imaging_regions")

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

            factor = readout.get("scale")
            animal_entry = None if entry is None or factor is None \
                else [v * factor for v in entry]

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
                "bank": "all" if plan.bank is None else plan.bank,
                "window_top_mm": "" if not readout.get("window_um")
                else round(max(readout["window_um"][0], 0.0) / 1000.0, 4),
                "window_bottom_mm": "" if not readout.get("window_um")
                else round(readout["window_um"][1] / 1000.0, 4),
                "window_sites_in_brain": readout.get("window_sites_in_brain", ""),
                "window_regions": " | ".join("{} {:.0f} um ({} sites)".format(
                    r["acronym"], r["length_um"], r["sites"])
                    for r in readout.get("window_regions") or []),
                "arm_azimuth_deg": round(readout["arm"][0], 3) if readout.get("arm") else "",
                "arm_elevation_deg": round(readout["arm"][1], 3) if readout.get("arm") else "",
                "craniotomy": (readout.get("craniotomy") or {}).get("name", ""),
                "closest_probe": "" if not readout.get("closest") else next(
                    p for p in readout["closest"]["probes"] if p != plan.probe),
                "closest_mm": "" if not readout.get("closest")
                else round(readout["closest"]["distance_um"] / 1000.0, 4),
                "bregma_lambda_scale": "unavailable" if factor is None else round(factor, 6),
                "animal_entry_ap_mm": mm(animal_entry, 1),
                "animal_entry_ml_mm": mm(animal_entry, 0),
                "animal_entry_dv_mm": mm(animal_entry, 2),
                "animal_depth_mm": "" if depth is None or factor is None
                else round(depth * factor / 1000.0, 4),
                "regions": " | ".join("{} {:.0f}-{:.0f} um".format(
                    r["acronym"], r["start_um"], r["end_um"])
                    for r in readout.get("regions") or [] if r["id"] != 0),
                "warnings": " ".join(readout.get("warnings") or []),
                "coordinates": (coordinate_line(plan, readout, atlas_name)
                                if readout else ""),
                "device": plan.kind,
                "device_settings": "" if plan.is_probe
                else describe_specs(plan.kind, plan.specs),
                "imaging_regions": imaging_summary(readout, limit=12, minimum=0.0),
            })
            if not plan.is_probe:
                # No contacts, shanks or recording window; the face is the
                # prism's imaging face (2.8.5).
                rows[-1].update({"contacts_face": readout.get("face", "")
                                 if plan.kind == PRISM else "", "shanks": "", "bank": ""})
        return rows

    def export_probe_plans(self, path):
        import csv

        self.flush_plan_edits()
        with open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.PLAN_COLUMNS)
            writer.writeheader()
            writer.writerows(self.plan_table_rows())
        return path

    # ---------------------------------------------------------- persistence
    def _load_probe_plans(self, p_dict):
        self.craniotomies, broken = CraniotomyBook.from_list(p_dict.get("craniotomies"))
        self.surgery_settings = validated_surgery_settings(p_dict.get("surgery_settings"))
        if broken:
            self.print_message("{} craniotomy(ies) could not be restored: {}".format(
                len(broken), "; ".join(broken)), self.reminder_color)
        self.probe_plans, problems = PlanBook.from_list(p_dict.get("probe_plans"),
                                                        p_dict.get("implant_plans"))
        for plan in self.probe_plans.plans_of(implants=True):
            # A fiber or prism plan belongs to its implant: it follows the
            # implant's name and specs, and goes when the implant is missing.
            implant = self.implants.get(plan.implant_id)
            if implant is None or implant.kind != plan.kind:
                self.probe_plans.remove(plan.probe)
                problems.append("{}: its {} was not found and the plan was left out".format(
                    plan.probe, plan.kind))
                continue
            if implant.name != plan.probe or implant.specs != plan.specs:
                self.probe_plans.remove(plan.probe)
                self.probe_plans.set(plan.copy(probe=implant.name, specs=implant.specs))
        for plan in self.probe_plans.plans():
            if plan.craniotomy and self.craniotomies.get(plan.craniotomy) is None:
                self.probe_plans.set(plan.copy(craniotomy=None))
                problems.append("{}: its craniotomy was not found and was left out".format(
                    plan.probe))
        if problems:
            self.print_message("{} probe plan(s) could not be restored: {}".format(
                len(problems), "; ".join(problems)), self.reminder_color)
