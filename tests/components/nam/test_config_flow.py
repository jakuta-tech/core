"""Define tests for the Nettigo Air Monitor config flow."""
import asyncio
from unittest.mock import patch

from nettigo_air_monitor import ApiError, AuthFailed, CannotGetMac
import pytest

from homeassistant import data_entry_flow
from homeassistant.components import zeroconf
from homeassistant.components.nam.const import DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER, SOURCE_ZEROCONF

from tests.common import MockConfigEntry

DISCOVERY_INFO = zeroconf.ZeroconfServiceInfo(host="10.10.2.3")
VALID_CONFIG = {"host": "10.10.2.3"}
VALID_AUTH = {"username": "fake_username", "password": "fake_password"}


async def test_form_create_entry_without_auth(hass):
    """Test that the user step without auth works."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == SOURCE_USER
    assert result["errors"] == {}

    with patch("homeassistant.components.nam.NettigoAirMonitor.initialize"), patch(
        "homeassistant.components.nam.NettigoAirMonitor.async_get_mac_address",
        return_value="aa:bb:cc:dd:ee:ff",
    ), patch(
        "homeassistant.components.nam.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            VALID_CONFIG,
        )
        await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "10.10.2.3"
    assert result["data"]["host"] == "10.10.2.3"
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_create_entry_with_auth(hass):
    """Test that the user step with auth works."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == SOURCE_USER
    assert result["errors"] == {}

    with patch(
        "homeassistant.components.nam.NettigoAirMonitor.initialize",
        side_effect=AuthFailed("Auth Error"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            VALID_CONFIG,
        )
        await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "credentials"

    with patch("homeassistant.components.nam.NettigoAirMonitor.initialize"), patch(
        "homeassistant.components.nam.NettigoAirMonitor.async_get_mac_address",
        return_value="aa:bb:cc:dd:ee:ff",
    ), patch(
        "homeassistant.components.nam.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            VALID_AUTH,
        )
        await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "10.10.2.3"
    assert result["data"]["host"] == "10.10.2.3"
    assert result["data"]["username"] == "fake_username"
    assert result["data"]["password"] == "fake_password"
    assert len(mock_setup_entry.mock_calls) == 1


async def test_reauth_successful(hass):
    """Test starting a reauthentication flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="10.10.2.3",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={"host": "10.10.2.3"},
    )
    entry.add_to_hass(hass)

    with patch("homeassistant.components.nam.NettigoAirMonitor.initialize"), patch(
        "homeassistant.components.nam.NettigoAirMonitor.async_get_mac_address",
        return_value="aa:bb:cc:dd:ee:ff",
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=VALID_AUTH,
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
        assert result["reason"] == "reauth_successful"


async def test_reauth_unsuccessful(hass):
    """Test starting a reauthentication flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="10.10.2.3",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={"host": "10.10.2.3"},
    )
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.nam.NettigoAirMonitor.initialize",
        side_effect=ApiError("API Error"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=VALID_AUTH,
        )

        assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
        assert result["reason"] == "reauth_unsuccessful"


@pytest.mark.parametrize(
    "error",
    [
        (ApiError("API Error"), "cannot_connect"),
        (AuthFailed("Auth Error"), "invalid_auth"),
        (asyncio.TimeoutError, "cannot_connect"),
        (ValueError, "unknown"),
    ],
)
async def test_form_with_auth_errors(hass, error):
    """Test we handle errors when auth is required."""
    exc, base_error = error
    with patch(
        "homeassistant.components.nam.NettigoAirMonitor.initialize",
        side_effect=AuthFailed("Auth Error"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data=VALID_CONFIG,
        )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "credentials"

    with patch(
        "homeassistant.components.nam.NettigoAirMonitor.initialize",
        side_effect=exc,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            VALID_AUTH,
        )

    assert result["errors"] == {"base": base_error}


@pytest.mark.parametrize(
    "error",
    [
        (ApiError("API Error"), "cannot_connect"),
        (asyncio.TimeoutError, "cannot_connect"),
        (ValueError, "unknown"),
    ],
)
async def test_form_errors(hass, error):
    """Test we handle errors."""
    exc, base_error = error
    with patch(
        "homeassistant.components.nam.NettigoAirMonitor.initialize",
        side_effect=exc,
    ):

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data=VALID_CONFIG,
        )

    assert result["errors"] == {"base": base_error}


