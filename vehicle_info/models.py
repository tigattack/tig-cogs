from datetime import UTC as dtUTC
from datetime import date, datetime
from enum import Enum
from typing import List, Literal, Optional, Union

from dateutil.relativedelta import relativedelta
from discord import Colour
from discord.utils import format_dt
from dvla_vehicle_enquiry_service import MotStatus, TaxStatus, Vehicle
from dvsa_mot_history import (
    CVSMotTest,
    DVANIMotTest,
    DVSAMotTest,
    MotTestTestResult,
    NewRegVehicleResponse,
    VehicleWithMotResponse,
)
from pydantic.dataclasses import dataclass
from redbot.core import chat_formatting

from vehicle_info.additional_vehicle_info import VehicleDetails


class VehicleColours(Enum):
    r"""
    Vehicle colours used by the DVLA

    Colours sourced from:
    https://hmvf.co.uk/topic/23542-dvla-vehicle-basic-colours-to-cover-the-manufacturer%E2%80%99s-description/
    Couldn't find any better source ¯\\_(ツ)_/¯
    """

    BEIGE = 0xF5F5DC
    BLACK = 0x000000
    BLUE = Colour.dark_blue()
    BRONZE = 0xCD7F32
    BROWN = 0x8B4513
    CREAM = 0xFFFCDC
    GREEN = Colour.dark_green()
    GREY = Colour.dark_grey()
    GOLD = Colour.gold()
    MAROON = Colour.dark_red()
    ORANGE = Colour.orange()
    PINK = Colour.pink()
    PURPLE = Colour.purple()
    RED = Colour.red()
    SILVER = 0xC0C0C0
    TURQUOISE = 0x40E0D0
    WHITE = 0xFFFFFF
    YELLOW = Colour.yellow()

    @classmethod
    def get_colour(cls, colour_name: Optional[str]) -> Union[int, Colour]:
        """Get the colour value by its name, case-insensitively."""
        if colour_name:
            colour_name = colour_name.upper()
            for colour in cls:
                if colour_name == colour.name:
                    return colour.value
        return cls.GREY.value


@dataclass
class VehicleData:
    """Dataclass to hold processed vehicle information"""

    registration_number: str
    make: Optional[str]
    model: Optional[str]
    colour: Optional[str]
    vehicle_is_ev: bool
    fuel_type: Optional[str]
    engine_capacity: Optional[int]
    real_driving_emissions: Optional[str]
    co2_emissions: Optional[int]
    euro_status: Optional[str]
    automated_vehicle: Optional[bool]
    fuel_label: Optional[str]
    mot_status: Optional[str]
    tax_status: Optional[str]
    mot_expiry_date_timestamp: Optional[str]
    tax_due_date_timestamp: Optional[str]
    date_of_last_v5c_issued_timestamp: Optional[str]
    ves_first_registration_timestamp: Optional[str]
    ves_first_dvla_registration_timestamp: Optional[str]
    mot_first_registration_timestamp: Optional[str]
    manufactured_year: Optional[int]
    marked_for_export: Optional[bool]
    vin: Optional[str]
    mot_tests: Optional[List[Union[DVSAMotTest, DVANIMotTest, CVSMotTest]]]

    @property
    def first_registered_globally(self) -> Optional[str]:
        """Get the first registered date globally"""
        return self.mot_first_registration_timestamp or self.ves_first_registration_timestamp

    @property
    def first_registered_uk(self) -> Optional[str]:
        """Get the first registered date in the UK"""
        return self.ves_first_dvla_registration_timestamp

    @property
    def conditional_real_driving_emissions(self) -> Optional[str]:
        """Get real driving emissions formatted"""
        return self.real_driving_emissions if self.real_driving_emissions and not self.vehicle_is_ev else None

    @property
    def conditional_tax_due_date(self) -> Optional[str]:
        """Get tax due date formatted"""
        return self.tax_due_date_timestamp if self.tax_status and "SORN" not in self.tax_status else None

    @property
    def engine_capacity_formatted(self) -> Optional[str]:
        """Get engine capacity formatted"""
        return f"{self.engine_capacity} cc" if self.engine_capacity and not self.vehicle_is_ev else None

    @property
    def co2_emissions_formatted(self) -> Optional[str]:
        """Get CO² emissions formatted"""
        return f"{self.co2_emissions} g/km" if self.co2_emissions and not self.vehicle_is_ev else None

    @property
    def automated_vehicle_formatted(self) -> Optional[str]:
        """Get if the vehicle is an automated vehicle"""
        return str(self.automated_vehicle) if self.automated_vehicle else None

    @property
    def marked_for_export_formatted(self) -> Optional[str]:
        """Get if the vehicle is marked for export"""
        return chat_formatting.success("") if self.marked_for_export else None


# Factory function to create VehicleData instance
async def build_vehicle_data(
    ves_info: Vehicle,
    mot_info: Union[VehicleWithMotResponse, NewRegVehicleResponse],
    additional_info: Optional[VehicleDetails] = None,
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
    )


# Getter, generator, and formatter functions


def get_registration_number(ves_info: Vehicle) -> str:
    """Returns uppercase registration number"""
    return ves_info.registrationNumber.upper()


