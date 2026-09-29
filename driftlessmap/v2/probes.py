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
        o = self.engine.object_ctrl
        return list(zip(range(len(o.obj_name)), o.obj_name, o.obj_type))

    def names(self):
        found = {probe_of(group_of(name)) for _i, name, kind in self._objects()
                 if kind in ("probe piece", "merged probe")}
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
        parts, built = len(self.parts(probe)), len(self.built(probe))
        if built and not parts:
            return "built"
        if built and parts:
            return "built · {} new section{} to add".format(parts, "" if parts == 1 else "s")
        if parts:
            return "{} section{} · not built".format(parts, "" if parts == 1 else "s")
        return "no sections yet"

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

    def new(self):
        existing = set(self.names())
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
        for index, name, _kind in self._objects():
            group = group_of(name)
            if probe_of(group) != old:
                continue
            rest = name[len(group):]
            self._set_name(index, new + group[len(old):] + rest)
        if old in self._empty:
            self._empty[self._empty.index(old)] = new
        if old in self._colours:
            self._colours[new] = self._colours.pop(old)
        return new

    def delete(self, probe):
        indexes = self.parts(probe) + self.built(probe)
        if indexes:
            self.engine.object_ctrl.delete_objects(indexes)
        if probe in self._empty:
            self._empty.remove(probe)
        self._colours.pop(probe, None)

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
        registration (the warp preview is switched on if needed); marks
        placed on the atlas are used directly.
        """
        engine = self.engine
        on_section, on_atlas = self.marks()
        if on_section == 0 and on_atlas == 0:
            return False, "Mark the track first: switch on Mark track and click along it."
        if on_section:
            if on_section < 2:
                return False, "Mark at least two points along the track."
            if not engine.h2a_transferred:
                engine.transfer_to_atlas_clicked()
                if not engine.h2a_transferred:
                    return False, ("The section could not be warped onto the atlas. Place "
                                   "or check the landmarks in the Register step.")
            engine.transform_accept()
        before = len(engine.object_ctrl.obj_name)
        engine.make_probe_piece()
        created = list(range(before, len(engine.object_ctrl.obj_name)))
        if not created:
            return False, "No part was made; see the message below the image."
        for shank, index in enumerate(created):
            name = "{} shank {} - piece".format(probe, shank + 1) if len(created) > 1 \
                else "{} - piece".format(probe)
            self._set_name(index, name)
        if probe in self._empty:
            self._empty.remove(probe)
        return True, "Added this section to {}.".format(probe)

    # ------------------------------------------------------------ build
    def build(self, probe):
        """Build ``probe`` from all its sections; returns ``(ok, message)``."""
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
