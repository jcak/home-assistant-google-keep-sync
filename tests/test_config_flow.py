"""Test config flow for Google Keep Sync."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.google_keep_sync.config_flow import (
    CannotConnectError,
)
from custom_components.google_keep_sync.const import DOMAIN


@pytest.fixture()
def mock_google_keep_api():
    """Fixture for mocking the GoogleKeepAPI class."""
    with patch("custom_components.google_keep_sync.config_flow.GoogleKeepAPI") as mock:
        # Mock lists returned by fetch_all_lists
        # Note that fetch_all_lists returns a list of gkeepapi.node.List
        mock_lists = [
            MagicMock(id=f"list_id_{i}", title=f"list{i}") for i in range(1, 4)
        ]
        mock_instance = mock.return_value
        mock_instance.authenticate = AsyncMock(return_value=True)
        mock_instance.fetch_all_lists = AsyncMock(return_value=mock_lists)
        yield mock

        mock.reset_mock()


@pytest.mark.asyncio
async def test_user_form_setup(hass: HomeAssistant, mock_google_keep_api):
    """Test the initial user setup form."""
    user_name = "testuser@example.com"
    user_password = "testpass"
    user_token = "testtoken"
    user_list_prefix = "testprefix"

    # Initiate the config flow
    initial_form_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert initial_form_result["type"] == "form"
    assert initial_form_result["errors"] == {}

    # Submit user credentials
    user_input = {
        "username": user_name,
        "password": user_password,
        "token": user_token,
        "list_prefix": user_list_prefix,
    }
    credentials_form_result = await hass.config_entries.flow.async_configure(
        initial_form_result["flow_id"], user_input=user_input
    )

    # Check if the next step is list selection
    assert credentials_form_result["type"] == "form"
    assert credentials_form_result["step_id"] == "select_lists"

    # Simulate list selection - use the mock list IDs
    list_selection = {"lists_to_sync": ["list_id_1", "list_id_2"]}
    final_form_result = await hass.config_entries.flow.async_configure(
        credentials_form_result["flow_id"], user_input=list_selection
    )

    # Check the final result for entry creation
    assert final_form_result["type"] == "create_entry"
    assert final_form_result["title"] == user_name
    assert final_form_result["data"] == {
        "list_prefix": user_list_prefix,
        "username": user_name,
        "password": user_password,
        "token": user_token,
        "lists_to_sync": ["list_id_1", "list_id_2"],
    }


@pytest.mark.asyncio
async def test_invalid_auth_handling(hass: HomeAssistant, mock_google_keep_api):
    """Test handling of invalid authentication."""
    user_input = {"username": "testuser", "password": "wrongpass"}

    # Get the mock instance and set authenticate to return False
    mock_instance = mock_google_keep_api.return_value
    mock_instance.authenticate.return_value = False

    initial_form_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    auth_fail_result = await hass.config_entries.flow.async_configure(
        initial_form_result["flow_id"], user_input=user_input
    )

    assert auth_fail_result["type"] == "form"
    assert auth_fail_result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_user_input_handling(hass: HomeAssistant, mock_google_keep_api):
    """Test user input handling."""
    user_input = {"username": "validuser@example.com", "password": "validpassword"}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=user_input
    )
    assert result["type"] == "form"
    assert result["step_id"] == "select_lists"


@pytest.mark.asyncio
async def test_invalid_user_input(hass: HomeAssistant):
    """Test invalid user input."""
    user_input = {"username": "", "password": ""}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=user_input
    )
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_unexpected_exception_handling(hass: HomeAssistant, mock_google_keep_api):
    """Test handling of unexpected exceptions."""
    # Access the mocked GoogleKeepAPI instance and set authenticate
    # to raise an exception
    mock_instance = mock_google_keep_api.return_value
    mock_instance.authenticate.side_effect = Exception("Test Exception")

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={"username": "user", "password": "pass"},
    )

    # Assert that an unknown error is handled
    assert result["type"] == "form"
    assert result["errors"] == {"base": "unknown"}


@pytest.mark.asyncio
async def test_reauth_flow(hass: HomeAssistant, mock_google_keep_api):
    """Test reauthentication flow."""
    # Create a mock entry to simulate existing config entry
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={"username": "user@example.com", "password": "old_password"},
    )
    mock_entry.add_to_hass(hass)

    # Modify the behavior of authenticate to simulate successful reauthentication
    mock_instance = mock_google_keep_api.return_value
    mock_instance.authenticate.return_value = True

    # Initiate the reauthentication flow
    init_flow_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth", "entry_id": mock_entry.entry_id}
    )

    # Assert that we are on the reauth_confirm step
    assert init_flow_result["type"] == "form"
    assert init_flow_result["step_id"] == "reauth_confirm"

    # Provide the new password
    new_password_input = {"password": "new_password"}
    config_flow_result = await hass.config_entries.flow.async_configure(
        init_flow_result["flow_id"], new_password_input
    )

    # Assert that reauthentication is successful and the flow is aborted
    assert config_flow_result["type"] == "abort"

    # Verify the entry data is updated with the new password
    updated_entry = hass.config_entries.async_get_entry(mock_entry.entry_id)
    assert updated_entry.data["password"] == "new_password"


@pytest.mark.asyncio
async def test_options_flow(
    hass: HomeAssistant, mock_google_keep_api, mock_config_entry
):
    """Test options flow."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    user_input = {"lists_to_sync": ["list_id_1", "list_id_3"]}

    # Initialize the options flow
    init_form_response = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )
    assert init_form_response["type"] == "form"
    assert init_form_response["step_id"] == "init"

    # Submit user input and get the response
    submission_response = await hass.config_entries.options.async_configure(
        init_form_response["flow_id"], user_input=user_input
    )
    assert submission_response["type"] == "create_entry"


