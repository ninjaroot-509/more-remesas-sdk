from __future__ import annotations
import datetime as dt
from typing import Any, Dict, Optional

from .endpoints import PATHS_SANDBOX, PATHS_PROD, SOAP11, MMT_NS
from .soap import SoapClient
from .exceptions import AuthError, ValidationError

# ------------------------------ Operation map ------------------------------
OP_MAP = {
    "AUTH":           ("AWS_API_AUTH2.Execute",           "Logintype"),
    "BRANCHES":       ("Ws_Api_BranchesList2.Execute",    "Request"),
    "RATES":          ("Ws_Api_Rates2.Execute",            "Request"),
    "RESERVE_KEY":    ("aWS_Api_ReserveKey2.Execute",      "Request"),
    "ORDER_IMPORT":   ("Ws_Api_OrderImport2.Execute",      "Request"),
    "ORDERS_STATUS":  ("Ws_Api_OrdersStatus2.Execute",     "Request"),
    "ORDER_ACTIVATE": ("Ws_Api_OrderActivate2.Execute",    "Request"),
    "ORDER_CANCEL":   ("Ws_Api_OrderCancel2.Execute",      "Request"),
    "ORDER_UPDATE":   ("Ws_Api_OrderUpdate2.Execute",      "Request"),
    "ORDER_REFUND":   ("Ws_Api_OrderRefund2.Execute",      "Request"),
    "ORDER_VOUCHER":  ("Ws_Api_OrderVoucher2.Execute",     "Request"),
    "ORDER_CALC":     ("Ws_Api_OrderCalc2.Execute",        "Request"),
    "ORDER_VALIDATE": ("Ws_Api_OrderValidate2.Execute",    "Request"),
}

REQUIRED_ORDER_INFO2 = [
    "OrderDate", "SourceCountry", "SourceBranchID",
    "OrderCurrency", "OrderAmount",
    "PayoutBranchID", "Customer", "Beneficiary",
]

_FORCE_LIST_BY_PARENT = {
    "Branches":   {"Branch", "BranchItem"},
    "Options":    {"Option"},
    "Rates":      {"Rate"},
    "Currencies": {"Currency"},
    "Taxes":      {"Tax"},
    "Messages":   {"Message"},
    "Orders":     {"Order"},
}

