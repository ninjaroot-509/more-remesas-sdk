from __future__ import annotations
from typing import TypedDict, NotRequired, Dict, Any

class PersonType2(TypedDict, total=False):
    FirstName: str
    LastName: str
    MiddleName: NotRequired[str]
    MaidenName: NotRequired[str]
    Phone: NotRequired[str]
    DateOfBirth: NotRequired[str]  # YYYY-MM-DD
    Activity: NotRequired[str]
    Profession: NotRequired[str]
    Position: NotRequired[str]
    MaritalStatus: NotRequired[str]  # "2"
    Gender: NotRequired[str]         # "M"|"F"
    Nationality: NotRequired[str]    # ISO 3166-1 alpha-2
    Email: NotRequired[str]
    Address: NotRequired[Dict[str, Any]]
    Document: NotRequired[Dict[str, Any]]
    PartnerId: NotRequired[str]
    Relationship: NotRequired[str]
    PourposeCode: NotRequired[str]

class BankInfo(TypedDict, total=False):
    BankName: str
    BankBranch: str
    BankAccType: str   # AHO|CTE
    BankAccount: str
    BankDocument: NotRequired[str]
    BankCity: NotRequired[str]

class OrderInfoType2(TypedDict, total=False):
    OrderId: NotRequired[str]
    OrderPartnerID: NotRequired[str]
    OrderDate: str              # YYYY-MM-DD
    SourceCountry: str          # ISO alpha-2
    SourceBranchID: str
    OrderCurrency: str          # ISO 4217
    OrderAmount: str            # "100.00"
    OrderRateID: NotRequired[str]
    PayoutCountry: NotRequired[str]
    PayoutBranchID: str
    PayoutCurrency: NotRequired[str]
    PayoutAmount: NotRequired[str]
    BeneMessage: NotRequired[str]
    Relationship: NotRequired[str]
    PourposeCode: NotRequired[str]
    Customer: PersonType2
    Beneficiary: PersonType2
    BankInfo: NotRequired[BankInfo]
