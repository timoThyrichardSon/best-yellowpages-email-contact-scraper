thonimport logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+"
)

SOCIAL_DOMAINS = {
    "linkedin": ["linkedin.com"],
    "facebook": ["facebook.com", "fb.com"],
    "twitter": ["twitter.com", "x.com"],
    "tiktok": ["tiktok.com"],
    "pinterest": ["pinterest.com"],
    "instagram": ["instagram.com"],
}

@dataclass
class ContactScanner:
    timeout: int = 15
    headers: Optional[Dict[str, str]] = None
    proxy: Optional[str] = None
    max_pages_per_site: int = 4

    def _request(self, url: str) -> Optional[str]:
        if not url or url == "Not Found":
            return None

        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        try:
            logger.debug("Requesting website URL for scanning: %s", url)
            resp = requests.get(
                url,
                headers=self.headers,
                timeout=self.timeout,
                proxies=proxies,
            )
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            logger.warning("Failed to fetch '%s' for contact scanning: %s", url, exc)
            return None

    def _extract_emails_from_text(self, text: str) -> Set[str]:
        emails = set(match.group(0) for match in EMAIL_REGEX.finditer(text))
        logger.debug("Extracted %d email(s) from text.", len(emails))
        return emails

    def _extract_social_links_from_soup(self, soup: BeautifulSoup, base_url: str) -> Dict[str, Set[str]]:
        found: Dict[str, Set[str]] = defaultdict(set)

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("#") or not href:
                continue

            full_url = urljoin(base_url, href)
            domain = urlparse(full_url).netloc.lower()

            for platform, domains in SOCIAL_DOMAINS.items():
                if any(d in domain for d in domains):
                    found[platform].add(full_url)

        for platform in SOCIAL_DOMAINS.keys():
            logger.debug("Found %d %s link(s).", len(found.get(platform, set())), platform)
        return found

    def _discover_internal_links(self, soup: BeautifulSoup, base_url: str) -> Set[str]:
        candidates: Set[str] = set()
        keywords = ["contact", "about", "impressum", "reach-us", "support"]
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            if any(kw in href for kw in keywords):
                full_url = urljoin(base_url, a["href"])
                candidates.add(full_url)
        logger.debug("Discovered %d potential internal contact/about links.", len(candidates))
        return candidates

    def _scan_single_page(self, url: str) -> Dict[str, any]:
        html = self._request(url)
        if not html:
            return {"emails": set(), "social": defaultdict(set)}

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)

        emails = self._extract_emails_from_text(text)
        social = self._extract_social_links_from_soup(soup, url)

        return {"emails": emails, "social": social, "soup": soup}

    def scan_website(self, website_url: str) -> Dict[str, List[str]]:
        """
        Scan given website URL for email addresses and social media profile links.
        """
        if not website_url or website_url == "Not Found":
            logger.info("No website URL provided, using Not Found defaults for contact data.")
            return {
                "emails": ["Not Found"],
                "socialmedia": {platform: ["Not Found"] for platform in SOCIAL_DOMAINS.keys()},
            }

        visited: Set[str] = set()
        to_visit: List[str] = [website_url]

        all_emails: Set[str] = set()
        all_social: Dict[str, Set[str]] = defaultdict(set)

        pages_scanned = 0

        while to_visit and pages_scanned < self.max_pages_per_site:
            current_url = to_visit.pop(0)
            if current_url in visited:
                continue

            visited.add(current_url)
            logger.debug("Scanning page %s (%d/%d)", current_url, pages_scanned + 1, self.max_pages_per_site)

            result = self._scan_single_page(current_url)
            pages_scanned += 1

            all_emails.update(result["emails"])
            for platform, links in result["social"].items():
                all_social[platform].update(links)

            # Discover additional internal contact/about pages from the first page
            if pages_scanned == 1 and isinstance(result.get("soup"), Tag | BeautifulSoup):
                soup = result["soup"]
                more_links = self._discover_internal_links(soup, current_url)
                for link in more_links:
                    if link not in visited:
                        to_visit.append(link)

        if not all_emails:
            emails_out = ["Not Found"]
        else:
            emails_out = sorted(all_emails)

        social_out: Dict[str, List[str]] = {}
        for platform in SOCIAL_DOMAINS.keys():
            links = sorted(all_social.get(platform, []))
            social_out[platform] = links if links else ["Not Found"]

        logger.info(
            "Contact scan for '%s' complete. Emails=%d, social platforms=%d.",
            website_url,
            0 if emails_out == ["Not Found"] else len(emails_out),
            len([p for p, v in social_out.items() if v != ["Not Found"]]),
        )

        return {
            "emails": emails_out,
            "socialmedia": social_out,
        }