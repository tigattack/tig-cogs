from datetime import UTC as dtUTC
from datetime import date, datetime
from typing import List, Literal, Optional, Union

from dateutil.relativedelta import relativedelta
from discord.utils import format_dt
from dvla_vehicle_enquiry_service import MotStatus, TaxStatus, VehicleResponse
from dvsa_mot_history import (
    MotTestOdometerResultType,
    MotTestTestResult,
    MotTestType,
    NewRegVehicleResponse,
    VehicleResponseType,
    VehicleWithMotResponse,
)
from redbot.core.utils.chat_formatting import humanize_number

from .additional_vehicle_info import VehicleDetails
from .models import FuelLabels, StatusFormatter, VehicleData


# Factory function to create VehicleData instance
async def build_vehicle_data(
    ves_info: VehicleResponse,
    mot_info: VehicleResponseType,
    additional_info: Optional[VehicleDetails] = None,
    brand_icon_url: Optional[str] = None,
) -> VehicleData:
    """Factory function to create VehicleData from vehicle information"""

    registration_number = get_registration_number(ves_info)
    make = get_make(ves_info, additional_info)
    model = get_model(additional_info, mot_info)
    colour = get_colour(ves_info)
    vehicle_is_ev = is_vehicle_ev(ves_info)
    fuel_type = get_fuel_type(ves_info)
    engine_capacity = ves_info.engineCapacity
    real_driving_emissions = format_real_driving_emissions(ves_info)
    co2_emissions = ves_info.co2Emissions
    euro_status = format_euro_status(ves_info)
    automated_vehicle = ves_info.automatedVehicle
    fuel_label = generate_fuel_label(ves_info)
    mot_status = format_mot_status(ves_info, mot_info)
    tax_status = format_tax_status(ves_info.taxStatus)
    mot_expiry_date_timestamp = format_timestamp(get_mot_due_date(ves_info, mot_info))
    tax_due_date_timestamp = format_timestamp(ves_info.taxDueDate)
    date_of_last_v5c_issued_timestamp = format_timestamp(ves_info.dateOfLastV5CIssued)
    ves_first_registration_timestamp = format_timestamp(ves_info.monthOfFirstRegistration, "d")
    ves_first_dvla_registration_timestamp = format_timestamp(ves_info.monthOfFirstDvlaRegistration, "d")
    mot_first_registration_timestamp = format_timestamp(mot_info.registrationDate, "d")
    manufactured_year = ves_info.yearOfManufacture
    marked_for_export = ves_info.markedForExport
    vin = get_vin(additional_info)
    mot_tests = get_mot_tests(mot_info)
    is_new_vehicle = get_is_new_vehicle(mot_info)

    return VehicleData(
        registration_number=registration_number,
        make=make,
        model=model,
        colour=colour,
        vehicle_is_ev=vehicle_is_ev,
        fuel_type=fuel_type,
        engine_capacity=engine_capacity,
        real_driving_emissions=real_driving_emissions,
        co2_emissions=co2_emissions,
        euro_status=euro_status,
        automated_vehicle=automated_vehicle,
        fuel_label=fuel_label,
        mot_status=mot_status,
        tax_status=tax_status,
        mot_expiry_date_timestamp=mot_expiry_date_timestamp,
        tax_due_date_timestamp=tax_due_date_timestamp,
        date_of_last_v5c_issued_timestamp=date_of_last_v5c_issued_timestamp,
        ves_first_registration_timestamp=ves_first_registration_timestamp,
        ves_first_dvla_registration_timestamp=ves_first_dvla_registration_timestamp,
        mot_first_registration_timestamp=mot_first_registration_timestamp,
        manufactured_year=manufactured_year,
        marked_for_export=marked_for_export,
        vin=vin,
        mot_tests=mot_tests,
        is_new_vehicle=is_new_vehicle,
        brand_icon_url=brand_icon_url,
    )


# Getter, generator, and formatter functions


def get_registration_number(ves_info: VehicleResponse) -> str:
    """Returns uppercase registration number"""
    return ves_info.registrationNumber.upper()


def get_make(ves_info: VehicleResponse, additional_info: Optional[VehicleDetails]) -> Optional[str]:
    """Get make from vehicle information or additional info"""
    return ves_info.make or (additional_info.Manufacturer if additional_info else None)


def get_model(additional_info: Optional[VehicleDetails], mot_info: VehicleResponseType) -> Optional[str]:
    """Get model from vehicle information or additional info"""
    return additional_info.Model if additional_info and additional_info.Model else mot_info.model


def get_colour(ves_info: VehicleResponse) -> Optional[str]:
    """Returns title-case colour from vehicle information"""
    return ves_info.colour.title()


def is_vehicle_ev(ves_info: VehicleResponse) -> bool:
    """Returns true if vehicle is electric"""
    return str(ves_info.fuelType).lower() == "electricity"


def get_fuel_type(ves_info: VehicleResponse) -> Optional[str]:
    """Get title-case fuel type from vehicle information"""
    return str(ves_info.fuelType).title() if ves_info.fuelType else None


def get_mot_due_date(ves_info: VehicleResponse, mot_info: VehicleResponseType) -> Optional[Union[datetime, date]]:
    """Get MOT due date from vehicle information or MOT info"""
    return ves_info.motExpiryDate if isinstance(mot_info, VehicleWithMotResponse) else mot_info.motTestDueDate


def get_vin(additional_info: Optional[VehicleDetails]) -> Optional[str]:
    """Get VIN from additional info"""
    return additional_info.VIN if additional_info else None


