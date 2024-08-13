"""Wrapper for DVSA MOT History API"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Type, Union

import aiohttp
from msal import ConfidentialClientApplication


@dataclass
class ErrorResponse:
    status_code: int
    message: str
    errors: Optional[List[str]] = None


@dataclass
class MotDefect:
    text: Optional[str]
    type: Optional[str]
    dangerous: Optional[bool]


@dataclass
class DVSAMotTest:
    completedDate: str
    testResult: Literal["PASSED", "FAILED"]
    expiryDate: Optional[str]
    odometerValue: Optional[int]
    odometerUnit: Optional[Literal["MI", "KM", "null"]]
    odometerResultType: Literal["READ", "UNREADABLE", "NO_ODOMETER"]
    motTestNumber: Optional[int]
    dataSource: Literal["DVSA"]
    defects: List[MotDefect] = field(default_factory=list)


@dataclass
class DVANIMotTest:
    completedDate: str
    testResult: Literal["PASSED", "FAILED"]
    expiryDate: Optional[str]
    odometerValue: Optional[int]
    odometerUnit: Optional[Literal["MI", "KM", "null"]]
    odometerResultType: Literal["READ", "NO_ODOMETER"]
    motTestNumber: Optional[int]
    dataSource: Literal["DVSA"]


@dataclass
class CVSMotTest:
    completedDate: str
    testResult: Literal["PASSED", "FAILED"]
    expiryDate: Optional[str]
    odometerValue: Optional[int]
    odometerUnit: Optional[Literal["MI", "KM", "null"]]
    odometerResultType: Literal["READ", "NO_ODOMETER"]
    motTestNumber: Optional[int]
    location: Optional[str]
    dataSource: Literal["DVSA"]
    defects: List[MotDefect] = field(default_factory=list)


@dataclass
class VehicleWithMotResponse:
    registration: Optional[str]
    make: Optional[str]
    model: Optional[str]
    firstUsedDate: Optional[str]
    fuelType: Optional[str]
    primaryColour: Optional[str]
    registrationDate: Optional[str]
    manufactureDate: Optional[str]
    engineSize: Optional[str]
    hasOutstandingRecall: Literal["Yes", "No", "Unknown", "Unavailable"]
    motTests: List[Union[DVSAMotTest, DVANIMotTest, CVSMotTest]] = field(default_factory=list)


@dataclass
class NewRegVehicleResponse:
    registration: Optional[str]
    make: Optional[str]
    model: Optional[str]
    manufactureYear: Optional[str]
    fuelType: Optional[str]
    primaryColour: Optional[str]
    registrationDate: Optional[str]
    manufactureDate: Optional[str]
    motTestDueDate: Optional[str]
    hasOutstandingRecall: Literal["Yes", "No", "Unknown", "Unavailable"]


@dataclass
class FileResponse:
    filename: str
    downloadUrl: str
    fileSize: int
    fileCreatedOn: str


@dataclass
class BulkDownloadResponse:
    bulk: List[FileResponse]
    delta: List[FileResponse]


class MOTHistoryAPIClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        api_key: str,
        scope_url: str = "https://tapi.dvsa.gov.uk/.default",
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope_url = scope_url
        self.tenant_id = tenant_id
        self.api_key = api_key
        self.base_url = "https://history.mot.api.gov.uk/v1/trade"

        # Initialise the MSAL Confidential Client Application
        self.msal_app = ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
        )

        self.access_token = None

    async def _get_access_token(self) -> str:
        """Obtain an access token using MSAL."""
        # acquire_token_for_client automatically checks cache before reaching out to the IDP
        token = self.msal_app.acquire_token_for_client(scopes=[self.scope_url])

        if not token.get("access_token"):
            raise Exception("Failed to obtain access token")

        return token["access_token"]

    async def _get_auth_headers(self) -> Dict[str, str]:
        """Generate the headers required for API requests."""
        token = await self._get_access_token()
        return {"Authorization": f"Bearer {token}", "X-API-Key": self.api_key}

    async def _make_api_request(self, endpoint: str) -> Dict[str, Any] | ErrorResponse:
        """Generic method to make API requests."""
        url = f"{self.base_url}{endpoint}"
        headers = await self._get_auth_headers()

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:  # noqa: PLR2004
                    return await response.json()
                elif response.status in {400, 404, 500}:
                    response_json = await response.json()
                    return ErrorResponse(
                        status_code=response.status,
                        message=response_json.get("message", "Unknown error"),
                        errors=response_json.get("errors"),
                    )
                response.raise_for_status()
                return ErrorResponse(status_code=response.status, message="Unknown error")

    async def get_vehicle_history_by_registration(
        self, registration: str
    ) -> Union[VehicleWithMotResponse, NewRegVehicleResponse, ErrorResponse]:
        """Get MOT history for a vehicle by registration."""
        endpoint = f"/vehicles/registration/{registration}"
        response_json = await self._make_api_request(endpoint)

        if isinstance(response_json, ErrorResponse):
            return response_json

        # Try to parse motTests attribute to applicable class
        if "motTests" in response_json:
            # Parse motTests specifically
            mot_tests_data = response_json.get("motTests", [])
            parsed_mot_tests = []
            for mot_test in mot_tests_data:
                parsed_mot_tests.append(await self._try_parse_dataclass(mot_test, [DVSAMotTest, DVANIMotTest, CVSMotTest]))
            response_json["motTests"] = parsed_mot_tests

        # Try parsing the response into the possible dataclasses
        return await self._try_parse_dataclass(response_json, [VehicleWithMotResponse, NewRegVehicleResponse])

    async def get_vehicle_history_by_vin(
        self, vin: str
    ) -> Union[VehicleWithMotResponse, NewRegVehicleResponse, ErrorResponse]:
        """Get MOT history for a vehicle by VIN."""
        endpoint = f"/vehicles/vin/{vin}"
        response_json = await self._make_api_request(endpoint)

        if isinstance(response_json, ErrorResponse):
            return response_json

        # Try to parse motTests attribute to applicable class
        if "motTests" in response_json:
            # Parse motTests specifically
            await self._try_parse_mot_class(response_json)

        # Try parsing the response into the possible dataclasses
        return await self._try_parse_dataclass(response_json, [VehicleWithMotResponse, NewRegVehicleResponse])

    async def _try_parse_mot_class(self, response_json):
        mot_tests_data = response_json.get("motTests", [])
        parsed_mot_tests = []
        for mot_test in mot_tests_data:
            parsed_mot_tests.append(await self._try_parse_dataclass(mot_test, [DVSAMotTest, DVANIMotTest, CVSMotTest]))
        response_json["motTests"] = parsed_mot_tests

    async def get_bulk_download(self) -> Union[BulkDownloadResponse, ErrorResponse]:
        """Get MOT history in bulk."""
        endpoint = "/vehicles/bulk-download"
        response_json = await self._make_api_request(endpoint)

        if isinstance(response_json, ErrorResponse):
            return response_json

        bulk = []
        for file in response_json.get("bulk", []):
            bulk.append(FileResponse(**file))

        delta = []
        for file in response_json.get("delta", []):
            delta.append(FileResponse(**file))

        return BulkDownloadResponse(bulk=bulk, delta=delta)

    @staticmethod
    async def _try_parse_dataclass(data: Dict[str, Any], dataclasse_types: List[Type]) -> Any:
        """Try to parse data into one of the provided dataclasses."""
        for dataclass_type in dataclasse_types:
            try:
                return dataclass_type(**data)
            except TypeError:
                continue
        raise ValueError("Unexpected response format")
