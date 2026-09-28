import dataclasses
from datetime import date
from decimal import Decimal

from app.dam_source.models import DamRecord

NUMERIC = ["price", "volume_sell", "volume_buy", "declared_volume_sell", "declared_volume_buy"]


def test_record_holds_all_five_values_as_decimal():
    r = DamRecord(date(2026, 7, 1), 1, *(Decimal(v) for v in ["14947.80", "3246.2", "3246.2", "3944.4", "3323.5"]))
    fields = {f.name for f in dataclasses.fields(r)}
    assert set(NUMERIC) <= fields
    for name in NUMERIC:
        value = getattr(r, name)
        assert isinstance(value, Decimal) and not isinstance(value, float)
