"""
Submit URLs to Google Indexing API and Bing URL Submission API.
"""
import logging
from typing import Optional

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

# Site URL for indexing - uses Wagtail base URL setting
SITE_URL = getattr(settings, 'WAGTAILADMIN_BASE_URL', 'https://example.com')


def request_indexing(url_path: str) -> dict:
    """
    Request indexing for a URL from Google and Bing.

    Args:
        url_path: Relative URL path (e.g., "/ai-agents-news/")

    Returns:
        Dict with success status for each search engine
    """
    full_url = f"{SITE_URL}{url_path}"
    results = {
        "url": full_url,
        "google": False,
        "bing": False,
    }

    results["google"] = submit_to_google(full_url)
    results["bing"] = submit_to_bing(full_url)

    logger.info(f"Indexing request for {full_url}: Google={results['google']}, Bing={results['bing']}")
    return results


def submit_to_google(url: str) -> bool:
    """
    Submit URL to Google Indexing API.

    Requires GOOGLE_INDEXING_CREDENTIALS env var pointing to service account JSON.
    """
    credentials_path = getattr(settings, "GOOGLE_INDEXING_CREDENTIALS", None)
    if not credentials_path:
        logger.warning("GOOGLE_INDEXING_CREDENTIALS not configured, skipping Google indexing")
        return False

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/indexing"],
        )

        service = build("indexing", "v3", credentials=credentials)

        body = {
            "url": url,
            "type": "URL_UPDATED",  # Use URL_DELETED for removal
        }

        response = service.urlNotifications().publish(body=body).execute()
        logger.debug(f"Google indexing response: {response}")
        return True

    except Exception as e:
        logger.error(f"Google indexing failed for {url}: {e}")
        return False


def submit_to_bing(url: str) -> bool:
    """
    Submit URL to Bing URL Submission API.

    Requires BING_WEBMASTER_API_KEY env var.
    Docs: https://www.bing.com/webmasters/help/url-submission-api-0f61686e
    """
    api_key = getattr(settings, "BING_WEBMASTER_API_KEY", None)
    if not api_key:
        logger.warning("BING_WEBMASTER_API_KEY not configured, skipping Bing indexing")
        return False

    try:
        endpoint = "https://ssl.bing.com/webmaster/api.svc/json/SubmitUrl"

        params = {"apikey": api_key}
        payload = {
            "siteUrl": SITE_URL,
            "url": url,
        }

        response = httpx.post(endpoint, params=params, json=payload, timeout=30)

        if response.status_code == 200:
            logger.debug(f"Bing indexing response: {response.text}")
            return True
        else:
            logger.error(f"Bing indexing failed: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Bing indexing failed for {url}: {e}")
        return False
