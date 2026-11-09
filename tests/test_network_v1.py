"""M2 元件、节点残差和污染物解析基准。"""

import math

import numpy as np
import pytest
from scipy.optimize import brentq

from openresivent.network.contaminant import TransportPath, integrate, transport_matrix
from openresivent.network.elements import (
    CheckValve,
    ConstantFlow,
    ConstantVolumeValve,
    Duct,
    PolynomialFan,
    PowerLaw,
    airtightness_coefficient,
    leakage_coefficient,
)
from openresivent.network.solver import Link, Zone, solve, wind_pressure


def zones():
    return {
        "out": Zone(293.15, fixed=True, density_kg_m3=1.2),
        "room": Zone(293.15, density_kg_m3=1.2),
    }


def link(start, end, element):
    return Link(start, end, 1.0, 1.0, element=element)


def test_airtight_exhaust():
    for n, expected in [(1, 66.1892265119685), (0.6, 145.24228561143244)]:
        c = airtightness_coefficient(n / 3600, 250)
        assert leakage_coefficient(n * 250 / 3600) == pytest.approx(c)
        with pytest.raises(ValueError):
            leakage_coefficient(0)
        if n == 1:
            assert c * 3600 == pytest.approx(19.6611766786)
        network = [link("out", "room", PowerLaw(c)), link("room", "out", ConstantFlow(300 / 3600))]
        result = solve(zones(), network, tolerance=1e-12, verify_jacobian=True)
        assert result["pressures"]["room"] == pytest.approx(-expected, rel=1e-7)


def test_fan_and_duct():
    fan = PolynomialFan((280, 0, -280 / (400 / 3600) ** 2), 400 / 3600)
    q = brentq(lambda q: fan.flow(-0.00525 * (q * 3600) ** 2)[0] - q, 1e-5, 400 / 3600)
    assert q * 3600 == pytest.approx(200, rel=1e-8)
    network = [
        link("out", "room", fan),
        link("room", "out", PowerLaw(1 / math.sqrt(0.00525) / 3600, 0.5)),
    ]
    solved = solve(zones(), network, tolerance=1e-12, verify_jacobian=True)
    assert solved["flows"][0]["volume_flow"] * 3600 == pytest.approx(200, rel=1e-8)
    assert fan.flow(-280)[0] == 0
    assert fan.flow(-281)[0] < 0
    assert fan.flow(1)[0] > 400 / 3600
    with pytest.raises(ValueError):
        PolynomialFan((1, 1), 1).flow(0)
    duct = Duct(10, 0.2, 0.0001, 2)
    for pressure in (0, 0.01, 1, 100):
        flow, derivative = duct.flow(pressure)
        assert flow >= 0 and derivative > 0
        if pressure:
            h = pressure * 1e-5
            difference = (duct.flow(pressure + h)[0] - duct.flow(pressure - h)[0]) / (2 * h)
            assert derivative == pytest.approx(difference, rel=1e-4)


def test_check_and_cav():
    valve = CheckValve.from_area_rating(2, 0.02, 100 / 3600, math.pi * 0.1**2)
    assert -valve.flow(-250)[0] * 3600 == pytest.approx(math.pi, rel=1e-8)
    assert -valve.flow(-100)[0] * 3600 == pytest.approx(1.731764637177603, rel=1e-8)
    assert valve.flow(1)[0] == 0 and valve.flow(3)[0] > 0
    cav = ConstantVolumeValve(0.05, 50, 200)
    assert cav.flow(100)[0] == 0.05
    for bound in (50, 200):
        assert cav.flow(bound * (1 - 1e-10))[0] == pytest.approx(
            cav.flow(bound * (1 + 1e-10))[0], rel=1e-9
        )
    assert cav.flow(25)[0] == pytest.approx(0.05 * math.sqrt(25 / 50))
    assert cav.flow(800)[0] == pytest.approx(0.05 * math.sqrt(800 / 200))


def test_network_boundaries():
    # 极小开口、极大压差比、多风机并联、孤立节点、零风速。
    for c, flow in [(1e-9, 1e-7), (1e-4, 0.1)]:
        result = solve(
            zones(),
            [link("out", "room", PowerLaw(c)), link("room", "out", ConstantFlow(flow))],
            tolerance=1e-13,
            verify_jacobian=True,
        )
        assert result["mass_residual"] < 1e-13
    result = solve(
        zones(),
        [
            link("out", "room", PowerLaw(0.001)),
            link("room", "out", ConstantFlow(0.02)),
            link("room", "out", ConstantFlow(0.03)),
        ],
        tolerance=1e-12,
        verify_jacobian=True,
    )
    assert result["flows"][0]["volume_flow"] == pytest.approx(0.05)
    with pytest.raises(ValueError, match="未连接"):
        solve({**zones(), "isolated": Zone(293)}, [])
    assert wind_pressure(0.8, 1.2, 0) == 0
    with pytest.raises(RuntimeError, match="最大残差节点.*相关元件"):
        solve(
            zones(),
            [link("out", "room", PowerLaw(0.001)), link("room", "out", ConstantFlow(0.03))],
            max_iterations=0,
        )


def test_contaminant_exact_and_sources():
    paths = [TransportPath(None, 0, 50 / 3600), TransportPath(0, None, 50 / 3600)]
    out = integrate([50], paths, [0], [1000e-9], [0, 3600], [(0, [0])], 20e-9)
    assert out[-1, 0] * 1e9 == pytest.approx(380.521852, rel=1e-8)
    paths2 = [
        TransportPath(None, 0, 100 / 3600),
        TransportPath(0, 1, 100 / 3600),
        TransportPath(1, None, 100 / 3600),
    ]
    a, b = transport_matrix([50, 50], paths2, [0, 0], 20e-9)
    steady = np.linalg.solve(-a, b + np.array([2000e-9 / 3600, 0]) / 50)
    assert steady * 1e9 == pytest.approx([40, 40])
    source = [(0, [0, 0]), (1800, [2000e-9 / 3600, 0])]
    coarse = integrate([50, 50], paths2, [0, 0], [20e-9, 20e-9], [0, 3600], source, 20e-9)
    fine = integrate(
        [50, 50], paths2, [0, 0], [20e-9, 20e-9], np.arange(0, 3601, 60), source, 20e-9
    )
    assert coarse[-1] == pytest.approx(fine[-1], rel=1e-12)
    filtered = integrate(
        [50],
        [TransportPath(None, 0, 50 / 3600, 0.5), TransportPath(0, None, 50 / 3600)],
        [1 / 3600],
        [0],
        [0, 3600],
        [(0, [0])],
        20e-9,
    )
    assert filtered[-1, 0] == pytest.approx(5e-9 * (1 - math.exp(-2)))
