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
import tempfile

from .background import run_in_background
from .project_session import ProjectSnapshot, snapshot_metadata
from .provenance import (
    describe_path,
    pack_path,
    path_stat_signature,
    resolve_reference,
    unpack_path,
    verify_reference,
)
from .sections import (
    SECTION_METADATA,
    SectionBook,
    SpillCache,
    section_state,
)


class SectionsMixin:
    """Mixed into ``DriftlessMap``."""

    def _init_sections(self):
        self.sections = SectionBook(self.section_id)
        self._section_cache = SpillCache()

    def sections_index(self):
        """The ``sections`` entry of the project payload (for change detection;
        a save replaces it with :meth:`sections_for_save`)."""
        return self.sync_sections().index()

    # ----------------------------------------------------------- listing
    def _section_default_name(self):
        if self.current_img_path:
            return os.path.basename(self.current_img_path)
        image_file = self.image_view.image_file
        names = getattr(image_file, "file_name_list", None) if image_file is not None else None
        # Readers may list full paths; a section is named after its file.
        return os.path.basename(str(names[0])) if names else ""

    def sync_sections(self):
        """Follow the open section if it was read again under a new identity."""
        name = self._section_default_name() if self.image_view.current_img is not None else None
        self.sections.follow_active(self.section_id, name)
        return self.sections

    def reset_sections(self):
        """The document was replaced: one open section."""
        self._section_cache.close()
        self._section_cache = SpillCache(self._section_cache.min_bytes)
        self.sections = SectionBook(self.section_id)
        self.sync_sections()

    def restore_sections(self, p_dict):
        """After a project was opened: its sections (schema 4), or only the
        open one for older projects."""
        self.reset_sections()
        block = p_dict.get("sections")
        book, problems = SectionBook.from_saved(block, self.section_id,
                                                self._section_default_name())
        packed = ((p_dict.get("portable_sources") or {}).get("sections") or {})
        for entry in book.entries():
            if not entry.stored:
                continue
            entry.state = self._section_cache.spill(entry.state)
            setting = entry.state.get("setting_data") or {}
            # The source is found through its provenance when it is opened.
            entry.metadata = {
                "current_img_path": None, "current_img_name": None, "save_path": None,
                "_loaded_histology_signature": None, "_temporary_histology_source": None,
                "editing_units": set(), "tri_simplices": setting.get("tri_simplices"),
                "triangulation_topology_point_count":
                    setting.get("triangulation_topology_point_count"),
            }
            entry.portable = packed.get(entry.section_id)
        self.sections = book
        self.sync_sections()
        if problems:
            self.print_message("{} section(s) could not be restored and were left out: "
                               "{}".format(len(problems), "; ".join(problems)),
                               self.reminder_color)

    def section_name(self, section_id):
        entry = self.sections.entry(section_id)
        return entry.name if entry is not None else "a section without a stored image"

    def section_position(self):
        """(number, count, name) of the open section."""
        book = self.sync_sections()
        ids = [entry.section_id for entry in book.entries()]
        return ids.index(book.active_id) + 1, len(ids), book.entry(book.active_id).name

    def object_section_names(self, index):
        """Names of the sections an object's mapped marks came from."""
        names = []
        for unit, _revision in self.object_ctrl.obj_derivation[index]:
            record = self.mapping_ledger.by_unit(unit)
            if record is not None:
                name = self.section_name(record.section_id)
                if name not in names:
                    names.append(name)
        return names

    def mapped_section_ids(self, kind=None, owner=None):
        """Sections with mapping records (of ``kind`` and ``owner``: a probe
        name or an implant id), in section order."""
        ids = {r.section_id for r in self.mapping_ledger.records()
               if (kind is None or r.kind in (kind if isinstance(kind, tuple) else (kind,)))
               and (owner is None or r.probe == owner)}
        order = [entry.section_id for entry in self.sections.entries()]
        return sorted(ids, key=lambda sid: (order.index(sid) if sid in order else len(order),
                                            sid))

    def sections_without_image(self):
        """Sections with mapping records but no stored section: mapped before
        projects kept every section, or removed with their results kept."""
        known = {entry.section_id for entry in self.sections.entries()}
        return sorted({r.section_id for r in self.mapping_ledger.records()} - known)

    def section_summary(self, entry):
        """Plane, page, landmark pairs and review of a section, for listing."""
        if entry.section_id == self.sections.active_id:
            view = self.atlas_view
            pages = {"coronal": view.current_coronal_index,
                     "sagittal": view.current_sagital_index,
                     "horizontal": view.current_horizontal_index}
            # The registration is kept so mappings made from this section can
            # be checked while it is stored (it cannot change until opened).
            return {"plane": self.atlas_display, "page": pages.get(self.atlas_display),
                    "pairs": len(self.atlas_tri_inside_data),
                    "review": self.registration_review_state(),
                    "registration": self.current_registration_fingerprint()}
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
        # Loading clears the section side only; the atlas landmarks, atlas
        # marks and layers and the warp preview were the previous section's
        # (kept with it) and must not carry over to the new one.
        self.reset_tri_points_atlas()
        self.delete_all_atlas_layer()
        self.remove_a2h_transferred_layers()
        self.working_atlas_data = self._default_working_atlas_data()
        self.atlas_mark_origin = {}
        self.refresh_kept_marks()

    # ------------------------------------------------------------- exporting
    def export_sections(self, folder):
        """Write each section's working image, landmarks and placement into
        ``folder`` (Export all results). Returns (paths, notes)."""
        import csv
        import json

        from .project_io import object_file_names
        from .sections import section_pixel_size_um, write_section_image

        self.sync_sections()
        payload = self.project_payload()
        sections = []
        for entry in self.sections.entries():
            state = section_state(payload) if entry.section_id == self.sections.active_id \
                else entry.state
            if state and state.get("img_ctrl_data") is not None:
                sections.append((entry, state))
        if not sections:
            return [], []
        os.makedirs(folder, exist_ok=True)
        paths, notes, index = [], [], []
        def stem_of(name):
            root, extension = os.path.splitext(name or "section")
            images = (".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".czi")
            return root if extension.lower() in images and root else (name or "section")

        stems = object_file_names([stem_of(entry.name) for entry, _state in sections])
        for (entry, state), stem in zip(sections, stems):
            image = state["img_ctrl_data"]
            source = image.get("source_metadata") or {}
            pixel_um = section_pixel_size_um(image)
            record = {"name": entry.name, "section_id": entry.section_id,
                      "open": entry.section_id == self.sections.active_id,
                      "pixel_size_um": pixel_um,
                      "channels": [str(n) for n in source.get("channel_name") or []]}
            raster_path = os.path.join(folder, stem + ".tif")
            try:
                write_section_image(raster_path, image["current_img"], record["channels"],
                                    pixel_um)
            except (OSError, ValueError, TypeError) as exc:
                notes.append("The image of {} was not written: {}".format(entry.name, exc))
            else:
                paths.append(raster_path)
                record["image"] = os.path.basename(raster_path)
            setting = state.get("setting_data") or {}
            pairs = list(zip(setting.get("atlas_tri_inside_data") or [],
                             setting.get("histo_tri_inside_data") or []))
            if pairs:
                landmark_path = os.path.join(folder, stem + "_landmarks.csv")
                with open(landmark_path, "w", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["pair", "atlas_x", "atlas_y", "section_x", "section_y"])
                    for number, (atlas, section) in enumerate(pairs, start=1):
                        writer.writerow([number, *atlas[:2], *section[:2]])
                paths.append(landmark_path)
                record["landmarks"] = os.path.basename(landmark_path)
            control = state.get("atlas_control") or {}
            if "atlas_display" in control:
                plane = control["atlas_display"]
                record["atlas_plane"] = plane
                record["atlas_page"] = control.get(
                    {"coronal": "coronal_index", "sagittal": "sagittal_index",
                     "horizontal": "horizontal_index"}.get(plane))
                record["atlas_tilt_deg"] = control.get("slice_rotation")
            reference = (state.get("histology_provenance") or {}).get("reference") or {}
            record["source"] = reference.get("absolute_path") or state.get("img_path")
            record["source_sha256"] = reference.get("sha256")
            index.append(record)
        index_path = os.path.join(folder, "sections.json")
        with open(index_path, "w") as stream:
            json.dump(index, stream, indent=2, default=lambda value: (
                value.tolist() if hasattr(value, "tolist") else str(value)))
        paths.append(index_path)
        return paths, notes

    # -------------------------------------------------------------- saving
    def _stored_section_provenance(self, entry, project_path):
        """(histology provenance, source changed since load) of a stored section."""
        meta = entry.metadata or {}
        path = meta.get("current_img_path")
        signature = meta.get("_loaded_histology_signature")
        previous = dict(entry.state.get("histology_provenance") or {})
        reference, changed = None, False
        if (path and os.path.exists(path) and signature is not None
                and path != meta.get("_temporary_histology_source")):
            if path_stat_signature(path) != signature:
                changed = True
            else:
                reference = describe_path(path, project_path=project_path)
        else:
            reference = previous.get("reference")
        image = entry.state["img_ctrl_data"]
        raster = image["current_img"]
        previous.update({
            "schema_version": 1,
            "reference": reference,
            "selected_scene": int(image.get("current_scene") or 0),
            "selected_page": int(image.get("current_page") or 0),
            "working_raster_embedded": True,
            "working_raster_shape": tuple(int(v) for v in raster.shape),
            "working_raster_dtype": raster.dtype.name,
            "source_changed_since_load": changed,
        })
        return previous, changed

    def sections_for_save(self, project_path, portable=False):
        """The ``sections`` block of a saved project, the packed sources of
        stored sections for a portable copy, and notes for the user.

        GUI-free (runs in the background): fingerprints and packing only.
        """
        block = self.sections.index()
        del block["stored"]
        stored, packed, notes, states = [], {}, [], {}
        for entry in self.sections.entries():
            if not entry.stored:
                continue
            provenance, changed = self._stored_section_provenance(entry, project_path)
            state = dict(entry.state, histology_provenance=provenance)
            states[entry.section_id] = state
            stored.append(entry.saved(state))
            if changed and portable:
                # As for the open section: changed bytes are never packed as
                # the original.
                raise ValueError(
                    "the original image of {} changed after it was loaded, so it cannot "
                    "be packed as its original. Restore the original file, or save a "
                    "normal project (its saved image is kept)".format(entry.name))
            if changed:
                notes.append("{}: its source changed after loading; its saved image is "
                             "kept and the changed file is not linked".format(entry.name))
            if portable:
                reference = provenance.get("reference")
                path = (entry.metadata or {}).get("current_img_path")
                if reference is not None and path and os.path.exists(path):
                    packed[entry.section_id] = pack_path(path, reference=reference)
                elif entry.portable is not None:
                    packed[entry.section_id] = entry.portable
                else:
                    notes.append("{}: its original source is unavailable; the portable "
                                 "project keeps its saved image".format(entry.name))
        block["stored"] = stored
        return block, packed, notes, states

    def sections_saved(self, states):
        """After a save: stored sections keep the provenance that was written."""
        for section_id, state in states.items():
            entry = self.sections.entry(section_id)
            if entry is not None and entry.stored:
                entry.state = state
                entry._digest = None

    # ----------------------------------------------------------- switching
    def _locate_section_source(self, entry, metadata):
        """Find a stored section's source through its provenance (after a
        project was opened); updates ``metadata`` when found."""
        reference = (entry.state.get("histology_provenance") or {}).get("reference")
        if reference is None:
            return False
        found, _ = run_in_background(self, "Finding the section's image...", resolve_reference,
                                     reference, project_path=self.current_project_path)
        if found is None and entry.portable is not None:
            folder = tempfile.TemporaryDirectory(prefix="driftlessmap-project-")
            try:
                found = unpack_path(entry.portable, folder.name)
                if not verify_reference(found, reference)[0]:
                    found = None
            except (OSError, ValueError):
                found = None
            if found is None:
                folder.cleanup()
            else:
                self._portable_source_directories.append(folder)
                metadata["_temporary_histology_source"] = found
        if found is None:
            return False
        metadata["current_img_path"] = str(found)
        metadata["current_img_name"] = os.path.basename(str(found))
        metadata["_loaded_histology_signature"] = path_stat_signature(str(found))
        return True

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
        if metadata.get("save_path") is None:
            metadata["save_path"] = self.save_path
        if metadata.get("_loaded_histology_signature") is None:
            self._locate_section_source(target, metadata)
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
        elif payload.get("img_ctrl_data") is not None:
            payload["img_path"] = path    # where the source was found
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
        records and the parts made from them.

        A built object that contains such a part is taken apart first, so the
        parts other sections contributed stay to be built again. Not undoable:
        the mapping undo history is cleared.
        """
        self.sync_sections()
        if section_id == self.sections.active_id:
            return False, "Open another section before removing this one."
        entry = self.sections.remove(section_id)
        message = "Removed {}.".format(entry.name)
        if delete_results:
            taken_apart = []
            for unit in {r.unit_id for r in self.section_mappings(section_id)}:
                taken_apart += [name for name in self._delete_results_of(unit)
                                if name not in taken_apart]
                self.mapping_ledger.forget(unit)
                self.editing_units.discard(unit)
            self.refresh_kept_marks()
            if taken_apart:
                message += (" Took apart {} (built from it too); build {} again from the "
                            "parts that are left.".format(
                                ", ".join(taken_apart),
                                "it" if len(taken_apart) == 1 else "them"))
        # Undo steps may refer to the removed section's mappings.
        self.undo_history.clear()
        self.sync_mapping_undo_actions()
        return True, message
