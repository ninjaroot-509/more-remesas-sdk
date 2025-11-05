from __future__ import annotations
import datetime as dt
from typing import Any, Dict

from .endpoints import PATHS, ACTION_PREFIX
from .soap import SoapClient
from .exceptions import AuthError, ValidationError
from .endpoints import MMT_NS

ORDER_STATUS = {
    "P": "Pending", "F": "Paid", "R": "Withhheld", "A": "Canceled",
    "I": "Incidence", "N": "Pending Activation", "T": "In transit",
}
BANK_ACC_TYPE = {"AHO": "Savings Account", "CTE": "Checking Account"}
RELATIONSHIP = {
    1:"Spouse",2:"Son/Daughter",3:"Parents",4:"Siblings",5:"Close Relative",
    6:"Him/Herself",7:"Ex-Spouse",8:"Friend",9:"Business Partner",10:"Client",
    11:"Employe",12:"Supplier",13:"Creditor",14:"Debtor",15:"Franchisee",16:"Non related",9999:"No information"
}
PURPOSE = {1:"Other",2:"Family Aid",3:"Gift",4:"Service Payment",5:"Goods purchase",
           6:"Medicine Purchase",7:"Study Payments",8:"Debt Payment",9:"Fees and services",
           10:"Travel Ticket",11:"Alimony"}
DOCUMENT_TYPE = {
    1:"Cédula de Identidad Uruguaya",98:"CPF",99:"Documento de Identidad Extranjero",
    523:"Pasaporte",541:"DNI - Argentina",561:"Cédula de Identidad Chilena",
    575:"Carné Identidad Cubano",5911:"Cédula Identidad Boliviana",5951:"Cédula Identidad Paraguaya"
}
BANK_ATTRIBUTE_BY_COUNTRY = {
    "US":{"BankBranch":"ABA Routing number (9 digits)"},
    "ES":{"BankAccount":"IBAN (ES + 22 digits)"},
    "AR":{"BankDocument":"CUIT/CUIL","BankAccount":"CBU (22 digits)"},
    "CL":{"BankDocument":"RUN/RUT"},
    "BR":{"BankDocument":"CPF (11 digits)"},
}

REQUIRED_ORDER_INFO2 = [
    "OrderDate","SourceCountry","SourceBranchID","OrderCurrency","OrderAmount","PayoutBranchID","Customer","Beneficiary"
]

class MoreRemesas:
    def __init__(self, host: str, login_user: str, login_pass: str, timeout: int = 30, retries: int = 3):
        self.host = host.rstrip("/")
        self.login_user = login_user
        self.login_pass = login_pass
        self.soap = SoapClient(self.host, timeout=timeout, retries=retries)
        self.token: str | None = None
        self.token_due: dt.datetime | None = None

    def _authenticate(self) -> None:
        action = ACTION_PREFIX + "AWS_API_AUTH2.Execute"
        body = ("<mmt:AWS_API_AUTH2.Execute><mmt:Logintype>"
                f"<mmt:LoginUser>{self.login_user}</mmt:LoginUser>"
                f"<mmt:LoginPass>{self.login_pass}</mmt:LoginPass>"
                "</mmt:Logintype></mmt:AWS_API_AUTH2.Execute>")
        xml = self._envelope(body)
        root = self.soap.post(PATHS["AUTH"], action, xml)
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

    def _ensure_token(self):
        if not self.token or (self.token_due and dt.datetime.utcnow() >= self.token_due):
            self._authenticate()

    @staticmethod
    def _envelope(body_xml: str, header_xml: str = "") -> str:
        return (f'<?xml version="1.0" encoding="utf-8"?>'
                f'<soap:Envelope xmlns:soap="{PATHS.get("SOAP11","http://schemas.xmlsoap.org/soap/envelope/")}" xmlns:mmt="{MMT_NS}">'
                f"<soap:Header>{header_xml}</soap:Header>"
                f"<soap:Body>{body_xml}</soap:Body></soap:Envelope>")

    @staticmethod
    def _xml2dict(el) -> dict:
        from xml.etree import ElementTree as ET
        out = {}
        for c in list(el):
            k = c.tag.split("}")[-1]
            out[k] = MoreRemesas._xml2dict(c) if list(c) else (c.text or "").strip()
        return out

    def _auth_header_xml(self) -> str:
        return f"<mmt:AuthHeader><mmt:AccessToken>{self.token}</mmt:AccessToken></mmt:AuthHeader>" if self.token else ""

    def _call(self, path_key: str, operation: str, params: Dict[str, Any] | None = None) -> dict:
        self._ensure_token()
        fields = "".join(f"<mmt:{k}>{v}</mmt:{k}>" for k, v in (params or {}).items())
        action = ACTION_PREFIX + operation
        body   = f"<mmt:{operation}>{fields}</mmt:{operation}>"
        xml    = self._envelope(body, self._auth_header_xml())
        root   = self.soap.post(PATHS[path_key], action, xml)
        resp = root.find(".//{MMT}Response") or root.find(".//*[contains(local-name(), 'Response')]")
        if resp is None:
            raise ValidationError("Response not found.")
        return self._xml2dict(resp)

    def rates(self, **fields) -> dict:
        return self._call("RATES", "Rates2.Execute", fields)

    def branches(self, **fields) -> dict:
        return self._call("BRANCHES", "BranchesList2.Execute", fields)

    def orders_status(self, **fields) -> dict:
        return self._call("ORDERS_STATUS", "OrdersStatus2.Execute", fields)

    def order_import(self, **order) -> dict:
        self._validate_order_min(order)
        return self._call("ORDER_IMPORT", "OrderImport2.Execute", order)

    def order_calc(self, **fields) -> dict:
        return self._call("ORDER_CALC", "OrderCalc2.Execute", fields)

    def order_cancel(self, **fields) -> dict:
        return self._call("ORDER_CANCEL", "OrderCancel2.Execute", fields)

    def order_update(self, **fields) -> dict:
        return self._call("ORDER_UPDATE", "OrderUpdate2.Execute", fields)

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