def get_make(ves_info: Vehicle, additional_info: Optional[VehicleDetails]) -> Optional[str]:
    """Get make from vehicle information or additional info"""
    return ves_info.make or (additional_info.Manufacturer if additional_info else None)


def get_model(
    additional_info: Optional[VehicleDetails], mot_info: Union[VehicleWithMotResponse, NewRegVehicleResponse]
) -> Optional[str]:
    """Get model from vehicle information or additional info"""
    return additional_info.Model if additional_info and additional_info.Model else mot_info.model


def get_colour(ves_info: Vehicle) -> Optional[str]:
    """Returns title-case colour from vehicle information"""
    return ves_info.colour.title()


def is_vehicle_ev(ves_info: Vehicle) -> bool:
    """Returns true if vehicle is electric"""
    return str(ves_info.fuelType).lower() == "electricity"


def get_fuel_type(ves_info: Vehicle) -> Optional[str]:
    """Get title-case fuel type from vehicle information"""
    return str(ves_info.fuelType).title() if ves_info.fuelType else None


def get_mot_due_date(
    ves_info: Vehicle, mot_info: Union[VehicleWithMotResponse, NewRegVehicleResponse]
) -> Optional[Union[datetime, date]]:
    """Get MOT due date from vehicle information or MOT info"""
    return ves_info.motExpiryDate if isinstance(mot_info, VehicleWithMotResponse) else mot_info.motTestDueDate


def get_vin(additional_info: Optional[VehicleDetails]) -> Optional[str]:
    """Get VIN from additional info"""
    return additional_info.VIN if additional_info else None


def get_mot_tests(
    mot_info: Union[VehicleWithMotResponse, NewRegVehicleResponse],
) -> Optional[List[Union[DVSAMotTest, DVANIMotTest, CVSMotTest]]]:
    """Returns a list of MOT tests if mot_info is of type VehicleWithMotResponse"""
    return mot_info.motTests if isinstance(mot_info, VehicleWithMotResponse) else None


def generate_fuel_label(ves_info: Vehicle) -> Optional[str]:
    """Generate formatted fuel label depending on fuel type"""
    if not ves_info.fuelType:
        return None
    fuel_type = str(ves_info.fuelType).lower()
    if fuel_type in ["petrol", "diesel"]:
        return "Fuel ⛽️"
    elif fuel_type == "hybrid electric":
        return "Fuel ⛽️⚡️"
    elif fuel_type == "electricity":
        return "Fuel ⚡️"
    else:
        return "Fuel"


def format_real_driving_emissions(ves_info: Vehicle) -> Optional[str]:
    """Format real driving emissions into a markdown link with further information"""
    if not ves_info.realDrivingEmissions:
        return None
    return f"[RDE{ves_info.realDrivingEmissions}](https://www.theaa.com/driving-advice/fuels-environment/euro-emissions-standards#rde-step2)"


def format_euro_status(ves_info: Vehicle) -> Optional[str]:
    """Format EURO emissions status into a markdown link with further information"""
    if not ves_info.euroStatus:
        return None
    return f"[{ves_info.euroStatus}](https://en.wikipedia.org/wiki/European_emission_standards#Toxic_emission:_stages_and_legal_framework)"


def format_mot_status(ves_info: Vehicle, mot_info: Union[VehicleWithMotResponse, NewRegVehicleResponse]) -> Optional[str]:
    """Returns a formatted MOT status"""
    if not ves_info.motStatus:
        status = utils.chat_formatting.warning("Unknown")
    mot_status = ves_info.motStatus
    if mot_status == MotStatus.VALID:
        status = utils.chat_formatting.success(mot_status.value)
    elif mot_status == MotStatus.NOT_VALID:
        status = utils.chat_formatting.error(mot_status.value)
    elif mot_status == MotStatus.NO_DETAILS_HELD and isinstance(mot_info, NewRegVehicleResponse):
        status = utils.chat_formatting.success("[<3 years old](https://blog.halfords.com/when-does-a-new-car-need-an-mot/)")
    elif mot_status == MotStatus.NO_DETAILS_HELD and isinstance(mot_info, VehicleWithMotResponse):
        if mot_info.motTests and mot_info.motTests[0].completedDate > datetime.now(dtUTC) - relativedelta(years=1):
            if mot_info.motTests[0].testResult == MotTestTestResult.PASSED:
                status = utils.chat_formatting.success(MotStatus.VALID.value)
        else:
            status = utils.chat_formatting.error("First MOT overdue")
    else:
        status = mot_status.value

    return status


def format_tax_status(tax_status: Optional[TaxStatus]) -> Optional[str]:
    """Returns a formatted tax status"""
    if not tax_status:
        return utils.chat_formatting.warning("No tax details available")
    if tax_status == TaxStatus.TAXED:
        return utils.chat_formatting.success(tax_status.value)
    else:
        return utils.chat_formatting.error(tax_status.value)


def format_timestamp(
    dt: Optional[Union[datetime, date]], style: Optional[Literal["f", "F", "d", "D", "t", "T", "R"]] = "R"
) -> Optional[str]:
    """Format a timestamp into a Discord timestamp string"""
    if not dt:
        return None
    if isinstance(dt, date):
        dt = datetime.combine(dt, datetime.min.replace(tzinfo=dtUTC).time())
    return format_dt(dt, style)