RESPONSE_CODES: dict[str, str] = {
    "1000": "The transaction was successfully completed.",
    "2": "Authorization to not control exchange rate",
    "3": "Order with incidence",
    "4": "Cancellation of Orders",
    "5": "Cancellation Request",
    "6": "Modification Request",
    "9": "Freed by Legal Compliance",
    "13": "With Incidence, contact Finances",
    "18": "In revision by Legal Compliance",
    "19": "Comment from Requests Panel",
    "20": "Order Activated",
    "21": "Order registered in the system",
    "22": "With Incidence, contact Finances",
    "30": "Payment rejected for incorrect data",
    "31": "Documentation required by Compliance",
    "33": "Recommend Payment",
    "34": "Claim",
    "102": "Origin Agent Inactive",
    "103": "Invalid Exchange Rate",
    "126": "Validation - Duplication Suspect",
    "129": "Source Country error",
    "131": "Payment branch is inactive",
    "133": "Payment branch non-existent",
    "134": "Sender’s name isn’t specified",
    "135": "Sender’s last name isn’t specified",
    "136": "Receiver’s name isn’t specified",
    "137": "Receiver’s last name isn’t specified",
    "138": "Invalid amount of origin/destination",
    "139": "Incoherence in origin/destination currencies and amount",
    "142": "Payer Agent is inactive",
    "144": "Branch City Null",
    "148": "Sender's telephone isn’t specified",
    "149": "Beneficiary’s telephone or address isn’t specified",
    "150": "Sender’s ID isn’t specified",
    "151": "Receiver's ID isn't specified or the beneficiary's name doesn’t match with the registered document",
    "152": "Sender's address isn’t specified",
    "153": "Beneficiary's address isn’t specified",
    "154": "Sender's City isn’t specified",
    "155": "Beneficiary's City isn’t specified",
    "156": "Bank account isn’t specified",
    "157": "Payout branch doesn’t pay the amount sent",
    "158": "The currency is not enabled in the payment branch",
    "160": "Provider’s ID isn't specified or it is repeated",
    "161": "Invalid CPF",
    "162": "Null Bank Agency",
    "165": "Order without reference validation",
    "166": "There is no bank associated with the account",
    "167": "Incorrect IBAN code",
    "172": "Incorrect CBU",
    "173": "Sender’s birth date isn't specified",
    "174": "Beneficiary’s birth date isn't specified",
    "176": "A valid purpose must be specified",
    "177": "A valid relationship must be specified",
    "178": "Invalid payment method",
    "1261": "Do not control order maybe duplicated",
    "8050": "Order sent to the Payer",
    "9000": "Generic Webservice Error",
    "9001": "Authentication Error",
    "9002": "The order already exists",
    "9003": "The specified order wasn’t found",
    "9004": "The user does not have permission to execute the program or it is not enabled",
    "9005": "Time expired for activating the order",
    "9006": "AccessToken invalid",
    "9007": "The reserve data doesn't match",
    "9008": "Invalid Reserve",
    "9009": "Destination requires key reserve",
    "9010": "Request Canceled",
    "9011": "Manual Request - Waiting confirmation",
    "9014": "Requests - There are pending requests for the order",
    "9016": "Request - Order Status doesn't match",
    "9017": "Request - You are not authorized to perform the required action",
    "9019": "Invalid agent for the specified order",
    "9020": "Date range is above 30 days",
    "9039": "Order status doesn’t allow to cancel",
    "9046": "Invalid branch contract",
    "9047": "The selected branch doesn’t belong to the payout agent",
    "9048": "Agent doesn't reserve key",
    "9049": "No images of the document loaded",
    "9050": "The image sent is invalid",
    "9051": "Agent didn’t return reserve key",
    "9102": "The required order is PAYED",
    "9105": "Order Payment",
    "9106": "Reverse order payment",
    "9107": "Reverse cancellation",
    "9108": "Inconsistent reversion",
    "9111": "The order has no pending activation (OrderActivate)",
    "9112": "Order out of time of activation (OrderActivate)",
    "9113": "The agent is not set to activate orders (OrderActivate)",
    "9115": "Generic Error in order payment",
    "9118": "Incorrect Method (P/A)",
    "9119": "The method (P/A) does not correspond with the order status",
    "9120": "The method (P/A) does not correspond with agent",
    "9121": "Incorrect status of the order to make the request",
    "9999": "Non-controlled exception",
}

