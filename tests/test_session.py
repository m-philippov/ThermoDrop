from pathlib import Path

import numpy as np
import pytest

from thermodrop.core.models import HistogramFilter, ValueMode
from thermodrop.fileio.readers import default_registry
from thermodrop.services.session import AnalysisSession


@pytest.fixture
def drop_file(tmp_path: Path) -> Path:
    rows, cols = 80, 60
    yy, xx = np.mgrid[0:rows, 0:cols]
    data = np.full((rows, cols), 20.0)
    data[(yy - 40) ** 2 + (xx - 30) ** 2 <= 100] = 12.0
    lines = ["%d;%d" % (rows, cols)] + [";".join(("%.1f" % v).replace(".", ",") for v in r) for r in data]
    path = tmp_path / "drop.csv"
    path.write_text("\r\n".join(lines), encoding="cp1251")
    return path


def test_open_detects_drop_and_computes_delta(drop_file):
    session = AnalysisSession(default_registry())
    events = []
    session.region_data_changed.connect(lambda d: events.append(d))
    session.open_file(drop_file)

    region = session.region
    assert region.cx == pytest.approx(30, abs=1.5)
    assert region.cy == pytest.approx(40, abs=1.5)
    assert events, "представления должны получить данные области"
    data = session.region_data
    assert data.reference == pytest.approx(20.0)
    assert np.nanmin(data.inside) == pytest.approx(-8.0)


def test_threshold_is_kept_in_absolute_temperature(drop_file):
    session = AnalysisSession(default_registry())
    session.open_file(drop_file)
    session.set_threshold(-4.0)  # ΔT
    assert session.threshold_absolute == pytest.approx(16.0)
    session.set_value_mode(ValueMode.ABSOLUTE)
    assert session.threshold == pytest.approx(16.0)


def test_histogram_above_threshold(drop_file):
    session = AnalysisSession(default_registry())
    session.open_file(drop_file)
    session.set_hist_filter(HistogramFilter.ABOVE)
    session.set_threshold(-4.0)
    hist = session.histogram()
    assert hist.selected.minimum >= -4.0
    assert hist.selected.count < hist.total.count
