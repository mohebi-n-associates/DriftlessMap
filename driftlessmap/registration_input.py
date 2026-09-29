"""The histology input used by automatic section matching and landmark proposal.

Display settings (visibility, colours, levels, gamma, LUT curves) never enter
this input. A :class:`RegistrationInput` recipe names the source channels
explicitly, so a section can be registered on DAPI alone while tracer or GFP
channels stay visible for annotation.

Two modes exist:

``legacy``
    The raw active image is passed unchanged, reproducing DriftlessMap 1.6:
    the tissue mask takes the maximum over every min-max normalised channel,
    and the intensity image averages the first three raw channels.

``channels``
    Each selected channel is normalised to [0, 1] between robust percentile
    bounds, and the selected channels are averaged into one analysis plane that
    both automatic stages use.
"""

from dataclasses import dataclass

import numpy as np

RECIPE_VERSION = 1
DEFAULT_PERCENTILES = (0.5, 99.5)
MODES = ("legacy", "channels")


@dataclass(frozen=True)
class RegistrationInput:
    mode: str = "legacy"
    channels: tuple = ()          # source channel indices
    channel_names: tuple = ()     # names when chosen, for display and checks
    percentiles: tuple = DEFAULT_PERCENTILES
    version: int = RECIPE_VERSION

    @classmethod
    def legacy(cls):
        return cls("legacy")

    @classmethod
    def from_channels(cls, channels, names=None, percentiles=DEFAULT_PERCENTILES):
        channels = tuple(int(c) for c in channels)
        if not channels:
            raise ValueError("Select at least one registration channel.")
        if len(set(channels)) != len(channels):
            raise ValueError("A registration channel was selected twice.")
        names = tuple(str(n) for n in names) if names is not None else ()
        if names and len(names) != len(channels):
            raise ValueError("Each registration channel needs one name.")
        return cls("channels", channels, names, tuple(float(p) for p in percentiles))

    def describe(self):
        """Short label such as "DAPI only" or "Legacy (all channels)"."""
        if self.mode == "legacy":
            return "Legacy (all channels, 1.6 behaviour)"
        labels = self.channel_names or tuple("channel {}".format(c + 1) for c in self.channels)
        if len(labels) == 1:
            return "{} only".format(labels[0])
        return " + ".join(labels)

    def to_dict(self):
        return {
            "mode": self.mode,
            "channels": list(self.channels),
            "channel_names": list(self.channel_names),
            "percentiles": list(self.percentiles),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data):
        """Validate a saved recipe; ``None`` means not chosen yet."""
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValueError("The saved registration input is not a mapping.")
        mode = data.get("mode")
        if mode not in MODES:
            raise ValueError("Unknown registration input mode: {!r}.".format(mode))
        version = int(data.get("version", RECIPE_VERSION))
        if version > RECIPE_VERSION:
            raise ValueError(
                "The registration input was saved by a newer DriftlessMap "
                "(recipe version {}).".format(version)
            )
        if mode == "legacy":
            return cls.legacy()
        percentiles = tuple(float(p) for p in data.get("percentiles", DEFAULT_PERCENTILES))
        if len(percentiles) != 2 or not 0 <= percentiles[0] < percentiles[1] <= 100:
            raise ValueError("Invalid registration input percentiles.")
        return cls.from_channels(data.get("channels", ()), data.get("channel_names") or None,
                                 percentiles)


def default_for(n_channels, is_rgb, channel_names=()):
    """The recipe to use without asking, or ``None`` when the user must choose.

    One channel needs no choice. RGB images keep the 1.6 luminance behaviour.
    Multichannel microscopy images have no safe default: DAPI cannot be
    guessed from a colour or a position.
    """
    if n_channels == 1:
        names = tuple(channel_names[:1]) or None
        return RegistrationInput.from_channels((0,), names)
    if is_rgb:
        return RegistrationInput.legacy()
    return None


def check(recipe, n_channels):
    """Raise ``ValueError`` if ``recipe`` cannot be applied to the image."""
    if recipe is None:
        raise ValueError("Choose the registration channels first.")
    if recipe.mode == "channels":
        missing = [c for c in recipe.channels if not 0 <= c < n_channels]
        if missing:
            raise ValueError(
                "The registration channels ({}) are not in this image, which "
                "has {} channel(s). Choose them again.".format(
                    recipe.describe(), n_channels)
            )


def prepare(image, recipe):
    """Return the analysis input and a record of how it was made.

    For ``legacy`` the image is returned unchanged. For ``channels`` a float32
    H x W plane in [0, 1] is returned. The record lists the recipe and the
    per-channel intensity bounds actually used.
    """
    image = np.asarray(image)
    planes = image if image.ndim == 3 else image[..., None]
    check(recipe, planes.shape[2])
    if recipe.mode == "legacy":
        return image, {"recipe": recipe.to_dict(), "bounds": None}
    low_p, high_p = recipe.percentiles
    stack, bounds = [], []
    for channel in recipe.channels:
        values = planes[..., channel].astype(np.float32)
        low, high = np.percentile(values, [low_p, high_p])
        if not np.isfinite(low) or not np.isfinite(high) or high <= low:
            name = (recipe.channel_names[recipe.channels.index(channel)]
                    if recipe.channel_names else "channel {}".format(channel + 1))
            raise ValueError(
                "The registration channel {} is empty or constant, so it cannot "
                "be used for registration.".format(name)
            )
        stack.append(np.clip((values - low) / (high - low), 0.0, 1.0))
        bounds.append((float(low), float(high)))
    plane = np.mean(stack, axis=0).astype(np.float32)
    return plane, {"recipe": recipe.to_dict(), "bounds": bounds}
