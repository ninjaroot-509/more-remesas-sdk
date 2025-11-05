from __future__ import annotations
import datetime as dt
from typing import Any, Dict, Optional

from .endpoints import PATHS, SOAP11, MMT_NS
from .soap import SoapClient
from .exceptions import AuthError, ValidationError

OP_MAP = {
    "AUTH":          ("AWS_API_AUTH2.Execute",          "Logintype"),
    "RATES":         ("Ws_Api_Rates2.Execute",          "Request"),
    "BRANCHES":      ("Ws_Api_BranchesList2.Execute",   "Request"),
    "ORDERS_STATUS": ("Ws_Api_OrdersStatus2.Execute",   "Request"),
    "ORDER_IMPORT":  ("Ws_Api_OrderImport2.Execute",    "Request"),
    "ORDER_CALC":    ("Ws_Api_OrderCalc2.Execute",      "Request"),
    "ORDER_CANCEL":  ("Ws_Api_OrderCancel2.Execute",    "Request"),
    "ORDER_UPDATE":  ("Ws_Api_OrderUpdate2.Execute",    "Request"),
}

REQUIRED_ORDER_INFO2 = [
    "OrderDate","SourceCountry","SourceBranchID","OrderCurrency","OrderAmount","PayoutBranchID","Customer","Beneficiary"
]

class MoreRemesas:
    """
    sandbox=True/False: les deux font AUTH.
    - Envoi toujours AuthHeader si token.
    - Injecte AccessKey dans <Request> (priorité: params.AccessKey > token).
    """
    def __init__(
        self,
        host: str,
        login_user: Optional[str] = None,
        login_pass: Optional[str] = None,
        *,
        sandbox: bool = True,
        access_key: Optional[str] = None,
        timeout: int = 30,
        retries: int = 3,
        auto_auth: bool = True,
    ):
        self.host = host.rstrip("/")
        self.login_user = (login_user or "").strip()
        self.login_pass = (login_pass or "").strip()
        self.sandbox = sandbox
        self.access_key = access_key
        self.auto_auth = auto_auth

        self.soap = SoapClient(self.host, timeout=timeout, retries=retries)
        self.token: Optional[str] = None
        self.token_due: Optional[dt.datetime] = None

        if self.auto_auth and (self.login_user and self.login_pass):
            self._authenticate()

    @staticmethod
    def _xml2dict(el) -> dict:
        out = {}
        for c in list(el):
            k = c.tag.split("}")[-1]
            out[k] = MoreRemesas._xml2dict(c) if list(c) else (c.text or "").strip()
        return out

    def _auth_header_xml(self) -> str:
        return f"<mmt:AuthHeader><mmt:AccessToken>{self.token}</mmt:AccessToken></mmt:AuthHeader>" if self.token else ""

    def _ensure_token(self):
        if not self.auto_auth:
            return
        if not self.token or (self.token_due and dt.datetime.utcnow() >= self.token_due):
            if not (self.login_user and self.login_pass):
                raise AuthError("Missing login_user/login_pass for auto_auth")
            self._authenticate()

    def _authenticate(self) -> None:
        op_name, req_wrapper = OP_MAP["AUTH"]
        body = (
            f"<mmt:{op_name}>"
            f"<mmt:{req_wrapper}>"
            f"<mmt:LoginUser>{self.login_user}</mmt:LoginUser>"
            f"<mmt:LoginPass>{self.login_pass}</mmt:LoginPass>"
            f"</mmt:{req_wrapper}>"
            f"</mmt:{op_name}>"
        )
        xml    = self._envelope(body, "")
        action = "MMTaction/" + op_name
        root   = self.soap.post(PATHS["AUTH"], action, xml)
        payload = root.find(".//{MMT}Response")
        if payload is None:
            raise AuthError("Auth: <Response> not found.")
        data = self._xml2dict(payload)
        if data.get("ResponseCode") != "1000":
            raise AuthError(f"Auth failed: {data}")
        self.token = data.get("AccessToken") or ""
        try:
            self.token_due = dt.datetime.fromisoformat(data.get("DueDate", ""))
        except Exception:
            self.token_due = None

    @staticmethod
    def _envelope(body_xml: str, header_xml: str = "") -> str:
        return (f'<?xml version="1.0" encoding="utf-8"?>'
                f'<soap:Envelope xmlns:soap="{SOAP11}" xmlns:mmt="{MMT_NS}">'
                f"<soap:Header>{header_xml}</soap:Header>"
                f"<soap:Body>{body_xml}</soap:Body></soap:Envelope>")

    def _call(self, path_key: str, op_key: str, params: Dict[str, Any] | None = None) -> dict:
        if op_key != "AUTH":
            self._ensure_token()

        op_name, req_wrapper = OP_MAP[op_key]
        merged = dict(params or {})

        if "AccessKey" not in merged:
            if self.access_key:
                merged["AccessKey"] = self.access_key
            elif self.token:
                merged["AccessKey"] = self.token

        fields = "".join(f"<mmt:{k}>{v}</mmt:{k}>" for k, v in merged.items())
        body = f"<mmt:{op_name}><mmt:{req_wrapper}>{fields}</mmt:{req_wrapper}></mmt:{op_name}>"

        header = self._auth_header_xml()
        xml    = self._envelope(body, header)
        action = "MMTaction/" + op_name

        root = self.soap.post(PATHS[path_key], action, xml)
        resp = root.find(".//{MMT}Response") or root.find(".//*[contains(local-name(), 'Response')]")
        if resp is None:
            raise ValidationError("Response not found.")
        return self._xml2dict(resp)

    def rates(self, **fields) -> dict:         return self._call("RATES", "RATES", fields)
    def branches(self, **fields) -> dict:      return self._call("BRANCHES", "BRANCHES", fields)
    def orders_status(self, **fields) -> dict: return self._call("ORDERS_STATUS", "ORDERS_STATUS", fields)
    def order_import(self, **order) -> dict:
        self._validate_order_min(order)
        return self._call("ORDER_IMPORT", "ORDER_IMPORT", order)
    def order_calc(self, **fields) -> dict:    return self._call("ORDER_CALC", "ORDER_CALC", fields)
    def order_cancel(self, **fields) -> dict:  return self._call("ORDER_CANCEL", "ORDER_CANCEL", fields)
    def order_update(self, **fields) -> dict:  return self._call("ORDER_UPDATE", "ORDER_UPDATE", fields)

    def _validate_order_min(self, order: Dict[str, Any]) -> None:
        missing = [k for k in REQUIRED_ORDER_INFO2 if k not in order]
        if missing:
            raise ValidationError(f"OrderInfoType2 missing fields: {missing}")

    @staticmethod
    def person_min(FirstName: str, LastName: str, **opt) -> dict:
        d = {"FirstName": FirstName, "LastName": LastName}
        d.update(opt)
        return d

    @staticmethod
    def order_info_min(*, OrderDate: str, SourceCountry: str, SourceBranchID: str,
                       OrderCurrency: str, OrderAmount: str | float,
                       PayoutBranchID: str, Customer: dict, Beneficiary: dict, **opt) -> dict:
        base = {
            "OrderDate": OrderDate,
            "SourceCountry": SourceCountry,
            "SourceBranchID": SourceBranchID,
            "OrderCurrency": OrderCurrency,
            "OrderAmount": f"{float(OrderAmount):.2f}",
            "PayoutBranchID": PayoutBranchID,
            "Customer": Customer,
            "Beneficiary": Beneficiary,
        }
        base.update(opt)
        return base
