"""Methods for processing OPA 800 tuning data."""

import pathlib

import numpy as np
import WrightTools as wt

from .. import Curve, Dependent, Setpoints
from ._plot import plot_intensity


# --- processing methods --------------------------------------------------------------------------

__all__ = ["intensity"]


def _intensity(data, channel_name, tune_points, *, along=None, spline=True, **spline_kwargs):
    if along is not None:
        axis = (along, 1)
    else:
        axis = 1
    data.moment(axis=axis, channel=channel_name, moment=1)
    offsets = data[f"{channel_name}_1_moment_1"].points

    if spline:
        spline = wt.kit.Spline(tune_points, offsets, **spline_kwargs)
        return spline(tune_points)
    if np.allclose(data.axes[0].points, tune_points):
        return offsets
    else:
        raise ValueError("Data points and curve points do not match, and splining disabled")


def intensity(
    data,
    channel,
    dependent,
    curve=None,
    *,
    level=False,
    cutoff_factor=0.1,
    autosave=True,
    save_directory=None,
):
    """Workup a generic intensity plot for a single dependent.

    Parameters
    ----------
    data : wt.data.Data objeect
        should be in (setpoint, dependent)

    Returns
    -------
    curve
        New curve object.
    """
    data = data.copy()
    data.convert("wn")
    if curve is not None:
        old_curve = curve.copy()
        old_curve.convert("wn")
        setpoints = old_curve.setpoints
    else:
        old_curve = None
        setpoints = Setpoints(data.axes[0].points, data.axes[0].expression, data.axes[0].units)
    # TODO: units

    if isinstance(channel, (int, str)):
        channel = data.channels[wt.kit.get_index(data.channel_names, channel)]

    # TODO: check if level does what we want
    if level:
        data.level(channel.natural_name, 0, -3)

    # TODO: gtol/ltol
    cutoff = channel.max() * cutoff_factor
    channel.clip(min=cutoff)

    kwargs = {}
    if data.axes[1].points.ndim > 1:
        kwargs["along"] = [
            i
            for i in range(data.ndim)
            if data.axes[1].shape[i] > 1 and not data.axes[0].shape[i] > 1
        ][0]
    offsets = _intensity(data, channel.natural_name, setpoints[:], **kwargs)
    print(offsets)

    units = data.axes[1].units
    if units == "None":
        units = None

    new_curve = Curve(
        setpoints, [Dependent(offsets, dependent, units, differential=True)], name="intensity"
    )

    if curve is not None:
        curve = old_curve + new_curve
    else:
        curve = new_curve

    # Why did we have to map setpoints?
    curve.map_setpoints(setpoints[:])

    fig, _ = plot_intensity(data, channel.natural_name, dependent, curve, old_curve)

    if autosave:
        if save_directory is None:
            # TODO: Formal decision on whether this should be cwd or data/curve location
            save_directory = "."
        save_directory = pathlib.Path(save_directory)
        curve.save(save_directory=save_directory, full=True)
        # Should we timestamp the image?
        p = save_directory / "intensity.png"
        wt.artists.savefig(p, fig=fig)
    return curve
