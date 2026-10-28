"""In-memory recovery for project replacement, independent of source files.

Loading can replace arrays but must not mutate the old document's arrays.
Keep those arrays by reference and copy mutable metadata; no second atlas
volume or portable-source archive is allocated for the recovery snapshot.
"""

import copy
from pathlib import Path
import tempfile

import numpy as np
import pyqtgraph.opengl as gl

from .project_io import PROJECT_SCHEMA_VERSION
from .persistence import save_driftlessmap_file
from .version import __version__


def snapshot_metadata(value):
    if isinstance(value, np.ndarray):
        return value
    if isinstance(value, dict):
        return {key: snapshot_metadata(item) for key, item in value.items()}
    if isinstance(value, list):
        return [snapshot_metadata(item) for item in value]
    if isinstance(value, tuple):
        return tuple(snapshot_metadata(item) for item in value)
    return copy.deepcopy(value)


class ProjectSnapshot:
    """The current document, including runtime sources and undo history."""

    def __init__(self, engine):
        self.payload = snapshot_metadata(engine.project_payload())
        view = engine.atlas_view
        volume = None
        if view.atlas_data is not None:
            volume = (
                view.atlas_data, view.atlas_label,
                [view.anterior_info, view.dorsal_info, view.right_info,
                 {"vxsize": view.vox_size_um, "Bregma": view.origin_3d.copy()}],
                view.label_info, view.atlas_boundary,
                view.mesh.opts["meshdata"],
                {key: mesh.opts["meshdata"] for key, mesh in engine.small_mesh_list.items()},
            )
        self.sources = {"volume": volume, "image_reader": engine.image_view.image_file,
                        "volume_img": engine.image_view.volume_img}
        self.metadata = {name: snapshot_metadata(getattr(engine, name)) for name in (
            "current_project_path", "current_img_path", "current_img_name", "save_path",
            "volume_atlas_path", "slice_atlas_path", "volume_atlas_axis_info",
            "_loaded_atlas_signatures", "_loaded_histology_signature",
            "_temporary_histology_source", "editing_units", "action_list", "action_id",
            "tri_simplices", "triangulation_topology_point_count",
        )}
        self.undo = copy.copy(engine.undo_history)
        self.undo._undo = list(engine.undo_history._undo)
        self.undo._redo = list(engine.undo_history._redo)

    def restore(self, engine):
        engine._clear_project_objects()
        for name, value in self.metadata.items():
            setattr(engine, name, value)
        engine._restore_project_payload(self.payload, runtime=self.sources)
        for name, value in self.metadata.items():
            setattr(engine, name, value)
        engine.undo_history = self.undo
        engine.triangulation_registration = None
        engine.sync_mapping_undo_actions()
        engine.refresh_kept_marks()