def _esc(val: str) -> str:
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
    SOAP client for More Money Transfers V2 services.

    Features:
    - Auto-auth with token caching (sent in AuthHeader + AccessKey in body).
    - Resilient XML→dict parser with parent-aware list coercion.
    - OrderImport wraps order body inside <OrderInfo> and supports ReserveKey.
    - All public endpoints in the V2 spec are exposed.
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

        self.paths = PATHS_PROD if not sandbox else PATHS_SANDBOX

        if self.auto_auth and self.login_user and self.login_pass:
            self._authenticate()

    # ------------------------------- XML helpers -------------------------------
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

        force = _FORCE_LIST_BY_PARENT.get(this_key, set())
        for child_name in force:
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

    @staticmethod
    def _to_xml_fields(obj: Any, key: Optional[str] = None) -> str:
        ns = "mmt"
        if obj is None:
            return f"<{ns}:{key}></{ns}:{key}>" if key else ""
        if isinstance(obj, (str, int, float)):
            val = _esc(f"{obj}")
            return f"<{ns}:{key}>{val}</{ns}:{key}>" if key else val
        if isinstance(obj, dict):
            inner = "".join(MoreRemesas._to_xml_fields(v, k) for k, v in obj.items())
            return f"<{ns}:{key}>{inner}</{ns}:{key}>" if key else inner
        if isinstance(obj, list):
            return "".join(MoreRemesas._to_xml_fields(v, key) for v in obj)
        val = _esc(str(obj))
        return f"<{ns}:{key}>{val}</{ns}:{key}>" if key else val

    # ------------------------------- Auth helpers -------------------------------
    def _auth_header_xml(self) -> str:
        return (
            f"<mmt:AuthHeader><mmt:AccessToken>{self.token}</mmt:AccessToken></mmt:AuthHeader>"
            if self.token else ""
        )

    def _ensure_token(self):
        if not self.auto_auth:
            return
        refresh = not self.token or (self.token_due and dt.datetime.utcnow() >= self.token_due)
        if refresh:
            if not (self.login_user and self.login_pass):
                raise AuthError("Missing login_user/login_pass for auto_auth")
            self._authenticate()

    def _authenticate(self) -> None:
        op_name, req_wrapper = OP_MAP["AUTH"]
        body = (
            f"<mmt:{op_name}>"
            f"<mmt:{req_wrapper}>"
            f"<mmt:LoginUser>{_esc(self.login_user)}</mmt:LoginUser>"
            f"<mmt:LoginPass>{_esc(self.login_pass)}</mmt:LoginPass>"
            f"</mmt:{req_wrapper}>"
            f"</mmt:{op_name}>"
        )
        xml    = self._envelope(body, "")
        action = "MMTaction/" + op_name
        root   = self.soap.post(self.paths["AUTH"], action, xml)

        resp = root.find(".//{MMT}Response") or root.find(".//*[contains(local-name(), 'Response')]")
        if resp is None:
            raise AuthError("Auth: <Response> not found")

        data_raw = MoreRemesas._xml2dict_el(resp)
        data     = data_raw if isinstance(data_raw, dict) else {"_text": data_raw}
        data     = MoreRemesas._coerce_lists(data)

        if data.get("ResponseCode") != "1000":
            raise AuthError(f"Auth failed: {data}")
        self.token = data.get("AccessToken") or ""
        try:
            self.token_due = dt.datetime.fromisoformat(data.get("DueDate", ""))
        except Exception:
            self.token_due = None

    # ------------------------------ SOAP envelope ------------------------------
    @staticmethod
    def _envelope(body_xml: str, header_xml: str = "") -> str:
        return (
            f'<?xml version="1.0" encoding="utf-8"?>'
            f'<soap:Envelope xmlns:soap="{SOAP11}" xmlns:mmt="{MMT_NS}">'
            f"<soap:Header>{header_xml}</soap:Header>"
            f"<soap:Body>{body_xml}</soap:Body>"
            f"</soap:Envelope>"
        )

    # -------------------------------- Core caller --------------------------------
    def _call(self, path_key: str, op_key: str, params: Dict[str, Any] | None = None) -> dict:
        if op_key != "AUTH":
            self._ensure_token()

        op_name, req_wrapper = OP_MAP[op_key]
        merged = dict(params or {})

        if "AccessKey" not in merged:
            merged["AccessKey"] = self.access_key or self.token or ""

        fields_xml = self._to_xml_fields(merged)
        body = f"<mmt:{op_name}><mmt:{req_wrapper}>{fields_xml}</mmt:{req_wrapper}></mmt:{op_name}>"
        header = self._auth_header_xml()
        xml    = self._envelope(body, header)
        action = "MMTaction/" + op_name

        root = self.soap.post(self.paths[path_key], action, xml)
        resp = root.find(".//{MMT}Response") or root.find(".//*[contains(local-name(), 'Response')]")
        if resp is None:
            raise ValidationError("Response not found")

        raw  = MoreRemesas._xml2dict_el(resp)
        data = raw if isinstance(raw, dict) else {"_text": raw}
        return MoreRemesas._coerce_lists(data)

    # ------------------------------- Public APIs -------------------------------
    def branches(self, **fields) -> dict:
        """aWs_Api_BranchesList2.aspx"""
        return self._call("BRANCHES", "BRANCHES", fields)

    def rates(self, **fields) -> dict:
        """aWs_Api_Rates2.aspx"""
        return self._call("RATES", "RATES", fields)

    def order_calc(self, **fields) -> dict:
        """aWs_Api_OrderCalc2.aspx"""
        return self._call("ORDER_CALC", "ORDER_CALC", fields)

    def reserve_key(self, *, OrderInfo: dict, **extra) -> dict:
        """aWS_Api_ReserveKey2.aspx"""
        self._validate_order_min(OrderInfo)
        payload = {"OrderInfo": OrderInfo}
        payload.update(extra)
        return self._call("RESERVE_KEY", "RESERVE_KEY", payload)

    def order_import(self, *, ReserveKey: Optional[str] = None, **order) -> dict:
        """aWs_Api_OrderImport2.aspx"""
        self._validate_order_min(order)
        wrapped = {"OrderInfo": order}
        if ReserveKey:
            wrapped = {"ReserveKey": ReserveKey, **wrapped}
        return self._call("ORDER_IMPORT", "ORDER_IMPORT", wrapped)

    def orders_status(self, **fields) -> dict:
        """aWs_Api_OrdersStatus2.aspx"""
        return self._call("ORDERS_STATUS", "ORDERS_STATUS", fields)

    def order_activate(self, **fields) -> dict:
        """aWs_Api_OrderActivate2.aspx"""
        return self._call("ORDER_ACTIVATE", "ORDER_ACTIVATE", fields)

    def order_cancel(self, **fields) -> dict:
        """aWs_Api_OrderCancel2.aspx"""
        return self._call("ORDER_CANCEL", "ORDER_CANCEL", fields)

    def order_update(self, **fields) -> dict:
        """aWs_Api_OrderUpdate2.aspx"""
        return self._call("ORDER_UPDATE", "ORDER_UPDATE", fields)

    def order_refund(self, **fields) -> dict:
        """aWs_Api_OrderRefund2.aspx"""
        return self._call("ORDER_REFUND", "ORDER_REFUND", fields)

    def order_voucher(self, **fields) -> dict:
        """aWs_Api_OrderVoucher2.aspx"""
        return self._call("ORDER_VOUCHER", "ORDER_VOUCHER", fields)

    def order_validate(self, *, OrderInfo: dict, **extra) -> dict:
        """aWs_Api_OrderValidate2.aspx"""
        self._validate_order_min(OrderInfo)
        payload = {"OrderInfo": OrderInfo}
        payload.update(extra)
        return self._call("ORDER_VALIDATE", "ORDER_VALIDATE", payload)

    # ------------------------------- Helpers -------------------------------
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
        """
        Build a minimal OrderInfoType2 structure.
        BankInfo can be attached by caller as:
          BankInfo={
            "BankName": "...", "BankBranch": "...", "BankAccType": "AHO|CTE",
            "BankAccount": "...", "BankDocument": "...", "BankCity": "..."
          }
        """
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
    
    # ------------------------------ Error helpers ------------------------------
    @staticmethod
    def code_message(code: Optional[str | int]) -> str:
        """Return a human-readable message for a ResponseCode."""
        if code is None:
            return "Unknown error"
        key = str(code).strip()
        return RESPONSE_CODES.get(key, f"Unknown error code {key}")

    @staticmethod
    def error_from_response(resp: dict) -> dict:
        """
        Normalize an API response into {code, message, details}.
        Pulls first message from Messages.Message if present.
        """
        code = str(resp.get("ResponseCode") or "").strip() or None
        msg = resp.get("ResponseMessage") or ""
        messages = ((resp.get("Messages") or {}).get("Message")) or []
        if isinstance(messages, dict):
            messages = [messages]
        detail = ""
        if messages and isinstance(messages[0], dict):
            detail = str(messages[0].get("MessageText") or "").strip()
        base = MoreRemesas.code_message(code)
        human = detail or msg or base
        return {"code": code or "?", "message": human, "details": {"mapped": base, "raw": msg, "first_message": detail}}
