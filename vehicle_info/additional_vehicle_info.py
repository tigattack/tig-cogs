"""Wrapper for undisclosed additional vehicle information API"""

import logging
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Optional

from aiohttp import ClientError, ClientSession

log = logging.getLogger("red.tigattack.vehicle_info.additional_vehicle_info")


@dataclass
class VehicleDetails:
    """Dataclass for vehicle details from undiscovered vehicle information API.

    Attributes:
        - VRN (str): The Vehicle Registration Number.
        - Manufacturer (str): The manufacturer of the vehicle.
        - Model (str): The model of the vehicle.
        - Colour (str): The colour of the vehicle.
        - Year (str): The date of the vehicle's first registration with the DVLA.
        - VIN (str): The Vehicle Identification Number.
    """

    VRN: str
    Manufacturer: str
    Model: str
    Colour: str
    Year: str
    VIN: str


class VehicleLookupAPI:
    def __init__(self, base_url: str, user_agent: Optional[str]):
        """
        Initialise the VehicleLookupAPI with the base URL.

        Args:
            base_url (str): The base URL of the API.
        """
        self.base_url = base_url
        self.user_agent = user_agent

    async def get_vehicle_details(self, vrn: str) -> Optional[VehicleDetails]:
        """
        Fetch vehicle details by VRN (Vehicle Registration Number).

        Args:
            vrn (str): The Vehicle Registration Number.

        Returns:
            Optional[VehicleDetails]: The vehicle details if successful, None otherwise.
        """
        headers = {"User-Agent": self.user_agent} if self.user_agent else None
        url = f"{self.base_url}/api/lookup-reg/{vrn}"

        log.debug(
            "Making request for additional vehicle info to %s%s",
            url,
            f" with user agent {self.user_agent}" if self.user_agent else "",
        )

        try:
            async with ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        try:
                            vehicle_data = await response.json()
                            return VehicleDetails(**vehicle_data)
                        except (JSONDecodeError, TypeError) as e:
                            raise ValueError(f"Invalid response format: {e}")
                    else:
                        error_message = await response.text()
                        log.error("API request failed with status %s: %s", response.status, error_message)
                        raise ValueError(f"Error from API: {response.status} - {error_message}")

        except ClientError as e:
            log.error("Network error occurred while fetching vehicle details: %s", e)
            raise ConnectionError(f"Network error: {e}")

        except Exception as e:
            log.exception("An unexpected error occurred: %s", e)
            raise RuntimeError(f"Unexpected error: {e}")
