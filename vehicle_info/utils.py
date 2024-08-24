import logging
from io import BytesIO
from typing import Literal, Optional

import aiohttp
from CelticTuning import Celtic
from discord import Embed
from dvla_vehicle_enquiry_service import ErrorResponse as VesErrorResponse
from dvla_vehicle_enquiry_service import Vehicle, VehicleEnquiryAPI
from dvsa_mot_history import ErrorResponse as MotHistoryErrorResponse
from dvsa_mot_history import (
    MOTHistory,
    MotTestOdometerResultType,
    MotTestTestResult,
    NewRegVehicleResponse,
    VehicleWithMotResponse,
)
from PIL import Image
from redbot.core.utils.chat_formatting import humanize_number

from .additional_vehicle_info import VehicleLookupAPI
from .models import StatusFormatter, VehicleColours, VehicleData, build_vehicle_data, format_timestamp, get_make

log = logging.getLogger("red.tigattack.vehicle_info.utils")


async def get_vehicle_info(
    vrn: str,
    dvla_ves_token: dict[str, str],
    dvsa_mot_history_token: dict[str, str],
    additional_vehicle_api_cfg: dict[str, str],
) -> Optional[VehicleData]:
    """Get vehicle info"""

    # Validate tokens
    if dvla_ves_token.get("token") is None:
        raise ValueError("DVLA Vehicle Enquiry Service API token not found")

    for cred in ["client_id", "client_secret", "tenant_id", "api_key"]:
        if dvsa_mot_history_token.get(cred) is None:
            raise ValueError(f"DVSA MOT History API {cred} not found")

    # Fetch vehicle data from DVLA VES
    ves_info = await _get_dvla_ves_info(vrn, dvla_ves_token)

    if isinstance(ves_info, VesErrorResponse):
        errors = [
            f"{error.status}: {error.title}" + (f" - {error.detail}" if error.detail else "") for error in ves_info.errors
        ]
        log.exception(", ".join(errors))
        if int(ves_info.errors[0].status) == 400:  # noqa: PLR2004
            return None

    # Fetch MOT data from DVSA
    mot_info = await _get_dvsa_mot_info(vrn, dvsa_mot_history_token)

    if isinstance(mot_info, MotHistoryErrorResponse):
        error = f"{mot_info.status_code}: {mot_info.message} - Errors: {', '.join(mot_info.errors)}"
        log.exception(error)
        raise ValueError(f"Error querying MOT History API: {error}")

    # Fetch additional vehicle details if API configuration is provided
    additional_info = None
    if additional_vehicle_api_cfg.get("base_url"):
        additional_info_api = VehicleLookupAPI(
            additional_vehicle_api_cfg["base_url"],
            additional_vehicle_api_cfg.get("user_agent"),
        )
        additional_info = await additional_info_api.get_vehicle_details(vrn)

    make = get_make(ves_info, additional_info)
    brand_icon_url = await _get_brand_icon(make) if make else None

    # Build VehicleData
    vehicle_data = await build_vehicle_data(
        ves_info=ves_info,
        mot_info=mot_info,
        additional_info=additional_info,
        brand_icon_url=brand_icon_url,
    )

    return vehicle_data


