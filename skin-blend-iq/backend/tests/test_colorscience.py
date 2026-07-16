"""Mathematical validation (spec section 20): color conversions and
CIEDE2000 against the Sharma, Wu & Dalal (2005) reference pairs."""

import math

import pytest

from app.colorscience import (
    classify_undertone,
    delta_e_76,
    delta_e_2000,
    ita_degrees,
    lab_to_lch,
    lab_to_srgb,
    lab_to_xyz,
    rgb_to_hsv,
    srgb_to_lab,
    srgb_to_xyz,
    xyz_to_lab,
)

# (Lab1, Lab2, expected ΔE00) — Sharma/Wu/Dalal reference dataset subset.
SHARMA_PAIRS = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, -1.0000, 2.0000), (50.0000, 0.0000, 0.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0011), 7.2195),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0010, -2.4900), 4.8045),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (61.0000, -5.0000, 29.0000), 22.8977),
    ((50.0000, 2.5000, 0.0000), (56.0000, -27.0000, -3.0000), 31.9030),
    ((50.0000, 2.5000, 0.0000), (58.0000, 24.0000, 15.0000), 19.4535),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2972, 0.0000), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 1.8634, 0.5757), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2592, 0.3350), 1.0000),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((35.0831, -44.1164, 3.7933), (35.0232, -40.0716, 1.5901), 1.8645),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((36.4612, 47.8580, 18.3852), (36.2715, 50.5065, 21.2231), 1.4146),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((90.9257, -0.5406, -0.9208), (88.6381, -0.8985, -0.7239), 1.5381),
    ((6.7747, -0.2908, -2.4247), (5.8714, -0.0985, -2.2286), 0.6377),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize("lab1,lab2,expected", SHARMA_PAIRS)
def test_ciede2000_reference_pairs(lab1, lab2, expected):
    assert delta_e_2000(lab1, lab2) == pytest.approx(expected, abs=1e-4)


def test_ciede2000_symmetry_and_identity():
    a, b = (59.1, 12.8, 19.7), (58.5, 13.4, 20.1)
    assert delta_e_2000(a, b) == pytest.approx(delta_e_2000(b, a))
    assert delta_e_2000(a, a) == 0.0
    assert delta_e_76(a, a) == 0.0


def test_srgb_lab_known_values():
    # White and primary red (standard D65/2deg values).
    assert srgb_to_lab((255, 255, 255)) == pytest.approx((100.0, 0.0, 0.0), abs=0.01)
    assert srgb_to_lab((255, 0, 0)) == pytest.approx((53.2408, 80.0925, 67.2032), abs=0.01)
    assert srgb_to_lab((0, 0, 0)) == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)


def test_xyz_lab_roundtrip():
    for xyz in [(41.24, 21.26, 1.93), (50.0, 50.0, 50.0), (95.047, 100.0, 108.883)]:
        lab = xyz_to_lab(xyz)
        assert lab_to_xyz(lab) == pytest.approx(xyz, abs=1e-6)


def test_srgb_lab_roundtrip():
    for rgb in [(151, 108, 86), (10, 200, 30), (250, 250, 2)]:
        lab = srgb_to_lab(rgb)
        back = lab_to_srgb(lab)
        assert back == pytest.approx(rgb, abs=0.05)


def test_hsv_and_lch():
    h, s, v = rgb_to_hsv((255, 0, 0))
    assert (h, s, v) == pytest.approx((0.0, 1.0, 1.0))
    L, c, hue = lab_to_lch((50.0, 0.0, 10.0))
    assert hue == pytest.approx(90.0)
    assert c == pytest.approx(10.0)


def test_ita_degrees():
    # ITA = atan((L-50)/b) in degrees.
    assert ita_degrees((70.0, 10.0, 20.0)) == pytest.approx(math.degrees(math.atan(1.0)))
    assert ita_degrees((50.0, 5.0, 15.0)) == pytest.approx(0.0)
    assert ita_degrees((60.0, 5.0, 0.0)) is None


def test_undertone_classifier_bands():
    warm, conf_w = classify_undertone((60.0, 8.0, 30.0))   # hue ~75deg
    cool, conf_c = classify_undertone((60.0, 25.0, 12.0))  # hue ~26deg
    neutral, _ = classify_undertone((60.0, 0.5, 0.5))      # low chroma
    assert warm == "warm"
    assert cool == "cool"
    assert neutral == "neutral"
    assert 0.0 <= conf_w <= 1.0 and 0.0 <= conf_c <= 1.0