@pytest.mark.asyncio
async def test_reauth_flow_invalid_credentials(
    hass: HomeAssistant, mock_google_keep_api
):
    """Test reauthentication flow with invalid credentials."""
    # Create a mock entry to simulate existing config entry
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={"username": "user@example.com", "password": "old_password"},
    )
    mock_entry.add_to_hass(hass)

    # Modify the behavior of authenticate to simulate failed reauthentication
    mock_instance = mock_google_keep_api.return_value
    mock_instance.authenticate.return_value = False

    # Initiate the reauthentication flow
    init_flow_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth", "entry_id": mock_entry.entry_id}
    )

    # Provide the incorrect new password
    incorrect_password_input = {"password": "wrong_password"}
    config_flow_result = await hass.config_entries.flow.async_configure(
        init_flow_result["flow_id"], incorrect_password_input
    )

    # Assert that reauthentication fails
    assert config_flow_result["type"] == "form"
    assert config_flow_result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_options_flow_fetch_list_failure(
    hass: HomeAssistant, mock_google_keep_api, mock_config_entry
):
    """Test options flow when list fetch fails."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Simulate fetch_all_lists raising an exception
    mock_instance = mock_google_keep_api.return_value
    mock_instance.fetch_all_lists.side_effect = Exception("Fetch Failed")

    # Initialize the options flow
    init_form_response = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )
    assert init_form_response["type"] == "form"
    assert init_form_response["errors"] == {"base": "list_fetch_error"}


@pytest.mark.asyncio
async def test_empty_username_or_password(hass: HomeAssistant):
    """Test that empty username or password is handled."""
    # Test with empty username
    user_input = {"username": "", "password": "password"}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=user_input
    )
    assert result["errors"] == {"base": "invalid_auth"}

    # Test with empty password
    user_input = {"username": "username", "password": ""}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=user_input
    )
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_authentication_network_issue(hass: HomeAssistant, mock_google_keep_api):
    """Test network issues during authentication."""
    user_input = {"username": "testuser", "password": "testpass"}

    # Simulate network issue
    mock_instance = mock_google_keep_api.return_value
    mock_instance.authenticate.side_effect = CannotConnectError()

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=user_input
    )

    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_duplicate_config_entry(hass: HomeAssistant, mock_google_keep_api):
    """Test that creating a duplicate configuration entry is handled."""
    user_name = "duplicateuser@example.com"
    user_password = "testpass"

    # Create a mock entry to simulate existing config entry
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=user_name.lower(),
        data={"username": user_name, "password": user_password},
    )
    existing_entry.add_to_hass(hass)

    # Attempt to create a new entry with the same unique_id
    user_input = {"username": user_name, "password": "newpass"}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=user_input
    )

    assert result["errors"] == {"base": "already_configured"}


@pytest.mark.asyncio
async def test_reauth_flow_success(hass: HomeAssistant, mock_google_keep_api):
    """Test reauthentication flow is aborted on success."""
    user_name = "testuser@example.com"
    old_password = "old_password"
    new_password = "new_password"

    # Create a mock entry to simulate existing config entry
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=user_name.lower(),
        data={"username": user_name, "password": old_password},
    )
    mock_entry.add_to_hass(hass)

    # Modify the behavior of authenticate to simulate successful reauthentication
    mock_instance = mock_google_keep_api.return_value
    mock_instance.authenticate.return_value = True

    # Initiate the reauthentication flow
    init_flow_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth", "entry_id": mock_entry.entry_id}
    )

    # Provide the new password
    new_password_input = {"password": new_password}
    config_flow_result = await hass.config_entries.flow.async_configure(
        init_flow_result["flow_id"], new_password_input
    )

    # Assert that reauthentication is successful and the flow is aborted
    assert config_flow_result["type"] == "abort"
    assert config_flow_result["reason"] == "reauth_successful"


@pytest.mark.asyncio
async def test_options_flow_update_data(
    hass: HomeAssistant, mock_google_keep_api, mock_config_entry
):
    """Test that options flow updates the configuration entry data."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    user_input = {"lists_to_sync": ["list_id_1", "list_id_3"]}

    # Initialize the options flow and capture the flow ID
    init_result = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )
    flow_id = init_result["flow_id"]

    # Submit user input and update the configuration entry
    await hass.config_entries.options.async_configure(flow_id, user_input=user_input)

    # Assert that the entry data is updated
    updated_entry = hass.config_entries.async_get_entry(mock_config_entry.entry_id)
    assert updated_entry.data["lists_to_sync"] == ["list_id_1", "list_id_3"]


