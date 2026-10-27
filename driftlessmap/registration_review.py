"""User review of a registration, recorded against what was reviewed.

Review is a human decision: it says the user inspected the current landmarks
and warp, not that the registration is anatomically correct. A review is tied
to a fingerprint of the registration inputs (landmarks, frame points, atlas
plane, page and tilt, image size); any change to them makes it lapse.

States:

``not recorded``  work from before review existed, or nothing reviewed yet
                  in an older project; never treated as reviewed
``not reviewed``  the current registration has not been reviewed
``reviewed``      the user marked the current registration as reviewed
"""

import hashlib
import json
from dataclasses import dataclass

import numpy as np

REVIEWED = "reviewed"
NOT_REVIEWED = "not reviewed"
NOT_RECORDED = "not recorded"


def _points(points):
    array = np.asarray(points if points is not None else [], dtype=float).reshape(-1, 2)
    return np.round(array, 3).tolist()


def registration_fingerprint(atlas_points, histology_points, atlas_frame, histology_frame,
                             plane, page, tilt, image_shape):
    """A stable digest of the inputs a review applies to."""
    payload = {
        "atlas": _points(atlas_points),
        "histology": _points(histology_points),
        "atlas_frame": _points(atlas_frame),
        "histology_frame": _points(histology_frame),
        "plane": str(plane),
        "page": int(page) if page is not None else None,
        "tilt": [round(float(value), 4) for value in (tilt or ())],
        "image_shape": [int(value) for value in (image_shape or ())][:2],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RegistrationReview:
    fingerprint: str = ""      # what was reviewed; empty when never reviewed
    reviewed_at: str = ""      # ISO time of the review
    recorded: bool = True      # False for work loaded from before review existed

    def state(self, current_fingerprint):
        if not self.recorded and not self.fingerprint:
            return NOT_RECORDED
        if self.fingerprint and self.fingerprint == current_fingerprint:
            return REVIEWED
        return NOT_REVIEWED

    def to_dict(self):
        return {"fingerprint": self.fingerprint, "reviewed_at": self.reviewed_at,
                "recorded": self.recorded}

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return cls(recorded=False)
        if not isinstance(data, dict):
            raise ValueError("The saved registration review is not a mapping.")
        fingerprint = str(data.get("fingerprint", ""))
        if fingerprint and len(fingerprint) != 64:
            raise ValueError("The saved registration review has an invalid fingerprint.")
        return cls(fingerprint, str(data.get("reviewed_at", "")), bool(data.get("recorded", True)))
