"""GUI-free object archive writing from a captured export snapshot."""
from pathlib import Path

from .persistence import save_driftlessmap_file
from .project_io import object_file_names


def write_objects(objects, folder):
    paths = []
    stems = object_file_names([obj['name'] for obj in objects])
    for obj, stem in zip(objects, stems):
        path = str(Path(folder) / (stem + '.dmapobj'))
        success, error = save_driftlessmap_file(path, obj, 'object')
        if not success:
            return paths, error
        paths.append(path)
    return paths, None