@pytest.mark.asyncio
async def test_options_flow_create_entry(
    hass: HomeAssistant, mock_google_keep_api, mock_config_entry
):
    """Test options flow creates an entry correctly."""
    mock_config_entry.add_to_hass(hass)

    # Initialize the options flow
    init_result = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )

    user_input = {"lists_to_sync": ["list_id_1", "list_id_2"]}

    # Submit user input
    result = await hass.config_entries.options.async_configure(
        init_result["flow_id"], user_input=user_input
    )

    assert result["type"] == "create_entry"
    assert result["data"] == user_input


@pytest.mark.asyncio
async def test_options_flow_reauth_required(
    hass: HomeAssistant, mock_google_keep_api, mock_config_entry
):
    """Test options flow aborts when reauthentication is required."""
    mock_config_entry.add_to_hass(hass)

    # Mock authenticate to return False
    mock_instance = mock_google_keep_api.return_value
    mock_instance.authenticate.return_value = False

    # Initialize the options flow
    init_result = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )

    assert init_result["type"] == "abort"
    assert init_result["reason"] == "reauth_required"


@pytest.mark.asyncio
async def test_user_form_cannot_connect(hass: HomeAssistant, mock_google_keep_api):
    """Test the user setup form handles connection issues."""
    mock_instance = mock_google_keep_api.return_value
    mock_instance.authenticate.side_effect = CannotConnectError()

    initial_form_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    user_input = {"username": "testuser@example.com", "password": "testpass"}
    result = await hass.config_entries.flow.async_configure(
        initial_form_result["flow_id"], user_input=user_input
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_reauth_confirm_cannot_connect(hass: HomeAssistant, mock_google_keep_api):
    """Test handling of network issues during reauthentication."""
    # Create a mock entry to simulate existing config entry
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={"username": "user@example.com", "password": "old_password"},
    )
    mock_entry.add_to_hass(hass)

    # Modify the behavior of authenticate to simulate a network connection issue
    mock_instance = mock_google_keep_api.return_value
    mock_instance.authenticate.side_effect = CannotConnectError()

    # Initiate the reauthentication flow
    init_flow_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth", "entry_id": mock_entry.entry_id}
    )

    # Provide the new password input
    new_password_input = {"password": "new_password"}
    config_flow_result = await hass.config_entries.flow.async_configure(
        init_flow_result["flow_id"], new_password_input
    )

    # Assert that a network issue error is returned
    assert config_flow_result["type"] == "form"
    assert config_flow_result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_reauth_confirm_entry_not_found(
    hass: HomeAssistant, mock_google_keep_api
):
    """Test handling when the configuration entry is not found."""
    # Create a mock entry to simulate existing config entry,
    # but don't add it to Home Assistant
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={"username": "user@example.com", "password": "old_password"},
    )

    # Initiate the reauthentication flow with the non-existent entry's ID
    init_flow_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth", "entry_id": mock_entry.entry_id}
    )

    # Provide the new password input
    new_password_input = {"password": "new_password"}
    config_flow_result = await hass.config_entries.flow.async_configure(
        init_flow_result["flow_id"], user_input=new_password_input
    )

    # Assert that the flow is aborted due to the missing config entry
    assert config_flow_result["type"] == "abort"
    assert config_flow_result["reason"] == "config_entry_not_found"
