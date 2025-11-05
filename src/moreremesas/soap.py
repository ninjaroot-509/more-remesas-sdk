from __future__ import annotations
import uuid, xml.etree.ElementTree as ET
from typing import Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .exceptions import TransportError, SoapFaultError, ServerError
from .endpoints import SOAP11, MMT_NS
from .security import sanitize_headers

NS = {"soap": SOAP11}

class SoapClient:
    def __init__(self, base_url: str, timeout: int = 30, retries: int = 3, backoff: float = 0.5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        adapter = HTTPAdapter(
            max_retries=Retry(
                total=retries,
                backoff_factor=backoff,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["POST"]),
                raise_on_status=False,
            )
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    @staticmethod
    def envelope(body_xml: str, header_xml: str = "") -> str:
        return (f'<?xml version="1.0" encoding="utf-8"?>'
                f'<soap:Envelope xmlns:soap="{SOAP11}" xmlns:mmt="{MMT_NS}">'
                f"<soap:Header>{header_xml}</soap:Header>"
                f"<soap:Body>{body_xml}</soap:Body></soap:Envelope>")

    @staticmethod
    def xml2dict(el: ET.Element) -> dict:
        out = {}
        for c in list(el):
            k = c.tag.split("}")[-1]
            out[k] = SoapClient.xml2dict(c) if list(c) else (c.text or "").strip()
        return out

    def post(self, path: str, soap_action: str, xml: str) -> ET.Element:
        url = self.base_url + path
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": soap_action,
            "Accept": "text/xml",
            "X-Request-Id": str(uuid.uuid4()),
        }
        try:
            resp = self.session.post(url, data=xml.encode("utf-8"), timeout=self.timeout, headers=headers)
        except requests.RequestException as e:
            raise TransportError(str(e)) from e

        if resp.status_code >= 400:
            raise ServerError(f"HTTP {resp.status_code} at {url} hdr={sanitize_headers(headers)}")

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            raise ServerError(f"Invalid XML: {e}")

        fault = root.find(".//soap:Fault", NS)
        if fault is not None:
            code = (fault.findtext("faultcode") or "").strip()
            msg = (fault.findtext("faultstring") or "").strip()
            raise SoapFaultError(code, msg)
        return root