class ProjectSessionMixin:
    """Shared project collection and replacement for both interfaces."""

    def project_payload(self):
        """Collect the complete saved state without writing or hashing source files.

        Arrays are borrowed, not copied; callers retaining this across mutations
        must take a snapshot. Saving and unsaved-change detection share this list.
        """
        atlas_provenance = self.atlas_provenance
        histology_provenance = self.histology_provenance
        portable_sources = None
        saved_at = None
        if self.current_atlas == "slice":
            atlas_ctrl_data = self.atlas_view.save_slice_data_and_info()
        else:
            atlas_rotation = self.atlas_view.get_atlas_angles()
            atlas_ctrl_data = {
                "atlas_display": self.atlas_display,
                "coronal_index": self.atlas_view.current_coronal_index,
                "sagittal_index": self.atlas_view.current_sagital_index,
                "horizontal_index": self.atlas_view.current_horizontal_index,
                "slice_rotation": atlas_rotation,
            }

        if self.image_view.current_img is not None:
            img_ctrl_data = self.image_view.get_img_ctrl_data()
        else:
            img_ctrl_data = None

        setting_data = self.get_setting_data()

        tool_data = self.tool_box.get_tool_data()

        if self.layer_ctrl.layer_link:
            layer_data = self.layer_ctrl.get_layer_data()
            all_2d_data = []
            cells_symbol_atlas = None
            cells_symbol_img = None
            for single_layer_link in self.layer_ctrl.layer_link:
                if "atlas" in single_layer_link:
                    data_2d = self.get_atlas_single_layer_vis_data(
                        single_layer_link
                    )
                    if "cells" in single_layer_link:
                        cells_symbol_atlas = data_2d["symbol"]
                else:
                    data_2d = self.get_hist_single_layer_vis_data(single_layer_link)
                    if "cells" in single_layer_link:
                        cells_symbol_img = data_2d["symbol"]
                all_2d_data.append(data_2d["data"])
            layer_data["2d_data"] = all_2d_data
            layer_data["cells_symbol_atlas"] = cells_symbol_atlas
            layer_data["cells_symbol_img"] = cells_symbol_img
        else:
            layer_data = None

        if self.object_ctrl.obj_name:
            object_data = self.object_ctrl.get_obj_data()
            # object_data["object_3d_list"] = [
            #     [] for _ in range(len(self.object_3d_list))
            # ]
        else:
            object_data = None

        probe_planning = self.get_probe_planning_data()
        probe_settings = probe_planning["probe_settings"]

        project_data = {
            "project_schema_version": PROJECT_SCHEMA_VERSION,
            "software": {"name": "DriftlessMap", "version": __version__},
            "created_at": self.project_created_at,
            "saved_at": saved_at,
            "portable": bool(portable_sources),
            "portable_sources": portable_sources,
            "atlas_provenance": atlas_provenance,
            "histology_provenance": histology_provenance,
            "session_state": {
                "current_layout": self.current_layout,
                "layer_shift_val": self.layer_shift_val,
                "layer_rotate_val": self.layer_rotate_val,
                "display_mode_3d": self.display_mode_3d,
                "display_mode_2d": self.display_mode_2d,
                "planes_visible": self.is_planes_on,
                "axes_visible": self.is_axis_on,
                "grids_visible": self.is_grids_on,
                "object_display_mode": self.obj_display_mode,
            },
            "atlas_path": self.current_atlas_path,
            "img_path": (
                histology_provenance.get("reference", {}).get("absolute_path")
                if self.current_img_path == self._temporary_histology_source
                and histology_provenance is not None
                and histology_provenance.get("reference") is not None
                else self.current_img_path
            ),
            "current_atlas": self.current_atlas,
            "num_windows": self.num_windows,
            "probe_settings": probe_settings,
            "probe_planning": probe_planning,
            "registration_input": (
                self.registration_input.to_dict()
                if self.registration_input is not None else None
            ),
            "registration_review": self.registration_review.to_dict(),
            "mapping_review_state": self.mapping_review_state,
            "section_id": self.section_id,
            "mapping_records": self.mapping_ledger.to_list(),
            "atlas_mark_origin": self.atlas_mark_origin,
            "implants": self.implants.to_list(),
            "implant_outlines": self.implant_outlines,
            "interface_state": self._interface_state_for_save(),
            "np_onside": self.np_onside,
            "processing_slice": self.atlas_view.processing_slice,
            "processing_img": self.image_view.processing_img,
            "overlay_img": self.overlay_img,
            "atlas_control": atlas_ctrl_data,
            "img_ctrl_data": img_ctrl_data,
            "setting_data": setting_data,
            "tool_data": tool_data,
            "layer_data": layer_data,
            "working_img_data": self.working_img_data,
            "working_atlas_data": self.working_atlas_data,
            "object_data": object_data,
        }
        return project_data

    def _clear_project_objects(self):
        """Remove rendered objects and layers before installing a document."""
        self.object_ctrl.clear_all()
        for item in self.object_3d_list:
            if not isinstance(item, list):
                self.view3d.removeItem(item)
                item.deleteLater()
        self.object_3d_list.clear()
        if self.atlas_view.atlas_data is not None:
            self.delete_all_atlas_layer()
        self.image_view.clear_image_stacks()
        self.layer_ctrl.clear_all()

    def load_project(self, p_dict, *, project_path=None):
        """Replace the document atomically; restore the current work on failure."""
        try:
            snapshot = getattr(self, "_project_recovery", None) or ProjectSnapshot(self)
        except Exception as exc:
            self.print_message("The current work could not be preserved ({}); no project "
                               "was replaced.".format(exc), self.error_message_color)
            return False
        self._project_loading = True
        try:
            image = p_dict.get("img_ctrl_data")
            if image is not None:
                pixels = np.asarray(image.get("current_img"))
                if pixels.ndim not in (2, 3) or not pixels.size or min(pixels.shape[:2]) < 1:
                    raise ValueError("The project's active raster is empty or invalid.")
            self._clear_project_objects()
            if project_path is not None:
                self.current_project_path = project_path
            self._restore_project_payload(p_dict)
        except Exception as exc:
            try:
                snapshot.restore(self)
            except Exception as recovery_error:
                # Keep the complete snapshot available even if a widget cannot
                # be restored (e.g. a native rendering failure).
                self._project_recovery = snapshot
                self.current_project_path = snapshot.metadata["current_project_path"]
                recovery_note = "The previous work is retained in memory."
                try:
                    recovery_path = Path(tempfile.mkdtemp(prefix="driftlessmap-recovery-")) / "previous.dmap"
                    saved, error = save_driftlessmap_file(recovery_path, snapshot.payload, "project")
                    if saved:
                        self._project_recovery_path = str(recovery_path)
                        recovery_note = "Open the preserved project at {}.".format(recovery_path)
                    else:
                        recovery_note += " Recovery file could not be written: {}.".format(error)
                except OSError as save_error:
                    recovery_note += " Recovery file could not be written: {}.".format(save_error)
                self.print_message("Project opening failed ({}); recovery could not finish "
                                   "({}). {} Saving this partial session is disabled.".format(
                                       exc, recovery_error, recovery_note), self.error_message_color)
                return False
            self.print_message("Project opening failed ({}). Your previous project and "
                               "unsaved work have been restored.".format(exc),
                               self.error_message_color)
            return False
        finally:
            self._project_loading = False
        self.__dict__.pop("_project_recovery", None)
        self.__dict__.pop("_project_recovery_path", None)
        self.print_message("Project loaded successfully.", self.normal_color)
        if callable(self.on_project_loaded):
            try:
                self.on_project_loaded(self.interface_state)
            except Exception as exc:
                self.print_message("The project is loaded, but where you left off "
                                   "could not be restored: {}".format(exc),
                                   self.reminder_color)
        return True

    def _clear_project_atlas(self):
        view = self.atlas_view
        if view.atlas_data is not None:
            view.clear_all_display_obj()
        for mesh in self.small_mesh_list.values():
            self.view3d.removeItem(mesh)
        self.small_mesh_list.clear()
        view.mesh.setMeshData(meshdata=gl.MeshData())
        view.mesh.resetTransform()
        view.atlas_data = view.atlas_label = view.slice_image_data = None
        view.origin_3d = view.rotate_origin_3d = view.Bregma = None
        view.slice_size = view.vox_size_um = view.atlas_size = None
        view.current_coronal_index = view.current_sagital_index = view.current_horizontal_index = None
        view.coronal_rads = view.sagittal_rads = view.horizontal_rads = (0, 0)
        self.volume_atlas_path = self.slice_atlas_path = None
        self.volume_atlas_axis_info = None
        for stack in (view.cimg, view.simg, view.himg):
            stack.img.clear()
        view.slice_stack.img_layer.clear()
        self.atlascontrolpanel.setEnabled(False)
        self.treeviewpanel.setEnabled(False)

