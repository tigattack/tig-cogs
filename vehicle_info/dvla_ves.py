"""Wrapper for DVLA Vehicle Enquiry Service API"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

import aiohttp

BASE_URLS = {
    "production": "https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry",
    "test": "https://uat.driver-vehicle-licensing.api.gov.uk/vehicle-enquiry",
}


@dataclass
class VehicleRequest:
    registrationNumber: str


@dataclass
class Errors:
    status: str
    code: str
    title: str
    detail: Optional[str] = None


@dataclass
class ErrorResponse:
    errors: List[Errors] = field(default_factory=list)


@dataclass
class Vehicle:
    """
    Represents a vehicle's details as retrieved from the DVLA Vehicle Enquiry Service API.

    Attributes:
        - registrationNumber (str): The registration number of the vehicle (required).
        - taxStatus (str, optional): The tax status of the vehicle. Possible values include:
            - 'Not Taxed for on Road Use'
            - 'SORN'
            - 'Taxed'
            - 'Untaxed'
        - taxDueDate (str, optional): Date of tax liability, used in calculating licence information presented to the user.
        - artEndDate (str, optional): Additional Rate of Tax End Date, format: YYYY-MM-DD.
        - motStatus (str, optional): The MOT status of the vehicle. Possible values include:
            - 'No details held by DVLA'
            - 'No results returned'
            - 'Not valid'
            - 'Valid'
        - motExpiryDate (str, optional): The expiry date of the MOT.
        - make (str, optional): The make of the vehicle.
        - monthOfFirstDvlaRegistration (str, optional): Month of the first DVLA registration.
        - monthOfFirstRegistration (str, optional): Month of the first registration.
        - yearOfManufacture (int, optional): Year of manufacture of the vehicle.
        - engineCapacity (int, optional): Engine capacity in cubic centimetres.
        - co2Emissions (int, optional): Carbon Dioxide emissions in grams per kilometre.
        - fuelType (str, optional): The fuel type (method of propulsion) of the vehicle.
        - markedForExport (bool, optional): True if the vehicle has been export marked.
        - colour (str, optional): The colour of the vehicle.
        - typeApproval (str, optional): Vehicle Type Approval Category.
        - wheelplan (str, optional): Vehicle wheel plan.
        - revenueWeight (int, optional): Revenue weight in kilograms.
        - realDrivingEmissions (str, optional): Real Driving Emissions value.
        - dateOfLastV5CIssued (str, optional): Date of the last V5C issued.
        - euroStatus (str, optional): Euro Status (Dealer / Customer Provided for new vehicles).
        - automatedVehicle (bool, optional): True if the vehicle is an Automated Vehicle (AV).
    """

    registrationNumber: str
    taxStatus: Optional[Literal["Not Taxed for on Road Use", "SORN", "Taxed", "Untaxed"]] = None
    taxDueDate: Optional[str] = None
    artEndDate: Optional[str] = None
    motStatus: Optional[Literal["No details held by DVLA", "No results returned", "Not valid", "Valid"]] = None
    motExpiryDate: Optional[str] = None
    make: Optional[str] = None
    monthOfFirstDvlaRegistration: Optional[str] = None
    monthOfFirstRegistration: Optional[str] = None
    yearOfManufacture: Optional[int] = None
    engineCapacity: Optional[int] = None
    co2Emissions: Optional[int] = None
    fuelType: Optional[str] = None
    markedForExport: Optional[bool] = None
    colour: Optional[str] = None
    typeApproval: Optional[str] = None
    wheelplan: Optional[str] = None
    revenueWeight: Optional[int] = None
    realDrivingEmissions: Optional[str] = None
    dateOfLastV5CIssued: Optional[str] = None
    euroStatus: Optional[str] = None
    automatedVehicle: Optional[bool] = None


class VehicleEnquiryAPI:
    def __init__(self, api_key: str, environment: str = "production"):
        if environment not in BASE_URLS:
            raise ValueError("Invalid environment. Choose 'production' or 'test'.")
        self.api_key = api_key
        self.base_url = BASE_URLS[environment]

    async def _make_request(self, endpoint: str, data: Dict[str, Any], correlation_id: Optional[str]) -> Dict[str, Any]:
        headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}
        if correlation_id:
            headers["X-Correlation-Id"] = correlation_id

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}{endpoint}", json=data, headers=headers) as response:
                response_json = await response.json()
                return {"status_code": response.status, "body": response_json}

    async def get_vehicle(self, registration_number: str, correlation_id: Optional[str] = None) -> Vehicle:
        """Get vehicle info from DVLA Vehicle Enquiry Service API"""
        data = asdict(VehicleRequest(registrationNumber=registration_number))
        response = await self._make_request("/v1/vehicles", data, correlation_id)

        if response["status_code"] == 200:  # noqa: PLR2004
            try:
                vehicle_data = response["body"]
                return Vehicle(**vehicle_data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid response format: {e}")
        else:
            try:
                error_data = json.loads(response["body"])
                error_response = ErrorResponse(errors=[Errors(**error) for error in error_data.get("errors", [])])
                raise ValueError(f"Error from API: {error_response.errors}")
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid error format: {e}")
