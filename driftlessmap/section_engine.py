"""Sections of a project in the engine: add, open (switch), rename, remove.

See ``multi_section_design.md``. Switching installs a payload made of the
document's current fields and the target section's stored fields through the
same :class:`ProjectSnapshot` restore that opening a project uses for
recovery, so a failed switch restores the previous state exactly. The
section's own ``section_id`` comes back with it, so its mapping records are
current again and mapping it once more replaces its earlier part.
"""

import copy
import os

from .project_session import ProjectSnapshot, snapshot_metadata
from .provenance import path_stat_signature
from .sections import SECTION_METADATA, SectionBook, SpillCache, section_state


class SectionsMixin:
    """Mixed into ``DriftlessMap``."""

    def _init_sections(self):
        self.sections = SectionBook(self.section_id)
        self._section_cache = SpillCache()

    # ----------------------------------------------------------- listing
    def _section_default_name(self):
        if self.current_img_path:
            return os.path.basename(self.current_img_path)
        image_file = self.image_view.image_file
        names = getattr(image_file, "file_name_list", None) if image_file is not None else None
        return names[0] if names else ""

    def sync_sections(self):
        """Follow the open section if it was read again under a new identity."""
        name = self._section_default_name() if self.image_view.current_img is not None else None
        self.sections.follow_active(self.section_id, name)
        return self.sections

    def reset_sections(self):
        """A project was opened or the document replaced: one open section."""
        self._section_cache.close()
        self.sections = SectionBook(self.section_id)
        self.sync_sections()

    def section_summary(self, entry):
        """Plane, page, landmark pairs and review of a section, for listing."""
        if entry.section_id == self.sections.active_id:
            view = self.atlas_view
            pages = {"coronal": view.current_coronal_index,
                     "sagittal": view.current_sagital_index,
                     "horizontal": view.current_horizontal_index}
            return {"plane": self.atlas_display, "page": pages.get(self.atlas_display),
                    "pairs": len(self.atlas_tri_inside_data),
                    "review": self.registration_review_state()}
        return dict(entry.summary)

    def section_mappings(self, section_id):
        """Mapping records made on ``section_id``."""
        return [r for r in self.mapping_ledger.records() if r.section_id == section_id]

    # ------------------------------------------------------- putting away
    def _collect_open_section(self):
        """The open section's stored form: (state, metadata, summary)."""
        payload = self.project_payload()
        state = self._section_cache.spill(section_state(payload))
        metadata = {name: snapshot_metadata(getattr(self, name, None))
                    for name in SECTION_METADATA}
        summary = self.section_summary(self.sections.entry(self.sections.active_id))
        return state, metadata, summary

    def begin_new_section(self):
        """Before loading an image as a new section: the open one's stored form,
        or None when no section is open (the image then becomes the first)."""
        if self.image_view.current_img is None:
            return None
        self.sync_sections()
        return self._collect_open_section()

    def finish_new_section(self, stored):
        """After an image was loaded as a new section."""
        if stored is None:
            self.sync_sections()
            return
        self.sections.put_away(*stored)
        self.sections.add(self.section_id, self._section_default_name())

    # ----------------------------------------------------------- switching
    def switch_section(self, section_id):
        """Open another section of the project; returns (ok, message)."""
        self.sync_sections()
        book = self.sections
        if section_id == book.active_id:
            return True, ""
        target = book.entry(section_id)
        if target is None or not target.stored:
            return False, "That section is not in the project."
        try:
            rollback = ProjectSnapshot(self)
            stored = self._collect_open_section()
        except Exception as exc:
            return False, "The open section could not be put away ({}).".format(exc)
        previous_id = book.active_id

        payload = dict(rollback.payload)
        for key in section_state(payload):
            payload.pop(key)
        payload.update(target.state)
        metadata = dict(rollback.metadata)
        metadata.update(copy.deepcopy(target.metadata))
        metadata["action_list"], metadata["action_id"] = [], 0
        path = metadata.get("current_img_path")
        signature = metadata.get("_loaded_histology_signature")
        if payload.get("img_ctrl_data") is not None and not (
                path and os.path.isfile(path) and signature is not None
                and path_stat_signature(path) == signature):
            # The source is gone or changed: open the section's exact raster,
            # and do not link the work to whatever file is there now.
            payload["_histology_load_mode"] = "embedded"
            metadata["current_img_path"] = None
            metadata["_loaded_histology_signature"] = None
        install = copy.copy(rollback)
        install.payload = payload
        install.metadata = metadata
        install.sources = dict(rollback.sources, image_reader=None, volume_img=None,
                               keep_atlas=self.current_atlas == "volume")
        install.undo = copy.copy(self.undo_history)
        install.undo._undo, install.undo._redo = [], []

        self._project_loading = True
        try:
            book.put_away(*stored)
            book.activate(section_id)
            install.restore(self)
            self.section_id = section_id
        except Exception as exc:
            try:
                rollback.restore(self)
            finally:
                book.active_id = previous_id
                book.opened(previous_id)
            return False, "The section could not be opened ({}); the previous one is " \
                          "open again.".format(exc)
        finally:
            self._project_loading = False
        book.opened(section_id)
        note = "" if payload.get("_histology_load_mode") != "embedded" else \
            " Its source file was missing or changed, so its saved image was used."
        return True, "Opened {}.{}".format(target.name, note)

    # ------------------------------------------------------------ editing
    def rename_section(self, section_id, name):
        self.sync_sections()
        return self.sections.rename(section_id, name)

    def remove_section(self, section_id, delete_results=False):
        """Remove a stored section; with ``delete_results`` also its mapping
        records and the parts and built objects made from them."""
        self.sync_sections()
        if section_id == self.sections.active_id:
            return False, "Open another section before removing this one."
        entry = self.sections.remove(section_id)
        if delete_results:
            units = {r.unit_id for r in self.section_mappings(section_id)}
            o = self.object_ctrl
            doomed = [index for index, origin in enumerate(o.obj_derivation)
                      if any(unit in units for unit, _revision in origin)]
            if doomed:
                o.delete_objects(doomed)
            for unit in units:
                self.mapping_ledger.forget(unit)
            self.refresh_kept_marks()
        return True, "Removed {}.".format(entry.name)
