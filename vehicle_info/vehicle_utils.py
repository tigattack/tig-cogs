import logging
from typing import Optional

from CelticTuning import Celtic
from discord import Embed
from dvla_vehicle_enquiry_service import ErrorResponse as VesErrorResponse
from dvla_vehicle_enquiry_service import Vehicle, VehicleEnquiryAPI
from dvsa_mot_history import ErrorResponse as MotHistoryErrorResponse
from dvsa_mot_history import (
    MOTHistory,
    NewRegVehicleResponse,
    VehicleWithMotResponse,
)

from .additional_vehicle_info import VehicleDetails, VehicleLookupAPI
from .brand_icons import get_brand_icon
from .models import StatusFormatter, VehicleColours, VehicleData
from .vehicle_factory import (
    build_vehicle_data,
    get_last_known_mileage,
    get_make,
    get_mot_test_results,
    get_vehicle_has_failed_mots,
)

log = logging.getLogger("red.tigattack.vehicle_info.utils")


async def fetch_vehicle_data(
    vrn: str,
    dvla_ves_token: dict[str, str],
    dvsa_mot_history_token: dict[str, str],
    additional_vehicle_api_cfg: dict[str, str],
) -> Optional[VehicleData]:
    """Fetch vehicle data from APIs and build VehicleData."""

    # Validate tokens
    if dvla_ves_token.get("token") is None:
        raise ValueError("DVLA Vehicle Enquiry Service API token not found")

    for cred in ["client_id", "client_secret", "tenant_id", "api_key"]:
        if dvsa_mot_history_token.get(cred) is None:
            raise ValueError(f"DVSA MOT History API {cred} not found")

    # Fetch vehicle data from DVLA VES
    ves_info = await _get_dvla_ves_info(vrn, dvla_ves_token)

    if isinstance(ves_info, VesErrorResponse):
        _log_ves_error(ves_info.errors)
        return None

    # Fetch MOT data from DVSA
    mot_info = await _get_dvsa_mot_info(vrn, dvsa_mot_history_token)

    if isinstance(mot_info, MotHistoryErrorResponse):
        _log_mot_error(mot_info)
        raise ValueError("Error querying MOT History API")

    additional_info = await _fetch_additional_info(vrn, additional_vehicle_api_cfg)
    make = get_make(ves_info, additional_info)
    brand_icon_url = await get_brand_icon(make) if make else None

    # Build & return VehicleData
    return await build_vehicle_data(
        ves_info=ves_info,
        mot_info=mot_info,
        additional_info=additional_info,
        brand_icon_url=brand_icon_url,
    )


async def generate_vehicle_embed(vehicle_data: VehicleData) -> Embed:
    """Generate an embed for vehicle data."""
    embed = Embed(
        title=(
            f"{vehicle_data.registration_number} | {vehicle_data.manufactured_year} {vehicle_data.make} {vehicle_data.model}"
        ),
        colour=VehicleColours.get_colour(vehicle_data.colour),
    )

    if vehicle_data.brand_icon_url:
        embed.set_thumbnail(url=vehicle_data.brand_icon_url)

    fields = _build_vehicle_embed_fields(vehicle_data)
    for name, value in fields.items():
        if value:
            embed.add_field(name=name, value=value, inline=True)

    if vehicle_data.vin is None:
        embed.set_footer(
            text="Additional info such as full model, VIN, etc. not available. "
            "Check `[p]vehicle_info additional_vehicle_info_config`."
        )
    return embed


