import math

import numpy as np
import pytest

from thermodrop.core.analysis import auto_block_factor, block_reduce, compute_histogram, extract_region
from thermodrop.core.geometry import (
    bounding_box,
    ellipse_mask,
    from_local,
    moved,
    resized,
    rotated,
    to_local,
)
from thermodrop.core.models import EllipseRegion, HistogramFilter, ReferenceMode, ThermalField, ValueMode
from thermodrop.core.reference import make_reference_strategy


def test_circle_mask_area_close_to_pi_r2():
    region = EllipseRegion(cx=50, cy=50, rx=20, ry=20)
    mask = ellipse_mask(region, 100, 100)
    assert abs(mask.sum() - math.pi * 400) / (math.pi * 400) < 0.02


def test_rotated_ellipse_mask_is_rotation_invariant_in_area():
    a = ellipse_mask(EllipseRegion(50, 50, 30, 10, 0), 100, 100).sum()
    b = ellipse_mask(EllipseRegion(50, 50, 30, 10, 37), 100, 100).sum()
    assert abs(int(a) - int(b)) / a < 0.03


def test_rotation_direction_x_toward_y():
    # Эллипс, вытянутый под 90°, должен быть вытянут по Y (строкам).
    mask = ellipse_mask(EllipseRegion(50, 50, 30, 5, 90), 100, 100)
    rows, cols = np.nonzero(mask)
    assert np.ptp(rows) > 3 * np.ptp(cols)


def test_bounding_box_contains_mask():
    region = EllipseRegion(40.3, 30.7, 25, 8, 30)
    r0, r1, c0, c1 = bounding_box(region, 80, 100)
    full = ellipse_mask(region, 80, 100)
    assert full.sum() == full[r0:r1, c0:c1].sum()


def test_extract_region_delta_with_background_reference():
    data = np.full((60, 60), 20.0)
    region = EllipseRegion(30, 30, 10, 10)
    data[ellipse_mask(region, 60, 60)] = 18.0
    field = ThermalField(data)
    rd = extract_region(field, region, ValueMode.DELTA,
                        make_reference_strategy(ReferenceMode.BACKGROUND_MEDIAN))
    assert rd.reference == pytest.approx(20.0)
    assert np.allclose(rd.inside, -2.0)


def test_histogram_filter_above():
    values = np.arange(100, dtype=float)
    h = compute_histogram(values, 10, 50.0, HistogramFilter.ABOVE)
    assert h.selected.count == 50
    assert h.counts_all.sum() == 100
    assert h.counts.sum() == 50
    assert h.fraction_selected == pytest.approx(0.5)


def test_block_reduce_mean_and_mask():
    values = np.arange(16, dtype=float).reshape(4, 4)
    mask = np.ones((4, 4), bool)
    v, m = block_reduce(values, mask, 2)
    assert v.shape == (2, 2) and m.all()
    assert v[0, 0] == pytest.approx((0 + 1 + 4 + 5) / 4)


def test_auto_block_factor():
    assert auto_block_factor((40, 40), 1600) == 1
    assert auto_block_factor((100, 100), 1600) == 3


@pytest.mark.parametrize("angle", [0.0, 25.0, -60.0, 135.0])
def test_local_coordinates_roundtrip(angle):
    region = EllipseRegion(12.5, 40.25, 7.0, 3.5, angle)
    point = (3.0, -8.0)
    back = from_local(region, to_local(region, point))
    assert back == pytest.approx(point)


def test_moved_follows_cursor():
    region = moved(EllipseRegion(10, 10, 5, 3), (11, 12), (21, 2))
    assert (region.cx, region.cy) == (20, 0)


def test_rotated_by_quarter_turn():
    region = rotated(EllipseRegion(0, 0, 5, 3, 10), (5, 0), (0, 5))
    assert region.angle_deg == pytest.approx(100)


@pytest.mark.parametrize("angle", [0.0, 30.0, -75.0])
def test_resized_grab_point_follows_cursor(angle):
    region = EllipseRegion(50, 50, 10, 4, angle)
    grab = from_local(region, (10, 0))       # край по оси Rx
    target = from_local(region, (15, 0.3))
    out = resized(region, grab, target)
    assert out.rx == pytest.approx(15)
    assert out.ry == pytest.approx(4)        # захват на оси Rx не меняет Ry
    assert (out.cx, out.cy, out.angle_deg) == (50, 50, angle)


def test_resized_uniform_keeps_aspect():
    region = EllipseRegion(0, 0, 10, 5)
    out = resized(region, (10, 0), (20, 0), uniform=True)
    assert (out.rx, out.ry) == pytest.approx((20, 10))


def test_resized_never_collapses():
    out = resized(EllipseRegion(0, 0, 10, 5), (10, 0), (0, 0))
    assert out.rx > 0
