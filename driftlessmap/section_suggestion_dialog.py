"""Dialog presenting automatic atlas section suggestions for confirmation."""

import cv2
import numpy as np
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QVBoxLayout,
)

from .atlas_matching import (
    atlas_slice,
    histology_gray,
    mirror_hemisphere,
    mirrored_index,
    mirrored_tilt,
    tilted_slice,
)

THUMB_WIDTH = 220
THUMB_HEIGHT = 130


def _pixmap(gray):
    gray = np.ascontiguousarray(
        cv2.normalize(np.asarray(gray, dtype=np.float32), None, 0, 255, cv2.NORM_MINMAX)
        .astype(np.uint8)
    )
    height, width = gray.shape
    image = QImage(gray.data, width, height, width, QImage.Format.Format_Grayscale8)
    return QPixmap.fromImage(image.copy())


def _fit(gray, box=(THUMB_WIDTH, THUMB_HEIGHT)):
    height, width = gray.shape[:2]
    scale = min(box[0] / width, box[1] / height)
    return cv2.resize(np.asarray(gray, dtype=np.float32),
                      (max(1, int(width * scale)), max(1, int(height * scale))),
                      interpolation=cv2.INTER_AREA)


def _pair(left, right):
    """Section and atlas side by side, each centred in its half."""
    canvas = np.zeros((THUMB_HEIGHT, 2 * THUMB_WIDTH + 6), np.float32)
    for image, x0 in ((_fit(left), 0), (_fit(right), THUMB_WIDTH + 6)):
        oy = (THUMB_HEIGHT - image.shape[0]) // 2
        ox = x0 + (THUMB_WIDTH - image.shape[1]) // 2
        canvas[oy:oy + image.shape[0], ox:ox + image.shape[1]] = image / max(image.max(), 1)
    return canvas


class SectionSuggestionDialog(QDialog):
    """Lists suggestions; ``choice()`` returns the confirmed placement."""

    def __init__(self, report, histology, intensity_volume, pivot, voxel_um, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Suggest Atlas Section")
        self.report = report
        self.intensity_volume = intensity_volume
        self.pivot = pivot
        self.voxel_um = float(voxel_um)
        best = report.plane_candidates[0]
        self.plane = best.plane

        summary = ", ".join(
            "{} {:.2f}".format(candidate.plane, candidate.silhouette)
            for candidate in report.plane_candidates
        )
        confidence = (
            "clear" if report.plane_margin >= 0.08
            else "uncertain; check the plane" if report.plane_margin >= 0.03
            else "ambiguous; the plane may be wrong"
        )
        header = QLabel(
            "<b>{}</b> section ({}). Outline match by plane: {}.<br>"
            "Section orientation: {}. Candidates are ranked by outline and "
            "internal anatomy; compare the thumbnails (left: your section, "
            "right: atlas) and choose the best.".format(
                self.plane.capitalize(), confidence, summary, best.orientation.describe()
            )
        )
        header.setWordWrap(True)

        self.hemisphere_group = QButtonGroup(self)
        hemisphere_row = QHBoxLayout()
        hemisphere_row.addWidget(QLabel("Hemisphere:"))
        for number, text in enumerate(("As suggested", "Other hemisphere")):
            button = QRadioButton(text)
            button.setChecked(number == 0)
            self.hemisphere_group.addButton(button, number)
            hemisphere_row.addWidget(button)
        hemisphere_row.addStretch(1)
        hemisphere_note = QLabel(
            "Brain outlines are left-right symmetric, so the hemisphere cannot "
            "be detected automatically."
        )
        hemisphere_note.setWordWrap(True)

        self.apply_tilt = QCheckBox("Apply the suggested cutting-angle tilt")
        self.apply_tilt.setChecked(True)
        self.rotate_histology = QCheckBox(
            "Rotate/flip the histology to match ({}); this resets histology "
            "landmarks".format(best.orientation.describe())
        )
        self.rotate_histology.setChecked(
            best.orientation.quarter_turns != 0 or best.orientation.mirrored
        )

        section = best.orientation.apply(histology_gray(histology))
        self.list = QListWidget()
        self.list.setIconSize(QSize(2 * THUMB_WIDTH + 6, THUMB_HEIGHT))
        for suggestion in report.suggestions:
            atlas = self._atlas_image(suggestion.index, suggestion.tilt_degrees)
            item = QListWidgetItem(QIcon(_pixmap(_pair(section, atlas))), self._label(suggestion))
            item.setData(Qt.ItemDataRole.UserRole, suggestion)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(header)
        layout.addWidget(self.list, 1)
        layout.addLayout(hemisphere_row)
        layout.addWidget(hemisphere_note)
        layout.addWidget(self.apply_tilt)
        layout.addWidget(self.rotate_histology)
        layout.addWidget(buttons)
        self.resize(700, 640)

    def _atlas_image(self, index, tilt):
        if tuple(tilt) == (0.0, 0.0):
            return atlas_slice(self.intensity_volume, self.plane, index)
        return tilted_slice(self.intensity_volume, self.plane, index, tilt, self.pivot)

    def _label(self, suggestion):
        if self.plane == "sagittal" and self.report.midline is not None:
            where = "{:.2f} mm lateral".format(
                abs(suggestion.index - self.report.midline) * self.voxel_um / 1000
            )
        else:
            where = "slice {}".format(suggestion.index)
        return "{}\ntilt ({:+.0f}°, {:+.0f}°)   score {:.2f}".format(
            where, suggestion.tilt_degrees[0], suggestion.tilt_degrees[1], suggestion.score
        )

    def choice(self):
        """Return (plane, index, orientation, tilt, rotate_histology) or None."""
        item = self.list.currentItem()
        if item is None:
            return None
        suggestion = item.data(Qt.ItemDataRole.UserRole)
        index, orientation = suggestion.index, suggestion.orientation
        tilt = suggestion.tilt_degrees if self.apply_tilt.isChecked() else (0.0, 0.0)
        if self.hemisphere_group.checkedId() == 1:
            tilt = mirrored_tilt(self.plane, tilt)
            if self.plane == "sagittal" and self.report.midline is not None:
                index = mirrored_index(index, self.report.midline)
            else:
                orientation = mirror_hemisphere(self.plane, orientation)
        return self.plane, index, orientation, tilt, self.rotate_histology.isChecked()
