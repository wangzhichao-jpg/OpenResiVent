"""健康剂量法和缺省边界。"""

import pytest

from openresivent.health.risk import (
    chronic_daily_intake,
    dose_hazard_quotient,
    lifetime_cancer_risk,
)


def test_dose_and_risk():
    cdi = chronic_daily_intake(2e-8, 1e-4, 70, 0.5)
    assert cdi == pytest.approx(2e-8 * 1e-4 / 70 * 0.5)
    assert dose_hazard_quotient(cdi, cdi / 2) == 2
    assert lifetime_cancer_risk(cdi, 3) == pytest.approx(cdi * 3)
    with pytest.raises(ValueError):
        chronic_daily_intake(1, 1, 0, 1)
    with pytest.raises(ValueError):
        dose_hazard_quotient(1, 0)
    with pytest.raises(ValueError):
        lifetime_cancer_risk(1, -1)
