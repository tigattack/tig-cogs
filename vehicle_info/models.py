from dataclasses import dataclass
from datetime import UTC as dtUTC
from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional, Union

from dateutil.relativedelta import relativedelta
from discord import Colour
from discord.utils import format_dt
from dvla_vehicle_enquiry_service import MotStatus, TaxStatus, Vehicle
from dvsa_mot_history import MotTestTestResult, NewRegVehicleResponse, VehicleWithMotResponse
from redbot.core import utils


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
    make: str
    model: str
    colour: Union[int, Colour]
    vehicle_is_ev: bool
    fuel_type: str
    engine_capacity: Optional[int]
    real_driving_emissions: Optional[str]
    co2_emissions: Optional[int]
    euro_status: Optional[str]
    automated_vehicle: Optional[bool]
    fuel_label: str
    mot_status: str
    tax_status: str
    mot_expiry_date_timestamp: Optional[str] = None
    tax_due_date_timestamp: Optional[str] = None
    date_of_last_v5c_issued_timestamp: Optional[str] = None
    ves_first_registration_timestamp: Optional[str] = None
    ves_first_dvla_registration_timestamp: Optional[str] = None
    mot_first_registration_timestamp: Optional[str] = None
    manufactured_year: Optional[int] = None
    marked_for_export: Optional[bool] = None

    @classmethod
    def from_vehicle(cls, ves_info: Vehicle, mot_info: Union[VehicleWithMotResponse, NewRegVehicleResponse]) -> "VehicleData":
        """Factory method to create VehicleData from Vehicle object"""
        mot_due = mot_info.motTestDueDate if isinstance(mot_info, NewRegVehicleResponse) else ves_info.motExpiryDate

        return cls(
            registration_number=ves_info.registrationNumber.upper(),
            make=ves_info.make,
            model=mot_info.model,
            colour=VehicleColours.get_colour(ves_info.colour),
            vehicle_is_ev=str(ves_info.fuelType).lower() == "electricity",
            fuel_type=str(ves_info.fuelType).title(),
            engine_capacity=ves_info.engineCapacity,
            real_driving_emissions=f"[RDE{ves_info.realDrivingEmissions}](https://www.theaa.com/driving-advice/fuels-environment/euro-emissions-standards#rde-step2)"
            if ves_info.realDrivingEmissions
            else None,
            co2_emissions=ves_info.co2Emissions,
            euro_status=f"[{ves_info.euroStatus}](https://en.wikipedia.org/wiki/European_emission_standards#Toxic_emission:_stages_and_legal_framework)"
            if ves_info.euroStatus
            else None,
            automated_vehicle=ves_info.automatedVehicle,
            fuel_label=cls.generate_fuel_label(ves_info),
            mot_status=cls.format_mot_status(ves_info, mot_info),
            tax_status=cls.format_tax_status(ves_info.taxStatus),
            mot_expiry_date_timestamp=cls.format_timestamp(mot_due),
            tax_due_date_timestamp=cls.format_timestamp(ves_info.taxDueDate),
            date_of_last_v5c_issued_timestamp=cls.format_timestamp(ves_info.dateOfLastV5CIssued),
            ves_first_registration_timestamp=cls.format_timestamp(ves_info.monthOfFirstRegistration, "d"),
            ves_first_dvla_registration_timestamp=cls.format_timestamp(ves_info.monthOfFirstDvlaRegistration, "d"),
            mot_first_registration_timestamp=cls.format_timestamp(mot_info.registrationDate, "d"),
            manufactured_year=ves_info.yearOfManufacture,
            marked_for_export=ves_info.markedForExport,
        )

    @staticmethod
    def generate_fuel_label(ves_info: Vehicle) -> str:
        """Generate the fuel label based on vehicle fuel type"""
        fuel_type = str(ves_info.fuelType).lower()
        if fuel_type in ["petrol", "diesel"]:
            return "Fuel ⛽️"
        elif fuel_type == "hybrid electric":
            return "Fuel ⛽️⚡️"
        elif fuel_type == "electricity":
            return "Fuel ⚡️"
        else:
            return "Fuel"

    @staticmethod
    def format_mot_status(ves_info: Vehicle, mot_info: Union[VehicleWithMotResponse, NewRegVehicleResponse]) -> str:
        """Format MOT status with appropriate styling"""
        mot_status = ves_info.motStatus

        if mot_status == MotStatus.VALID:
            return utils.chat_formatting.success(mot_status.value)
        elif mot_status == MotStatus.NOT_VALID:
            return utils.chat_formatting.error(mot_status.value)
        elif mot_status == MotStatus.NO_DETAILS_HELD and isinstance(mot_info, NewRegVehicleResponse):
            return utils.chat_formatting.success("[<3 years old](https://blog.halfords.com/when-does-a-new-car-need-an-mot/)")
        elif mot_status == MotStatus.NO_DETAILS_HELD and isinstance(mot_info, VehicleWithMotResponse):
            # Sometimes DVLA VES doesn't have a valid result for the last MOT even though
            # the date is within range (1y) and the result is true.
            if mot_info.motTests[0].completedDate > datetime.now(dtUTC) - relativedelta(years=1):
                if mot_info.motTests[0].testResult == MotTestTestResult.PASSED:
                    return utils.chat_formatting.success(MotStatus.VALID.value)
            else:
                return utils.chat_formatting.error("First MOT overdue")

        return mot_status.value if mot_status else utils.chat_formatting.warning("Unknown")

    @staticmethod
    def format_tax_status(tax_status: Optional[TaxStatus]) -> str:
        """Format tax status with appropriate styling"""
        if not tax_status:
            return utils.chat_formatting.warning("No tax details available")
        if tax_status == TaxStatus.TAXED:
            return utils.chat_formatting.success(tax_status.value)
        else:
            return utils.chat_formatting.error(tax_status.value)

    @staticmethod
    def format_timestamp(
        dt: Optional[Union[datetime, date]], style: Optional[Literal["f", "F", "d", "D", "t", "T", "R"]] = "R"
    ) -> Optional[str]:
        """Format a date into a Discord timestamp"""
        if dt:
            if isinstance(dt, date):
                dt = datetime.combine(dt, datetime.min.replace(tzinfo=dtUTC).time())
            return format_dt(dt, style)
        return None