def get_mot_tests(mot_info: VehicleResponseType) -> Optional[List[MotTestType]]:
    """Returns a list of MOT tests if mot_info is of type VehicleWithMotResponse"""
    return mot_info.motTests if isinstance(mot_info, VehicleWithMotResponse) else None


def get_is_new_vehicle(mot_info: VehicleResponseType) -> bool:
    """Returns true if mot_info is of type NewRegVehicleResponse"""
    return isinstance(mot_info, NewRegVehicleResponse)


def get_mot_test_results(mot_tests: Optional[List[MotTestType]]) -> List[str]:
    """Get formatted MOT test results for the embed."""
    if not mot_tests:
        return []

    test_results = []
    for test in mot_tests[:5]:
        test_result = (
            StatusFormatter.format_ok("") if test.testResult == MotTestTestResult.PASSED else StatusFormatter.format_error("")
        )
        test_results.append(test_result)
    return test_results


def get_last_known_mileage(mot_tests: Optional[List[MotTestType]]) -> Optional[str]:
    """Get the last known mileage for the vehicle."""
    if not mot_tests:
        return None

    last_test = mot_tests[0]
    last_mot_mileage_humanised = humanize_number(last_test.odometerValue) if last_test.odometerValue else None
    last_mot_timestamp = format_timestamp(last_test.completedDate, "d")
    last_mot_odo_unit = last_test.odometerUnit.value.lower() if last_test.odometerUnit and last_test.odometerUnit.value else ''

    if last_test.odometerResultType == MotTestOdometerResultType.READ:
        return f"{last_mot_mileage_humanised}{last_mot_odo_unit} ({last_mot_timestamp})"
    else:
        return StatusFormatter.format_warning(f"Unknown - {last_test.odometerResultType.value.title()}")


def get_vehicle_has_failed_mots(mot_tests: Optional[List[MotTestType]]) -> bool:
    """Get whether the vehicle has failed MOTs."""
    if not mot_tests:
        return False
    return any(test.testResult == MotTestTestResult.FAILED for test in mot_tests)


def generate_fuel_label(ves_info: VehicleResponse) -> Optional[str]:
    """Generate formatted fuel label depending on fuel type"""
    if not ves_info.fuelType:
        return None

    fuel_label = "Fuel "
    fuel_type = str(ves_info.fuelType).lower()

    if fuel_type in ["petrol", "diesel"]:
        fuel_label += FuelLabels.ICE.value
    elif fuel_type == "hybrid electric":
        fuel_label += FuelLabels.HYBRID.value
    elif fuel_type == "electricity":
        fuel_label += FuelLabels.ELECTRIC.value

    return fuel_label


def format_real_driving_emissions(ves_info: VehicleResponse) -> Optional[str]:
    """Format real driving emissions into a markdown link with further information"""
    if not ves_info.realDrivingEmissions:
        return None
    return f"[RDE{ves_info.realDrivingEmissions}](https://www.theaa.com/driving-advice/fuels-environment/euro-emissions-standards#rde-step2)"


def format_euro_status(ves_info: VehicleResponse) -> Optional[str]:
    """Format EURO emissions status into a markdown link with further information"""
    if not ves_info.euroStatus:
        return None
    return f"[{ves_info.euroStatus}](https://en.wikipedia.org/wiki/European_emission_standards#Toxic_emission:_stages_and_legal_framework)"


def format_mot_status(ves_info: VehicleResponse, mot_info: VehicleResponseType) -> Optional[str]:
    """Returns a formatted MOT status"""
    mot_status = ves_info.motStatus
    if mot_status == MotStatus.VALID:
        status = StatusFormatter.format_ok(mot_status.value)
    elif mot_status == MotStatus.NOT_VALID:
        status = StatusFormatter.format_error(mot_status.value)
    elif mot_status == MotStatus.NO_DETAILS_HELD and isinstance(mot_info, NewRegVehicleResponse):
        status = StatusFormatter.format_neutral(
            "[Exempt](https://www.theaa.com/mot/advice/when-does-my-vehicle-need-its-first-mot)"
        )
    elif mot_status == MotStatus.NO_DETAILS_HELD and isinstance(mot_info, VehicleWithMotResponse):
        if mot_info.motTests and mot_info.motTests[0].completedDate > datetime.now(dtUTC) - relativedelta(years=1):
            if mot_info.motTests[0].testResult == MotTestTestResult.PASSED:
                status = StatusFormatter.format_ok(MotStatus.VALID.value)
        else:
            status = StatusFormatter.format_error("First MOT overdue")
    else:
        status = StatusFormatter.format_unknown("Unknown")

    return status


def format_tax_status(tax_status: Optional[TaxStatus]) -> Optional[str]:
    """Returns a formatted tax status"""
    if not tax_status:
        return StatusFormatter.format_unknown("No details available")
    if tax_status == TaxStatus.TAXED:
        return StatusFormatter.format_ok(tax_status.value)
    else:
        return StatusFormatter.format_error(tax_status.value)


def format_timestamp(
    dt: Optional[Union[datetime, date]], style: Optional[Literal["f", "F", "d", "D", "t", "T", "R"]] = "R"
) -> Optional[str]:
    """Format a timestamp into a Discord timestamp string"""
    if not dt:
        return None
    if isinstance(dt, date):
        dt = datetime.combine(dt, datetime.min.replace(tzinfo=dtUTC).time())
    return format_dt(dt, style)
