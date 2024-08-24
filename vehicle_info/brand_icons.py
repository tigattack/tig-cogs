import logging
from io import BytesIO
from typing import Literal, Optional

import aiohttp
from PIL import Image

log = logging.getLogger("red.tigattack.vehicle_info.brand_icons")


async def _get_brand_domain(brand: str) -> str:
    """Get brand info from a brand name"""
    url = f"https://api.brandfetch.io/v2/search/{brand}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:  # noqa: PLR2004
                raise ValueError("Failed to fetch the brand domain.")
            response_json = await response.json()
    return response_json[0]["domain"]


async def get_brand_icon(
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
    try:
        brand_domain = await _get_brand_domain(brand_domain)
    except ValueError:
        log.error("Failed to fetch domain for brand '%s'.", brand_domain)
        return None

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
