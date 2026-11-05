"""Export orchestration through the shared application operations interface."""
import os
from .probe_csv import write_probe_csv_files


def export_all_results(engine, folder):
    """Export every available result into ``folder`` (created if needed).

    Staged plan edits are stored and built first.

    Writes a copy of the project, each built object as ``.dmapobj``
    (``objects/``), the localisation CSVs of each probe (``probes/``),
    the implant table, every section's working image, landmarks and
    placement (``sections/``) and every layer (``layers/``). The project being
    worked on keeps its own file. Returns ``(paths, notes)``: the files
    written and what was left out and why. Raises OSError when the
    folder cannot be created.
    """
    engine.flush_plan_edits()
    os.makedirs(folder, exist_ok=True)
    paths, notes = [], []
    o = engine.document.objects
    stem = (os.path.splitext(os.path.basename(engine.current_project_path))[0]
            if getattr(engine, "current_project_path", None) else "project")
    project = os.path.join(folder, "{}.dmap".format(stem))
    if engine.save_project_called(path=project, as_copy=True):
        paths.append(project)
    else:
        notes.append("The project copy was not saved; see the message below the image.")

    built = [i for i, kind in enumerate(o.obj_type) if kind.startswith("merged")]
    stale = engine.out_of_date_lines(built)
    if stale:
        notes.append("These exported results are out of date; fix them before using them "
                     "as current results:\n" + "\n".join(stale))
    unverified = engine.unverified_lines(built)
    if unverified:
        notes.append("These exported results could not be verified as current (the files "
                     "record \"not verified\"):\n" + "\n".join(unverified))
    old_probes = [i for i in built if o.obj_type[i] == "merged probe"
                  and "reconstruction" not in o.obj_data[i]]
    if old_probes:
        notes.append("Not exported, build again first (older probes without "
                     "reconstruction data): {}.".format(
                         ", ".join(o.obj_name[i] for i in old_probes)))
    built = [i for i in built if i not in old_probes]
    unbuilt = sum(1 for kind in o.obj_type if not kind.startswith("merged"))
    if unbuilt:
        notes.append("{} unbuilt part{} are in the project only.".format(
            unbuilt, " is" if unbuilt == 1 else "s"))
    if built:
        try:
            provenance = engine.get_object_export_provenance()
        except (OSError, ValueError) as exc:
            provenance = None
            notes.append("Objects not exported: the atlas could not be "
                         "fingerprinted ({}).".format(exc))
        if provenance is not None:
            objects = os.path.join(folder, "objects")
            os.makedirs(objects, exist_ok=True)
            written, error = engine._write_object_files(built, objects, provenance)
            paths.extend(written)
            if error is not None:
                notes.append(error)
            engine._note_out_of_date_export(built)

    probes = [i for i in built if o.obj_type[i] == "merged probe"]
    if probes:
        probe_folder = os.path.join(folder, "probes")
        os.makedirs(probe_folder, exist_ok=True)
        for index, file_stem in zip(probes, engine._object_file_names(
                [o.obj_name[i] for i in probes])):
            try:
                written = write_probe_csv_files(
                    os.path.join(probe_folder, "{}.csv".format(file_stem)),
                    o.obj_name[index], o.obj_data[index])
            except (KeyError, OSError, TypeError, ValueError) as exc:
                notes.append("Probe CSVs of {} not written: {}".format(
                    o.obj_name[index], exc))
                continue
            paths.extend(str(path) for path in written.values())

    if any(engine.implant_report(i.implant_id) for i in engine.implants.implants()) or probes:
        table = os.path.join(folder, "implants.csv")
        engine.export_implant_table(table)
        paths.append(table)

    if len(engine.probe_plans):
        table = os.path.join(folder, "probe_plans.csv")
        engine.export_probe_plans(table)
        paths.append(table)

    # Every section's working image, landmarks and atlas placement: the
    # images the exported results were mapped from.
    written, section_notes = engine.export_sections(os.path.join(folder, "sections"))
    paths.extend(written)
    notes.extend(section_notes)

    if engine.layer_ctrl.layer_link:
        layers = os.path.join(folder, "layers")
        os.makedirs(layers, exist_ok=True)
        before = set(os.listdir(layers))
        if not engine.save_all_layer(path=os.path.join(layers, "layer")):
            notes.append("Some layers were not saved; see the message below the image.")
        paths.extend(os.path.join(layers, name)
                     for name in sorted(set(os.listdir(layers)) - before))
    return paths, notes

