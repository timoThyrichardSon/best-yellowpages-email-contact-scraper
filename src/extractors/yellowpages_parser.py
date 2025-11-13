thonimport logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

@dataclass
class YellowPagesScraper:
    base_url: str = "https://www.yellowpages.com"
    timeout: int = 15
    headers: Optional[Dict[str, str]] = None
    proxy: Optional[str] = None
    request_delay: float = 0.0

    def _request(self, path: str, params: Dict[str, Any]) -> Optional[str]:
        url = urljoin(self.base_url, path)
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        try:
            logger.debug("Requesting URL: %s with params %s", url, params)
            resp = requests.get(
                url,
                params=params,
                headers=self.headers,
                timeout=self.timeout,
                proxies=proxies,
            )
            resp.raise_for_status()
            if self.request_delay > 0:
                time.sleep(self.request_delay)
            return resp.text
        except requests.RequestException as exc:
            logger.error("Failed to fetch '%s': %s", url, exc)
            return None

    def _parse_listing(self, card: Tag) -> Dict[str, Any]:
        def text_or_not_found(element: Optional[Tag]) -> str:
            if element is None:
                return "Not Found"
            text = element.get_text(strip=True)
            return text if text else "Not Found"

        name_el = card.select_one("a.business-name span, a.business-name")
        address_el = card.select_one("p.adr, .street-address")
        locality_el = card.select_one(".locality")
        phone_el = card.select_one("div.phones, .phones")
        website_el = card.select_one("a.track-visit-website, a.website-link, a[href^='http']")

        name = text_or_not_found(name_el)
        street = text_or_not_found(address_el)
        locality = text_or_not_found(locality_el)
        address = (
            f"{street}, {locality}" if street != "Not Found" and locality != "Not Found" else street or locality
        )
        if not address or address == "Not Found, Not Found":
            address = "Not Found"

        phone = text_or_not_found(phone_el)
        website = website_el.get("href") if website_el and website_el.get("href") else "Not Found"

        listing_url_el = card.select_one("a.business-name")
        listing_url = listing_url_el.get("href") if listing_url_el and listing_url_el.get("href") else None
        if listing_url and not listing_url.startswith("http"):
            listing_url = urljoin(self.base_url, listing_url)

        logger.debug(
            "Parsed listing: name=%s, address=%s, phone=%s, website=%s",
            name,
            address,
            phone,
            website,
        )

        return {
            "name": name,
            "address": address,
            "phone": phone,
            "website": website,
            "listing_url": listing_url or "Not Found",
        }

    def _parse_results_page(self, html: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("div.result, div.v-card")
        logger.debug("Found %d listing cards on page.", len(cards))
        results: List[Dict[str, Any]] = []

        for card in cards:
            try:
                listing = self._parse_listing(card)
                if listing["name"] != "Not Found":
                    results.append(listing)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error parsing listing card: %s", exc)

        return results

    def _has_next_page(self, html: str) -> bool:
        soup = BeautifulSoup(html, "lxml")
        next_link = soup.select_one("a.next, a.pagination-next, a[rel='next']")
        return bool(next_link)

    def search(
        self,
        keyword: str,
        location: str,
        max_results: int = 50,
        sort: str = "bestmatch",
    ) -> List[Dict[str, Any]]:
        """
        Search Yellow Pages for businesses matching the keyword and location.

        :param keyword: Search terms, e.g., "dentist".
        :param location: Location, e.g., "Los Angeles, CA".
        :param max_results: Maximum number of listings to return.
        :param sort: Sort mode, typically 'bestmatch', 'distance', 'rating', or 'name'.
        """
        results: List[Dict[str, Any]] = []
        page = 1

        while len(results) < max_results:
            params = {
                "search_terms": keyword,
                "geo_location_terms": location,
                "page": page,
                "sort": sort,
            }

            logger.info(
                "Fetching search page %d (current results: %d / %d). Params=%s",
                page,
                len(results),
                max_results,
                urlencode(params),
            )
            html = self._request("/search", params=params)
            if not html:
                logger.warning("No HTML returned for page %d. Stopping pagination.", page)
                break

            page_results = self._parse_results_page(html)
            if not page_results:
                logger.info("No results found on page %d. Stopping.", page)
                break

            results.extend(page_results)
            logger.info("Accumulated %d results after page %d.", len(results), page)

            if len(results) >= max_results:
                break

            if not self._has_next_page(html):
                logger.info("No next page link found. Stopping pagination.")
                break

            page += 1

        # Trim to max_results
        trimmed_results = results[:max_results]
        logger.info("Search complete. Returning %d results.", len(trimmed_results))
        return trimmed_results