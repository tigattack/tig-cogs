from enum import Enum
from typing import List, Optional, Union

from discord import Colour
from dvsa_mot_history import (
    CVSMotTest,
    DVANIMotTest,
    DVSAMotTest,
)
from pydantic.dataclasses import dataclass


class VehicleColours(Enum):
    r"""
    Vehicle colours used by the DVLA.

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


class StatusFormatter(Enum):
    """Formatter for status strings."""

    OK = "🟢"
    WARNING = "🟠"
    ERROR = "🔴"
    UNKNOWN = WARNING
    NEUTRL = "⚪"

    @classmethod
    def format_ok(cls, text: str) -> str:
        """Get text prefixed with an OK status emote."""
        return f"{cls.OK.value} {text}"

    @classmethod
    def format_warning(cls, text: str) -> str:
        """Get text prefixed with a warning status emote."""
        return f"{cls.WARNING.value} {text}"

    @classmethod
    def format_error(cls, text: str) -> str:
        """Get text prefixed with an error status emote."""
        return f"{cls.ERROR.value} {text}"

    @classmethod
    def format_unknown(cls, text: str) -> str:
        """Get text prefixed with an unknown status emote."""
        return cls.format_warning(text)

    @classmethod
    def format_neutral(cls, text: str) -> str:
        """Get text prefixed with an neutral status emote."""
        return f"{cls.NEUTRL.value} {text}"


class FuelLabels(Enum):
    """Fuel labels for each vehicle fuel type."""

    ICE = "⛽️"
    HYBRID = "⛽️⚡️"
    ELECTRIC = "⚡️"


@dataclass
class VehicleData:
    """Dataclass to hold processed vehicle information."""

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
    is_new_vehicle: Optional[bool]
    brand_icon_url: Optional[str]

    @property
    def first_registered_globally(self) -> Optional[str]:
        """Get the first registered date globally."""
        return self.mot_first_registration_timestamp or self.ves_first_registration_timestamp

    @property
    def first_registered_uk(self) -> Optional[str]:
        """Get the first registered date in the UK."""
        return self.ves_first_dvla_registration_timestamp

    @property
    def conditional_real_driving_emissions(self) -> Optional[str]:
        """Get real driving emissions formatted."""
        return self.real_driving_emissions if self.real_driving_emissions and not self.vehicle_is_ev else None

    @property
    def conditional_tax_due_date(self) -> Optional[str]:
        """Get tax due date formatted."""
        return self.tax_due_date_timestamp if self.tax_status and "SORN" not in self.tax_status else None

    @property
    def engine_capacity_formatted(self) -> Optional[str]:
        """Get engine capacity formatted."""
        return f"{self.engine_capacity} cc" if self.engine_capacity and not self.vehicle_is_ev else None

    @property
    def co2_emissions_formatted(self) -> Optional[str]:
        """Get CO² emissions formatted."""
        return f"{self.co2_emissions} g/km" if self.co2_emissions and not self.vehicle_is_ev else None

    @property
    def automated_vehicle_formatted(self) -> Optional[str]:
        """Get if the vehicle is an automated vehicle."""
        return str(self.automated_vehicle) if self.automated_vehicle else None

    @property
    def marked_for_export_formatted(self) -> Optional[str]:
        """Get if the vehicle is marked for export."""
        return str(self.marked_for_export) if self.marked_for_export else None
