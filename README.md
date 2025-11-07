# More Remesas SDK (Python)

> Official-style Python SDK for **More Payment Evolution | Remittance API v2.0**  
> Developed by [**Stanley Castin (n1n24)**](https://github.com/ninjaroot-509)  
> Email: [stanleycastin19@gmail.com](mailto:stanleycastin19@gmail.com)

---

## Overview

This SDK provides a clean, secure, and typed interface for the **Remittance SOAP API** used by **More Payment Evolution**.  
It automatically handles authentication, SOAP envelope creation, retries, and error handling and giving you JSON-like responses instantly.

---

## Quick Install

You can install it directly from GitHub:

```bash
pip install "git+https://github.com/ninjaroot-509/more-remesas-sdk.git@main"
```

To update later:

```bash
pip install --upgrade "git+https://github.com/ninjaroot-509/more-remesas-sdk.git@main"
```

---

## Features

✅ Automatic authentication (`aWs_Api_Auth2.aspx`)  
✅ Auto token refresh before expiration  
✅ Reserve Key flow support (`aWs_Api_ReserveKey2.aspx`)  
✅ SOAP 1.1 to Python dict converter  
✅ 8 API endpoints from Remittance v2.0  
✅ Full order lifecycle: Auth → Calc → Reserve → Import → Status  
✅ Secure logging (no credentials leaked)  
✅ Built-in retry + timeout  
✅ Custom exceptions for clarity  
✅ Light data validation

---

## Supported func

| Category       | Method            |
| -------------- | ----------------- |
| Authentication | `auth()`          |
| Core APIs      | `rates()`         |
|                | `branches()`      |
|                | `orders_status()` |
| Order Flow     | `order_calc2()`   |
|                | `reserve_key()`   |
|                | `order_import()`  |
| Optional       | `order_update()`  |
|                | `order_cancel()`  |

---

## Usage Example

```python
from moreremesas import MoreRemesas
from moreremesas.exceptions import MoreError
from datetime import date

api = MoreRemesas(
    host="...",
    login_user="...",
    login_pass="...",
    sandbox=True,
    auto_auth=True,
)

try:
    # Authenticate
    api._ensure_token()

    # --- Step 1: Fetch payout branches dynamically ---
    payout_country = "HT"
    branches = api.branches(Country=payout_country, Type="2", MaxResults="1000")

    # --- Step 2: Extract dynamic currencies from API ---
    currencies = sorted({c["Code"] for b in branches["Branches"]["Branch"] for c in b["Currencies"]["Currency"]})
    pay_ccy = currencies[0]  # Example: "USD" or "HTG" depending on API response

    # --- Step 3: Calculate payout and fees ---
    calc = api.order_calc2(CountryTo=payout_country, PaymentCurrency=pay_ccy, CalcType="1", Amount="500")
    option = calc["Options"]["Option"][0]

    # --- Step 4: Prepare sender & beneficiary ---
    sender = {
        "FirstName": "JEAN RICHARD", "LastName": "MERCIDIEU", "Gender": "M",
        "Nationality": "CL", "Email": "sender@example.com", "Phone": "957540283",
        "Address": {"State": "SANTIAGO", "City": "SANTIAGO", "StreetAndNumber": "CALLE 5, 123"},
        "Document": {"Type": "99", "Number": "X258881311", "IssueCountry": "CL"}
    }

    beneficiary = {
        "FirstName": "STANLEY", "LastName": "CASTIN", "Gender": "M",
        "Nationality": "HT", "Email": "bene@example.com", "Phone": "50947929400",
        "Address": {"State": "PORT AU PRINCE", "City": "PORT AU PRINCE", "StreetAndNumber": "RUE 1, 123"},
        "Document": {"Type": "99", "Number": "X258881311", "IssueCountry": "HT"}
    }

    # --- Step 5: Reserve key (Haiti and similar require it) ---
    order_info = {
        "OrderDate": str(date.today()),
        "SourceCountry": "CL",
        "SourceBranchID": "1234",
        "OrderCurrency": option["SendCurrency"],
        "OrderAmount": option["SendAmount"],
        "PayoutBranchID": option["BranchID"],
        "Customer": sender,
        "Beneficiary": beneficiary,
        "OrderID": "TMP-DEMO-001",
        "OrderPartnerID": "AGENT-DEMO-001",
        "PayoutCountry": payout_country,
        "PayoutCurrency": pay_ccy,
        "PayoutAmount": option["PaymentAmount"],
        "Relationship": "2",
        "PourposeCode": "1",
        "PayerID": option["PayerID"],
        "PayoutMethod": "2",
        "BeneMessage": "Gift transaction"
    }

    resv = api.reserve_key(OrderInfo=order_info)
    reserve_key = resv.get("ReservationKey") or resv.get("ReserveKey")

    # --- Step 6: Import order ---
    imp = api.order_import(ReserveKey=reserve_key, **order_info)
    print("Order imported:", imp)

    # --- Step 7: Check order status ---
    status = api.orders_status(OrderPartnerID=order_info["OrderPartnerID"])
    print("Order status:", status)

except MoreError as e:
    print("SDK error:", e)
```
**Everything is dynamic** — currencies, payer IDs, branches, and ReserveKey flow are handled automatically via API responses.

---

## Code Tables

| Type                   | Code | Meaning        |
| ---------------------- | ---- | -------------- |
| OrderStatus            | `P`  | Pending        |
|                        | `I`  | Incidence      |
|                        | `F`  | Paid           |
|                        | `A`  | Canceled       |
| Relationship           | `1`  | Spouse         |
|                        | `2`  | Child          |
|                        | `8`  | Friend         |
| Purpose (PourposeCode) | `1`  | Other          |
|                        | `2`  | Family Aid     |
|                        | `5`  | Goods Purchase |

### BankAccType

| Code | Type     |
| ---- | -------- |
| AHO  | Savings  |
| CTE  | Checking |

### Bank Attributes by Country

| Country   | Required field                              |
| --------- | ------------------------------------------- |
| USA       | BankBranch → ABA                            |
| Spain     | BankAccount → IBAN                          |
| Argentina | BankAccount → CBU, BankDocument → CUIT/CUIL |
| Chile     | BankDocument → RUN/RUT                      |
| Brazil    | BankDocument → CPF                          |

---

## Models

**`PersonType2`**

| Field       | Type | Example      |
| ----------- | ---- | ------------ |
| FirstName   | str  | “STANLEY”       |
| LastName    | str  | “CASTIN”  |
| Gender      | str  | “M”          |
| Nationality | str  | “UY”         |
| DateOfBirth | str  | “1979-12-01” |

**`BankInfo`**

| Field       | Type | Example        |
| ----------- | ---- | -------------- |
| BankName    | str  | “BANCO ESTADO” |
| BankAccType | str  | “AHO”          |
| BankAccount | str  | “123456789”    |

**`OrderInfoType2`**
Contains all remittance order data (sender, beneficiary, amounts, currencies, etc.).

---

## Exceptions

| Exception         | Description                          |
| ----------------- | ------------------------------------ |
| `MoreError`       | Base error                           |
| `TransportError`  | Network/HTTP issues                  |
| `SoapFaultError`  | SOAP-level faults from server        |
| `AuthError`       | Invalid credentials or expired token |
| `ValidationError` | Local field validation failed        |
| `ServerError`     | Unexpected server response           |

---

## Security

* Credentials (`LoginUser`, `LoginPass`, `AccessToken`) **never appear in logs**
* Automatic retry for 429/5xx
* Custom headers include `X-Request-Id` for tracing
* HTTPS required (always)

---

## Notes

* **ReserveKey flow** is mandatory for some destinations (e.g., Haiti).
* The SDK automatically sends orders in the **origin currency** required by API.
* All currencies and IDs are dynamically fetched from the API.
* The script `test_sdk.py` is a complete interactive example ready for real-world testing.

---

## Run the Example

```bash
python test_sdk.py
```

It will guide you through:

```
→ Country selection
→ Branch + currency discovery
→ Fee calculation
→ Reserve key
→ Final import + status check
```

---

## Installation for a specific

Any user can install it for a specific version via:

```bash
pip install "git+https://github.com/ninjaroot-509/more-remesas-sdk.git@v0.1.0"
```

---

## Contributing

1. Fork the repo
2. Create a feature branch
3. Run `black` and `flake8`
4. Add tests under `/tests`
5. Submit a PR 🙏

---

## Author

**Stanley Castin (n1n24)**  
📩 [stanleycastin19@gmail.com](mailto:stanleycastin19@gmail.com)  
💼 [GitHub — ninjaroot-509](https://github.com/ninjaroot-509)

---

## License

Released under the [MIT License](LICENSE).  
© 2025 **Stanley Castin (n1n24)** — Haiti on fire 🇭🇹🔥

---
