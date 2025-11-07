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
    "ORDER_CALC2":   ("Ws_Api_OrderCalc2.Execute",      "Request"),
    "ORDER_CANCEL":  ("Ws_Api_OrderCancel2.Execute",    "Request"),
    "ORDER_UPDATE":  ("Ws_Api_OrderUpdate2.Execute",    "Request"),
}

REQUIRED_ORDER_INFO2 = [
    "OrderDate","SourceCountry","SourceBranchID","OrderCurrency","OrderAmount",
    "PayoutBranchID","Customer","Beneficiary"
]

_FORCE_LIST_BY_PARENT = {
    "Branches":   {"Branch", "BranchItem"},
    "Options":    {"Option"},
    "Rates":      {"Rate"},
    "Currencies": {"Currency"},
    "Taxes":      {"Tax"},
    "Messages":   {"Message"},
}

def _escape(val: str) -> str:
    return (
        str(val)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

class MoreRemesas:
    """
    - Auth token envoyé dans AuthHeader.
    - AccessKey injecté dans <Request>.
    - Parser parent-aware pour listes.
    - order_import: wrappe l’ordre sous <OrderInfo> et sérialise récursivement.
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

    # ---------------- XML helpers ----------------
    @staticmethod
    def _xml2dict_el(el, parent_key: str | None = None):
        children = list(el)
        if not children:
            return (el.text or "").strip()

        bucket: Dict[str, Any] = {}
        this_key = el.tag.split("}")[-1]

        for c in children:
            k = c.tag.split("}")[-1]
            v = MoreRemesas._xml2dict_el(c, parent_key=this_key)

            if k in bucket:
                if not isinstance(bucket[k], list):
                    bucket[k] = [bucket[k]]
                bucket[k].append(v)
            else:
                bucket[k] = v

        force_children = _FORCE_LIST_BY_PARENT.get(this_key, set())
        if force_children:
            for child_name in force_children:
                if child_name in bucket and not isinstance(bucket[child_name], list):
                    val = bucket[child_name]
                    bucket[child_name] = [] if val in (None, "", {}) else [val]

        return bucket

    @staticmethod
    def _coerce_lists(obj):
        if isinstance(obj, list):
            return [MoreRemesas._coerce_lists(x) for x in obj]
        if isinstance(obj, dict):
            return {k: MoreRemesas._coerce_lists(v) for k, v in obj.items()}
        return obj

    # récursif: dict/list -> XML <mmt:Key>...</mmt:Key>
    @staticmethod
    def _to_xml_fields(obj: Any, key: Optional[str] = None) -> str:
        ns = "mmt"
        if obj is None:
            return f"<{ns}:{key}></{ns}:{key}>" if key else ""
        if isinstance(obj, (str, int, float)):
            val = _escape(f"{obj}")
            return f"<{ns}:{key}>{val}</{ns}:{key}>" if key else val
        if isinstance(obj, dict):
            if key:
                inner = "".join(MoreRemesas._to_xml_fields(v, k) for k, v in obj.items())
                return f"<{ns}:{key}>{inner}</{ns}:{key}>"
            return "".join(MoreRemesas._to_xml_fields(v, k) for k, v in obj.items())
        if isinstance(obj, list):
            # liste => répéter la même clé; si pas de clé parent, on ne peut pas deviner
            # ici on attend des listes seulement pour conteneurs connus (Rates/Options/etc.)
            return "".join(MoreRemesas._to_xml_fields(v, key) for v in obj)
        # fallback texte
        val = _escape(str(obj))
        return f"<{ns}:{key}>{val}</{ns}:{key}>" if key else val

    # ---------------- Auth ----------------
    def _auth_header_xml(self) -> str:
        return (
            f"<mmt:AuthHeader><mmt:AccessToken>{self.token}</mmt:AccessToken></mmt:AuthHeader>"
            if self.token else ""
        )

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
            f"<mmt:LoginUser>{_escape(self.login_user)}</mmt:LoginUser>"
            f"<mmt:LoginPass>{_escape(self.login_pass)}</mmt:LoginPass>"
            f"</mmt:{req_wrapper}>"
            f"</mmt:{op_name}>"
        )
        xml    = self._envelope(body, "")
        action = "MMTaction/" + op_name
        root   = self.soap.post(PATHS["AUTH"], action, xml)
        payload = root.find(".//{MMT}Response")
        if payload is None:
            raise AuthError("Auth: <Response> not found.")
        data_raw = MoreRemesas._xml2dict_el(payload, parent_key=None)
        data = data_raw if isinstance(data_raw, dict) else {"_text": data_raw}
        data = MoreRemesas._coerce_lists(data)
        if data.get("ResponseCode") != "1000":
            raise AuthError(f"Auth failed: {data}")
        self.token = data.get("AccessToken") or ""
        try:
            self.token_due = dt.datetime.fromisoformat(data.get("DueDate", ""))
        except Exception:
            self.token_due = None

    # ---------------- SOAP envelope ----------------
    @staticmethod
    def _envelope(body_xml: str, header_xml: str = "") -> str:
        return (
            f'<?xml version="1.0" encoding="utf-8"?>'
            f'<soap:Envelope xmlns:soap="{SOAP11}" xmlns:mmt="{MMT_NS}">'
            f"<soap:Header>{header_xml}</soap:Header>"
            f"<soap:Body>{body_xml}</soap:Body></soap:Envelope>"
        )

    # ---------------- Core caller ----------------
    def _call(self, path_key: str, op_key: str, params: Dict[str, Any] | None = None) -> dict:
        if op_key != "AUTH":
            self._ensure_token()

        op_name, req_wrapper = OP_MAP[op_key]
        merged = dict(params or {})

        # AccessKey prioritaire: param > self.access_key > token
        if "AccessKey" not in merged:
            merged["AccessKey"] = self.access_key or self.token or ""

        # sérialisation récursive
        fields_xml = self._to_xml_fields(merged)  # <mmt:Key>...</mmt:Key> récursifs

        body = f"<mmt:{op_name}><mmt:{req_wrapper}>{fields_xml}</mmt:{req_wrapper}></mmt:{op_name}>"
        header = self._auth_header_xml()
        xml    = self._envelope(body, header)

        # print("XML Request:", xml)  # debug
        action = "MMTaction/" + op_name

        root = self.soap.post(PATHS[path_key], action, xml)
        resp = root.find(".//{MMT}Response") or root.find(".//*[contains(local-name(), 'Response')]")
        if resp is None:
            raise ValidationError("Response not found.")

        raw = MoreRemesas._xml2dict_el(resp, parent_key=None)
        data = raw if isinstance(raw, dict) else {"_text": raw}
        return MoreRemesas._coerce_lists(data)

    # ---------------- Public endpoints ----------------
    def rates(self, **fields) -> dict:                return self._call("RATES", "RATES", fields)
    def branches(self, **fields) -> dict:             return self._call("BRANCHES", "BRANCHES", fields)
    def orders_status(self, **fields) -> dict:        return self._call("ORDERS_STATUS", "ORDERS_STATUS", fields)

    def order_import(self, **order) -> dict:
        # Validation côté SDK sur le payload minima
        self._validate_order_min(order)
        # La doc impose <OrderInfo>…</OrderInfo> à l’intérieur de <Request>
        wrapped = {"OrderInfo": order}
        return self._call("ORDER_IMPORT", "ORDER_IMPORT", wrapped)

    def order_calc(self, **fields) -> dict:           return self._call("ORDER_CALC", "ORDER_CALC", fields)
    def order_calc2(self, **fields) -> dict:          return self._call("ORDER_CALC2", "ORDER_CALC2", fields)
    def order_cancel(self, **fields) -> dict:         return self._call("ORDER_CANCEL", "ORDER_CANCEL", fields)
    def order_update(self, **fields) -> dict:         return self._call("ORDER_UPDATE", "ORDER_UPDATE", fields)

    # ---------------- Helpers ----------------
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
    def order_info_min(
        *,
        OrderDate: str,
        SourceCountry: str,
        SourceBranchID: str,
        OrderCurrency: str,
        OrderAmount: str | float,
        PayoutBranchID: str,
        Customer: dict,
        Beneficiary: dict,
        **opt
    ) -> dict:
        base = {
            "OrderDate": OrderDate,
            "SourceCountry": SourceCountry,
            "SourceBranchID": SourceBranchID,
            "OrderCurrency": str(OrderCurrency).upper(),
            "OrderAmount": f"{float(OrderAmount):.2f}",
            "PayoutBranchID": str(PayoutBranchID),
            "Customer": Customer,
            "Beneficiary": Beneficiary,
        }
        base.update(opt)
        return base