async def test_form_abort(hass):
    """Test we handle abort after error."""
    with patch("homeassistant.components.nam.NettigoAirMonitor.initialize"), patch(
        "homeassistant.components.nam.NettigoAirMonitor.async_get_mac_address",
        side_effect=CannotGetMac("Cannot get MAC address from device"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data=VALID_CONFIG,
        )

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "device_unsupported"


async def test_form_with_auth_abort(hass):
    """Test we handle abort after error."""
    with patch(
        "homeassistant.components.nam.NettigoAirMonitor.initialize",
        side_effect=AuthFailed("Auth Error"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data=VALID_CONFIG,
        )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "credentials"

    with patch("homeassistant.components.nam.NettigoAirMonitor.initialize"), patch(
        "homeassistant.components.nam.NettigoAirMonitor.async_get_mac_address",
        side_effect=CannotGetMac("Cannot get MAC address from device"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            VALID_AUTH,
        )

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "device_unsupported"


async def test_form_already_configured(hass):
    """Test that errors are shown when duplicates are added."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="aa:bb:cc:dd:ee:ff", data=VALID_CONFIG
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch("homeassistant.components.nam.NettigoAirMonitor.initialize"), patch(
        "homeassistant.components.nam.NettigoAirMonitor.async_get_mac_address",
        return_value="aa:bb:cc:dd:ee:ff",
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": "1.1.1.1"},
        )

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "already_configured"

    # Test config entry got updated with latest IP
    assert entry.data["host"] == "1.1.1.1"


async def test_zeroconf(hass):
    """Test we get the form."""
    with patch("homeassistant.components.nam.NettigoAirMonitor.initialize"), patch(
        "homeassistant.components.nam.NettigoAirMonitor.async_get_mac_address",
        return_value="aa:bb:cc:dd:ee:ff",
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            data=DISCOVERY_INFO,
            context={"source": SOURCE_ZEROCONF},
        )
        context = next(
            flow["context"]
            for flow in hass.config_entries.flow.async_progress()
            if flow["flow_id"] == result["flow_id"]
        )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] == {}
    assert context["title_placeholders"]["host"] == "10.10.2.3"
    assert context["confirm_only"] is True

    with patch(
        "homeassistant.components.nam.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {},
        )
        await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "10.10.2.3"
    assert result["data"] == {"host": "10.10.2.3"}
    assert len(mock_setup_entry.mock_calls) == 1


async def test_zeroconf_with_auth(hass):
    """Test that the zeroconf step with auth works."""
    with patch(
        "homeassistant.components.nam.NettigoAirMonitor.initialize",
        side_effect=AuthFailed("Auth Error"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            data=DISCOVERY_INFO,
            context={"source": SOURCE_ZEROCONF},
        )
        context = next(
            flow["context"]
            for flow in hass.config_entries.flow.async_progress()
            if flow["flow_id"] == result["flow_id"]
        )

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["step_id"] == "credentials"
    assert result["errors"] == {}
    assert context["title_placeholders"]["host"] == "10.10.2.3"

    with patch("homeassistant.components.nam.NettigoAirMonitor.initialize"), patch(
        "homeassistant.components.nam.NettigoAirMonitor.async_get_mac_address",
        return_value="aa:bb:cc:dd:ee:ff",
    ), patch(
        "homeassistant.components.nam.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            VALID_AUTH,
        )
        await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "10.10.2.3"
    assert result["data"]["host"] == "10.10.2.3"
    assert result["data"]["username"] == "fake_username"
    assert result["data"]["password"] == "fake_password"
    assert len(mock_setup_entry.mock_calls) == 1


async def test_zeroconf_host_already_configured(hass):
    """Test that errors are shown when host is already configured."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="aa:bb:cc:dd:ee:ff", data=VALID_CONFIG
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        data=DISCOVERY_INFO,
        context={"source": SOURCE_ZEROCONF},
    )

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    "error",
    [
        (ApiError("API Error"), "cannot_connect"),
        (CannotGetMac("Cannot get MAC address from device"), "device_unsupported"),
    ],
)
async def test_zeroconf_errors(hass, error):
    """Test we handle errors."""
    exc, reason = error
    with patch(
        "homeassistant.components.nam.NettigoAirMonitor.initialize",
        side_effect=exc,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            data=DISCOVERY_INFO,
            context={"source": SOURCE_ZEROCONF},
        )

    assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
    assert result["reason"] == reason
