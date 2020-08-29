__all__ = ["load", "restore", "store", "undo"]


from datetime import datetime, timedelta, timezone
import pathlib
import os
import warnings

import appdirs
import dateutil

from ._transition import Transition
from ._open import open as open_


def load(name, time=None, reverse=True):
    if time is None:
        time = datetime.now(timezone.utc)
    if hasattr(time, "datetime"):
        time = time.datetime()

    def find(name, time, reverse):
        year = time.year
        month = time.month

        if "ATTUNE_STORE" in os.environ and os.environ["ATTUNE_STORE"]:
            attune_dir = pathlib.Path(os.environ["ATTUNE_STORE"])
        else:
            attune_dir = pathlib.Path(appdirs.user_data_dir("attune", "attune"))

        if not (attune_dir / name).exists():
            raise ValueError(f"No instrument found with name '{name}'")

        while True:
            datadir = attune_dir
            datadir /= name
            datadir /= str(year)
            datadir /= f"{month:02}"
            if datadir.exists():
                for d in sorted(
                    datadir.iterdir(),
                    key=lambda x: dateutil.parser.isoparse(x.name),
                    reverse=reverse,
                ):
                    if reverse:
                        if dateutil.parser.isoparse(d.name) <= time:
                            return datadir / d.name
                    else:
                        if dateutil.parser.isoparse(d.name) >= time:
                            return datadir / d.name

            if reverese:
                if month == 1:
                    year -= 1
                    month = 12
                else:
                    month -= 1
                if year < 1960:
                    raise ValueError(
                        f"Could not find an instrument earlier than {time}. Looked back all the way to the invention of the laser"
                    )
            else:
                if month == 12:
                    month = 1
                    year += 1
                else:
                    month += 1
                if year > datetime.now().year + 20:
                    raise ValueError(f"Could not find an instrument later than {time}.")

    datadir = find(name, time, reverse)
    return open_(datadir / "instrument.json", load=dateutil.parser.isoparse(datadir.name))


def restore(name, time):
    instr = load(name, time)
    if load(name) == instr:
        warnings.warn("Attempted to restore instrument equivalent to current head, ignoring.")
    instr.transition = Transition(TransitionType.restore, metadata={"time": time})
    _store_instr(instr)


def store(instrument, warn=True):
    if load(instrument.name) == instrument:
        if warn:
            warnings.warn("Attempted to store instrument equivalent to current head, ignoring.")
        return
    if instrument.load is None and instrument.transition.previous is not None:
        store(instrument.transition.previous, warn=False)

    if instrument.load is not None:
        restore(instrument.name, instrument.load)
        return

    _store_instr(instrument)


def _store_instr(instrument):
    if "ATTUNE_STORE" in os.environ and os.environ["ATTUNE_STORE"]:
        attune_dir = pathlib.Path(os.environ["ATTUNE_STORE"])
    else:
        attune_dir = pathlib.Path(appdirs.user_data_dir("attune", "attune"))

    while True:
        now = datetime.now(timezone.utc)
        # make datadir
        datadir = attune_dir
        datadir /= instrument.name
        datadir /= f"{now.year}"
        datadir /= f"{now.month:02}"
        datadir /= now.isoformat(timespec="milliseconds").replace("-", "").replace(":", "")
        try:
            datadir.mkdir(parents=True)
        except FileExistsError:
            continue
        else:
            break
    # store instrument
    with open(datadir / "instrument.json", "w") as f:
        instrument.save(f)
        f.write("\n")
    # store data
    if instrument.transition.data is not None:
        instrument.transition.data.save(datadir / "data.wt5")
    # store old instrument
    if instrument.transition.previous is not None:
        with open(datadir / "previous_instrument.json", "w") as f:
            instrument.transition.previous.save(f)


def undo(instrument):
    if instrument.load is not None:
        return load(instrument.name, instrument.load - timedelta(milliseconds=1))
    elif instrument.transition.previous is not None:
        return instrument.transition.previous
    raise ValueError("Nothing to undo")
