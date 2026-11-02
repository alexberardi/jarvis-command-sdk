import asyncio

from jarvis_command_sdk import DeviceManagerDevice, IJarvisDeviceManager, device_type, device_types

CONTROL_TYPES = {"light", "toggle", "cover", "lock", "thermostat", "camera", "kettle", "media", "alarm", "sensor"}
BUTTON_TYPES = {"primary", "secondary", "destructive"}
REQUIRED = {"label", "icon", "controllable", "control_type", "features", "ui_hints", "state_fields", "actions"}


def _types():
    cat = device_types()
    return [("fallback", cat["fallback"])] + list(cat["domains"].items())


def test_every_type_is_complete():
    assert device_types()["version"] == 1
    for name, t in _types():
        assert REQUIRED <= t.keys(), name
        assert t["control_type"] in CONTROL_TYPES, name
        assert "state" in t["state_fields"], name
        assert set(t["ui_hints"]["features"]) <= set(t["features"]), name


def test_actions_are_well_formed_and_only_on_controllable_types():
    for name, t in _types():
        if not t["controllable"]:
            assert t["actions"] == [], name
        for a in t["actions"]:
            assert a.keys() == {"text", "action", "type", "icon"}, name
            assert a["type"] in BUTTON_TYPES, name
        actions = [a["action"] for a in t["actions"]]
        assert len(actions) == len(set(actions)), name


def test_unknown_domain_gets_fallback():
    assert device_type("toaster") == device_types()["fallback"]


def test_unit_overlay_and_no_leak():
    assert device_type("climate", "C")["ui_hints"]["min_value"] == 10
    assert device_type("climate", "F")["ui_hints"]["unit"] == "F"
    assert device_type("climate")["ui_hints"]["min_value"] == 50
    assert "ui_hints_by_unit" not in device_type("climate")
    assert "ui_hints_by_unit" in device_types()["domains"]["climate"]  # the cached catalogue is untouched


class _ListOnly(IJarvisDeviceManager):
    name = "list_only"
    friendly_name = "List Only"
    can_edit_devices = False

    async def collect_devices(self):
        return []


def test_manager_state_and_control_default_to_unsupported():
    dev = DeviceManagerDevice(name="TV", domain="media_player", entity_id="media_player.tv")
    mgr = _ListOnly()
    assert asyncio.run(mgr.get_state(dev)) is None
    result = asyncio.run(mgr.control(dev, "pause"))
    assert not result.success and result.entity_id == "media_player.tv" and result.action == "pause"
    assert "List Only" in result.error