async def gen_vehicle_embed(vehicle_data: VehicleData) -> Embed:
    """Helper method to generate a vehicle embed"""

    embed = Embed(
        title=(
            f"{vehicle_data.registration_number} | {vehicle_data.manufactured_year} {vehicle_data.make} {vehicle_data.model}"
        ),
        colour=VehicleColours.get_colour(vehicle_data.colour),
    )

    if vehicle_data.brand_icon_url:
        embed.set_thumbnail(url=vehicle_data.brand_icon_url)

    # Dynamically build the embed fields based on VehicleData attributes
    fields_to_include = {
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

    for name, value in fields_to_include.items():
        if value:
            embed.add_field(name=name, value=value, inline=True)

    if vehicle_data.vin is None:
        embed.set_footer(
            text="Additional info such as full model, VIN, etc. not available. "
            + "Check `[p]vehicle_info additional_vehicle_info_config`."
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

    test_results: list[str] = []
    has_failed = False
    mileage: Optional[str] = None
    if vehicle_data.mot_tests:
        has_failed = any(test.testResult == MotTestTestResult.FAILED for test in vehicle_data.mot_tests)
        if has_failed:
            for test in vehicle_data.mot_tests[:5]:
                test_results.append(
                    StatusFormatter.format_ok("")
                    if test.testResult == MotTestTestResult.PASSED
                    else StatusFormatter.format_error("")
                )

        last_mot_mileage_humanised = humanize_number(vehicle_data.mot_tests[0].odometerValue)
        last_mot_timestamp = format_timestamp(vehicle_data.mot_tests[0].completedDate, "d")
        mileage = (
            f"{last_mot_mileage_humanised} {vehicle_data.mot_tests[0].odometerUnit.value} ({last_mot_timestamp})"
            if vehicle_data.mot_tests[0].odometerResultType == MotTestOdometerResultType.READ
            else StatusFormatter.format_warning(f"Unknown - {vehicle_data.mot_tests[0].odometerResultType.value.title()}")
        )

    test_history = StatusFormatter.format_ok("Never failed") if not has_failed and vehicle_data.is_new_vehicle else None

    fields = {
        "MOT Status": vehicle_data.mot_status,
        "MOT Expiry": vehicle_data.mot_expiry_date_timestamp,
        "Last 5 Results": "".join(reversed(test_results)),
        "MOT Test History": test_history,
        "Last Known Mileage": mileage,
    }

    for name, value in fields.items():
        if value:
            embed.add_field(name=name, value=value, inline=True)

    return embed


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


async def _fetch_get(url_in: str, headers: dict = {}, data: dict = {}) -> dict:
    """Make web requests"""
    async with aiohttp.request("GET", url_in, headers=headers, data=data) as response:
        if response.status != 200:  # noqa: PLR2004
            return {}
        return await response.json()


async def _get_brand_domain(brand: str) -> str:
    """Get brand info from a brand name"""
    url = f"https://api.brandfetch.io/v2/search/{brand}"
    response = await _fetch_get(url)
    return response[0]["domain"]


async def _get_brand_icon(
    brand_domain: str,
    theme: Literal["light", "dark"] = "light",
) -> Optional[str]:
    """Get brand icon from a brand name and detect its true resolution"""

    async def _fetch_image(image_url: str) -> tuple[int, int]:
        headers = {"User-Agent": "curl/8.6.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, headers=headers) as response:
                if response.status != 200:  # noqa: PLR2004
                    raise ValueError("Failed to fetch the brand icon.")
                if response.headers.get("Content-Type") != "image/webp":
                    raise ValueError("Invalid image format. May need to use a different user agent.")
                image_data = await response.read()

        image = Image.open(BytesIO(image_data))
        return image.size

    # Set the desired width and aspect ratio tolerance
    width = 512
    fallback_width = 256
    aspect_ratio_tolerance = 0.2

    # Get the domain for the brand
    brand_domain = await _get_brand_domain(brand_domain)

    # Logo as desired
    # Logo with the fallback width
    # Logo without specifying a theme
    # Brand icon (usually not transparent, often not a "clean" logo)
    image_urls = [
        f"https://cdn.brandfetch.io/{brand_domain}/w/{width}/theme/{theme}/logo",
        f"https://cdn.brandfetch.io/{brand_domain}/w/{fallback_width}/theme/{theme}/logo",
        f"https://cdn.brandfetch.io/{brand_domain}/w/{width}/logo",
        f"https://cdn.brandfetch.io/{brand_domain}/logo",
        f"https://cdn.brandfetch.io/{brand_domain}",
    ]

    # Construct the image URL
    image_url = f"https://cdn.brandfetch.io/{brand_domain}/w/{width}/theme/{theme}/logo"

    # Fetch the image data
    icon_res = await _fetch_image(image_url)

    # Iterate through URLs to find the best matching image.
    # There are a few ways in which an image in the the desired format can be unavailable:
    # - The resolution is unavailable
    # - The theme is unavailable
    # - A logo for the brand is not available
    for image_url in image_urls:
        icon_res = await _fetch_image(image_url)
        aspect_ratio = icon_res[0] / icon_res[1]

        # Check image is square with 20% tolerance
        if 1 - aspect_ratio_tolerance <= aspect_ratio <= 1 + aspect_ratio_tolerance:
            return image_url
        else:
            continue

    log.warning("Failed to find a valid brand logo or icon for %s.", brand_domain)
    return None