async def gen_mot_embed(vehicle_data: VehicleData) -> Embed:
    """Helper method to generate an embed with extended MOT info"""

    embed = Embed(
        title=(
            f"{vehicle_data.registration_number} | {vehicle_data.manufactured_year} {vehicle_data.make} {vehicle_data.model}"
        ),
        colour=VehicleColours.get_colour(vehicle_data.colour),
    )

    if vehicle_data.brand_icon_url:
        embed.set_thumbnail(url=vehicle_data.brand_icon_url)

    # Determine if there has been any failed MOT test
    has_failed = get_vehicle_has_failed_mots(vehicle_data.mot_tests)

    # Create test results summary for the last 5 MOT tests
    test_results = get_mot_test_results(vehicle_data.mot_tests)

    # Get last known mileage details
    mileage = get_last_known_mileage(vehicle_data.mot_tests)

    # MOT test history text
    test_history = StatusFormatter.format_ok("Never failed") if not has_failed and vehicle_data.is_new_vehicle else None

    # Define fields for the embed
    fields = {
        "MOT Status": vehicle_data.mot_status,
        "MOT Expiry": vehicle_data.mot_expiry_date_timestamp,
        "Last 5 Results": "".join(reversed(test_results)),
        "MOT Test History": test_history,
        "Last Known Mileage": mileage,
    }

    # Add fields to the embed if they have values
    for name, value in fields.items():
        if value:
            embed.add_field(name=name, value=value, inline=True)

    return embed


async def _fetch_additional_info(vrn: str, api_cfg: dict[str, str]) -> Optional[VehicleDetails]:
    """Fetch additional vehicle details if API configuration is provided."""
    if api_cfg.get("base_url"):
        api = VehicleLookupAPI(api_cfg["base_url"], api_cfg.get("user_agent"))
        return await api.get_vehicle_details(vrn)
    return None


async def _get_dvla_ves_info(vrn: str, dvla_ves_token: dict[str, str]) -> Vehicle | VesErrorResponse:
    """Get vehicle info from DVLA Vehicle Enquiry Service API"""
    ves_api = VehicleEnquiryAPI(dvla_ves_token["token"])
    ves_info = await ves_api.get_vehicle(vrn)
    return ves_info


async def _get_dvsa_mot_info(
    vrn: str, dvsa_mot_history_token: dict[str, str]
) -> VehicleWithMotResponse | NewRegVehicleResponse | MotHistoryErrorResponse:
    """Get MOT info from DVSA MOT History API"""
    mot_api = MOTHistory(
        dvsa_mot_history_token["client_id"],
        dvsa_mot_history_token["client_secret"],
        dvsa_mot_history_token["tenant_id"],
        dvsa_mot_history_token["api_key"],
    )
    mot_info = await mot_api.get_vehicle_history_by_registration(vrn)
    return mot_info


async def _get_vehicle_remap_estimate(vrn: str) -> dict:
    """Get vehicle remap estimate"""
    ct = Celtic(vrn)
    remap = ct.remap_data()

    # TODO: build embed

    return remap


def _build_vehicle_embed_fields(vehicle_data: VehicleData) -> dict[Optional[str], Optional[str]]:
    """Build fields for the vehicle embed."""
    return {
        "Colour": vehicle_data.colour,
        vehicle_data.fuel_label: vehicle_data.fuel_type,
        "Engine Capacity": vehicle_data.engine_capacity_formatted,
        "First Registered": vehicle_data.first_registered_globally,
        "First Registered in UK": vehicle_data.first_registered_uk,
        "V5C Last Issued": vehicle_data.date_of_last_v5c_issued_timestamp,
        "Tax Status": vehicle_data.tax_status,
        "Tax Expiry": vehicle_data.conditional_tax_due_date,
        "MOT Status": vehicle_data.mot_status,
        "MOT Expiry": vehicle_data.mot_expiry_date_timestamp,
        "CO₂ Emissions": vehicle_data.co2_emissions_formatted,
        "Euro Status": vehicle_data.euro_status,
        "Real Driving Emissions": vehicle_data.conditional_real_driving_emissions,
        "Automated Vehicle": vehicle_data.automated_vehicle_formatted,
        "Marked for Export": vehicle_data.marked_for_export_formatted,
        "VIN": vehicle_data.vin,
    }


def _log_ves_error(errors):
    """Log errors."""
    error_messages = [f"{error.status}: {error.title}" + (f" - {error.detail}" if error.detail else "") for error in errors]
    log.exception(", ".join(error_messages))


def _log_mot_error(error_response):
    """Log error response."""
    err_strings = " - " + ", ".join(error_response.errors) if error_response.errors else ""
    error_message = f"{error_response.status_code}: {error_response.message}{err_strings}"
    log.exception(error_message)
