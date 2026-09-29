import pytest

from app.settings import ScheduleSettingsStore


async def test_defaults_on_empty_table(sessions):
    settings = await ScheduleSettingsStore(sessions).get()  # фікстура engine лишає таблицю порожньою
    assert (settings.enabled, settings.interval_minutes) == (True, 60)


async def test_update_persists_across_store_instances(sessions):
    await ScheduleSettingsStore(sessions).update(False, 15)
    settings = await ScheduleSettingsStore(sessions).get()
    assert (settings.enabled, settings.interval_minutes) == (False, 15)


async def test_update_moves_updated_at(sessions):
    store = ScheduleSettingsStore(sessions)
    before = await store.get()
    after = await store.update(True, 30)
    assert after.updated_at > before.updated_at


@pytest.mark.parametrize("bad", [4, 1441])
async def test_out_of_range_rejected_before_sql(sessions, bad):
    store = ScheduleSettingsStore(sessions)
    with pytest.raises(ValueError):
        await store.update(True, bad)
    assert (await store.get()).interval_minutes == 60


async def test_notifications_enabled_by_default(sessions):
    from app.settings import NotificationSettingsStore
    assert await NotificationSettingsStore(sessions).enabled() is True


async def test_notifications_switch_persists_and_leaves_schedule(sessions):
    from app.settings import NotificationSettingsStore
    await ScheduleSettingsStore(sessions).update(True, 15)
    await NotificationSettingsStore(sessions).set_enabled(False)
    assert await NotificationSettingsStore(sessions).enabled() is False
    schedule = await ScheduleSettingsStore(sessions).get()
    assert (schedule.enabled, schedule.interval_minutes) == (True, 15)
