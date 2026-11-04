"""Named probes for the V2 Annotate step.

A probe is identified by the name of its parts and built object, exactly as
the 1.x engine groups probe pieces for building: a part named
``"Probe 1 - piece"`` belongs to ``Probe 1``. This module keeps that
convention but manages it for the user, so probes from several sections
combine, and different probes stay apart, without renaming anything by hand.
Every scientific step (mapping, making parts, building) is the engine's own.
"""

import re

from natsort import natsorted
from PyQt6.QtGui import QColor

PALETTE = [
    (232, 72, 85), (47, 128, 237), (39, 174, 96), (242, 153, 74),
    (155, 81, 224), (0, 184, 169), (235, 87, 170), (242, 201, 76),
]
SHANK = re.compile(r"^(?P<probe>.+?) shank (?P<shank>\d+)$")


def group_of(object_name):
    """The building group of an object name, as the engine computes it."""
    return object_name.split("-")[0].strip()


def probe_of(group):
    match = SHANK.match(group)
    return match.group("probe") if match else group


class ProbeBook:
    def __init__(self, engine):
        self.engine = engine
        self._colours = {}
        self._empty = []          # probes created but without parts yet

    # ---------------------------------------------------------- listing
    def _objects(self):
        """(index, name, kind) of every object except those built from a plan,
        which belong to their probe through ``plan_of`` (the plan engine's)."""
        o = self.engine.object_ctrl
        return [(i, name, kind) for i, (name, kind, data)
                in enumerate(zip(o.obj_name, o.obj_type, o.obj_data))
                if not (isinstance(data, dict) and data.get("plan_of") is not None)]

    def _plans(self):
        plans = getattr(self.engine, "probe_plans", None)
        return {plan.probe for plan in plans.plans_of(implants=False)} \
            if plans is not None else set()

    def plan(self, probe):
        plans = getattr(self.engine, "probe_plans", None)
        plan = plans.get(probe) if plans is not None else None
        return plan if plan is not None and plan.is_probe else None

    def names(self):
        found = {probe_of(group_of(name)) for _i, name, kind in self._objects()
                 if kind in ("probe piece", "merged probe")} | self._plans()
        for name in list(self._empty):
            if name in found:
                self._empty.remove(name)
        return natsorted(found | set(self._empty))

    def parts(self, probe):
        return [i for i, name, kind in self._objects()
                if kind == "probe piece" and probe_of(group_of(name)) == probe]

    def built(self, probe):
        return [i for i, name, kind in self._objects()
                if kind == "merged probe" and probe_of(group_of(name)) == probe]

    def colour(self, probe):
        if probe not in self._colours:
            used = set(self._colours.values())
            free = [c for c in PALETTE if c not in used] or PALETTE
            self._colours[probe] = free[0]
        return self._colours[probe]

    def summary(self, probe):
        text = self._track_summary(probe)
        if self.plan(probe) is not None:
            return "planned" if text == "no sections yet" else "planned · " + text
        return text

    def _track_summary(self, probe):
        parts, built = len(self.parts(probe)), len(self.built(probe))
        if built and not parts:
            return "built"
        if built and parts:
            return "built · {} new section{} to add".format(parts, "" if parts == 1 else "s")
        if parts:
            return "{} section{} · not built".format(parts, "" if parts == 1 else "s")
        return "no sections yet"

    # ------------------------------------------------- where the user left off
    def state(self):
        """Probes without parts yet and the colours in use, for the project."""
        return {"empty": list(self._empty),
                "colours": {name: list(colour) for name, colour in self._colours.items()}}

    def restore(self, state):
        """Restore :meth:`state`; invalid entries are skipped."""
        state = state if isinstance(state, dict) else {}
        colours = state.get("colours") if isinstance(state.get("colours"), dict) else {}
        for name, colour in colours.items():
            try:
                colour = tuple(int(c) for c in colour)
            except (TypeError, ValueError):
                continue
            if len(colour) == 3 and all(0 <= c <= 255 for c in colour):
                self._colours[str(name)] = colour
        known = set(self.names())
        for name in state.get("empty") or []:
            try:
                name = self.check_name(name)
            except ValueError:
                continue
            if name not in known:
                self._empty.append(name)
                known.add(name)
                self.colour(name)

    # ---------------------------------------------------------- editing
    @staticmethod
    def check_name(name):
        name = " ".join(str(name).split())
        if not name:
            raise ValueError("A probe needs a name.")
        if "-" in name:
            raise ValueError("Probe names cannot contain '-'.")
        if SHANK.match(name):
            raise ValueError("Probe names cannot end in 'shank' and a number.")
        return name

    def _implant_names(self):
        implants = getattr(self.engine, "implants", None)
        return {i.name for i in implants.implants()} if implants is not None else set()

    def new(self):
        existing = set(self.names()) | self._implant_names()
        number = 1
        while "Probe {}".format(number) in existing:
            number += 1
        name = "Probe {}".format(number)
        self._empty.append(name)
        self.colour(name)
        return name

    def _set_name(self, index, name):
        o = self.engine.object_ctrl
        o.obj_name[index] = name
        o.obj_list[index].text_btn.setText(name)

    def rename(self, old, new):
        new = self.check_name(new)
        if new != old and new in self.names():
            raise ValueError("There is already a probe called {}.".format(new))
        if new != old and new in self._implant_names():
            # Plans are kept by name (2.8.5): a probe and an implant cannot share one.
            raise ValueError("There is already an implant called {}.".format(new))
        ledger = getattr(self.engine, "mapping_ledger", None)
        if ledger is not None:
            ledger.rename_probe(old, new)

        def renamed(name):
            group = group_of(name)
            return new + name[len(old):] if probe_of(group) == old else name

        for index, name, kind in self._objects():
            if kind not in ("probe piece", "merged probe"):
                continue
            group = group_of(name)
            if probe_of(group) != old:
                continue
            rest = name[len(group):]
            self._set_name(index, new + group[len(old):] + rest)
            data = self.engine.object_ctrl.obj_data[index]
            if isinstance(data, dict) and "pieces_names" in data:
                data["pieces_names"] = [renamed(n) for n in data["pieces_names"]]
        if self.plan(old) is not None:
            self.engine.rename_probe_plan(old, new)
        if old in self._empty:
            self._empty[self._empty.index(old)] = new
        if old in self._colours:
            self._colours[new] = self._colours.pop(old)
        return new

    def delete(self, probe):
        indexes = self.parts(probe) + self.built(probe)
        if indexes:
            self.engine.object_ctrl.delete_objects(indexes)
        if self.plan(probe) is not None:
            self.engine.remove_probe_plan(probe)
        if probe in self._empty:
            self._empty.remove(probe)
        self._colours.pop(probe, None)
        ledger = getattr(self.engine, "mapping_ledger", None)
        if ledger is not None:
            for record in ledger.records():
                if record.kind == "probe" and record.probe == probe:
                    ledger.forget(record.unit_id)
                    self.engine.editing_units.discard(record.unit_id)
            self.engine.refresh_kept_marks()

    # ------------------------------------------------------------ marks
    def marks(self):
        engine = self.engine
        return (len(engine.working_img_data.get("img-probe") or []),
                len(engine.working_atlas_data.get("atlas-probe") or []))

    def use_colour(self, probe):
        """Draw new marks in the probe's colour."""
        self.engine.tool_box.probe_color_btn.setColor(QColor(*self.colour(probe)))

    def add_section(self, probe):
        """Map this section's marks and file them as a part of ``probe``.

        Returns ``(ok, message)``. Section marks are mapped with the current
        registration (the warp preview is switched on if needed) and kept in
        the probe's mapping record for this section; adding the section again
        replaces its earlier part. Marks placed on the atlas are used directly.
        """
        with self.engine.undoable("Add section to {}".format(probe)):
            return self._add_section(probe)

    def _add_section(self, probe):
        engine = self.engine
        on_section, on_atlas = self.marks()
        if on_section == 0 and on_atlas == 0:
            cleared = engine.cleared_edit("probe", probe)
            if cleared is not None:
                # The section's mapped track was put back for editing and deleted.
                return self.remove_section(cleared.unit_id)
            return False, "Mark the track first: switch on Mark track and click along it."
        if on_section:
            if on_section < 2:
                return False, "Mark at least two points along the track."
            if not engine.h2a_transferred:
                engine.transfer_to_atlas_clicked()
                if not engine.h2a_transferred:
                    return False, ("The section could not be warped onto the atlas. Place "
                                   "or check the landmarks in the Register step.")
            engine.transform_accept(probe=probe)
        # A plan (no section loaded) is a single part: new points replace it.
        planning = engine.image_view.image_file is None
        earlier = self.parts(probe) + self.built(probe) if planning else []
        if not self.file_parts(probe):
            return False, "No part was made; see the message below the image."
        if earlier:
            engine.object_ctrl.delete_objects(earlier)
            return True, "Replaced the earlier plan of {}; build it again.".format(probe)
        return True, "Added this section to {}.".format(probe)

    def file_parts(self, probe):
        """Make parts from the atlas probe marks and file them under ``probe``."""
        created = self.engine.make_pieces_of("probe")
        for shank, index in enumerate(created):
            name = "{} shank {} - piece".format(probe, shank + 1) if len(created) > 1 \
                else "{} - piece".format(probe)
            self._set_name(index, name)
        if created and probe in self._empty:
            self._empty.remove(probe)
        return created

    def remove_section(self, unit_id):
        """Remove a mapping and what was made from it; a probe left without
        parts stays listed. Returns ``(ok, message)``."""
        engine = self.engine
        record = engine.mapping_ledger.by_unit(unit_id)
        probe = record.probe if record is not None and record.kind == "probe" else None
        result = engine.remove_mapping(unit_id)
        if result is None:
            return False, "The mapping could not be removed; see the message below the image."
        if probe and probe not in self.names():
            self._empty.append(probe)
        return True, result[1]

    def update_section(self, unit_id):
        """Update a probe section's mapping and replace its part."""
        with self.engine.undoable("Update mapping"):
            return self._update_section(unit_id)

    def _update_section(self, unit_id):
        record = self.engine.update_mapping(unit_id)
        if record is None:
            return False, "The mapping could not be updated; see the message below the image."
        if record.kind in ("fiber", "prism"):
            return True, ("Updated the mapping of {} on this section; build it again to use "
                          "it.".format(self.engine.implant_record_name(record)))
        if record.kind == "probe" and record.probe:
            if not self.file_parts(record.probe):
                return False, "Mapped again, but no part was made."
            return True, ("Updated this section of {}; build it again to use the new "
                          "part.".format(record.probe))
        return True, "Mapping updated. Make parts again to replace the earlier parts."

    # ------------------------------------------------------------ build
    def build(self, probe):
        """Build ``probe`` from all its sections; returns ``(ok, message)``."""
        with self.engine.undoable("Build {}".format(probe)):
            return self._build(probe)

    def _build(self, probe):
        engine = self.engine
        o = engine.object_ctrl
        if not self.parts(probe) and not self.built(probe):
            return False, "Add at least one section to {} first.".format(probe)
        # Rebuild from every section: restore the parts of an earlier build.
        for index in sorted(self.built(probe), reverse=True):
            o.current_obj_index = index
            o.unmerge_objects()
        groups = sorted({group_of(o.obj_name[i]) for i in self.parts(probe)})
        engine.merge_probes(only=groups)
        built, left = self.built(probe), self.parts(probe)
        if not built or left:
            return False, "{} could not be built; see the message below the image.".format(probe)
        colour = QColor(*self.colour(probe))
        for index in built:
            o.obj_list[index].set_icon_style(colour)
            o.sig_color_changed.emit((index, (colour.red(), colour.green(), colour.blue(), 255)))
        o.current_obj_index = built[-1]
        return True, "Built {}.".format(probe)

    def select_built(self, probe):
        built = self.built(probe)
        if built:
            self.engine.object_ctrl.current_obj_index = built[-1]
        return bool(built)
