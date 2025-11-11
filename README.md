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

✅ Automatic authentication  
✅ Auto token refresh before expiration  
✅ Reserve Key flow support  
✅ SOAP 1.1 to Python dict converter  
✅ 8 API endpoints from Remittance v2.0  
✅ Full order lifecycle: Auth → Calc → Reserve → Import → Status  
✅ Secure logging (no credentials leaked)  
✅ Built-in retry + timeout  
✅ Custom exceptions for clarity  
✅ Light data validation

---

## Supported Methods

| Category           | Method                           | Description                                                             |
| ------------------ | -------------------------------- | ----------------------------------------------------------------------- |
| **Authentication** | `auth()`                         | Authenticates the user and returns an access token.                     |
| **Core APIs**      | `rates()`                        | Retrieves exchange rates between source and payout currencies.          |
|                    | `branches()`                     | Lists all payout branches (Cash / Bank / Wallet) by country and method. |
|                    | `orders_status()`                | Gets the current status of a transaction.                               |
| **Order Flow**     | `order_calc()` | Calculates payout amount, fees, and rates for a given corridor.         |
|                    | `reserve_key()`                  | Reserves an operation key before sending money.                         |
|                    | `order_import()`                 | Confirms (imports) an order after reservation.                          |
| **Optional**       | `order_update()`                 | Updates a previously imported order.                                    |
|                    | `order_cancel()`                 | Cancels or refunds an order.                                            |

---

## Method Parameters

### `auth()`

Authenticate with username and password.

| Parameter   | Type  | Required | Description                         |
| ----------- | ----- | -------- | ----------------------------------- |
| `LoginUser` | `str` | ✅        | Username provided by More Sistemas. |
| `LoginPass` | `str` | ✅        | Password for the API account.       |

**Returns:**
`AccessToken`, `ResponseCode`, `DueDate`, `Messages`.

---

### `rates()`

Retrieve exchange rates between two currencies.

| Parameter             | Type  | Required | Description                                    |
| --------------------- | ----- | -------- | ---------------------------------------------- |
| `PayerId`             | `str` | ✅        | Payer or branch network ID.                    |
| `BranchID`            | `str` | ✅        | Branch identifier.                             |
| `Currency`            | `str` | ✅        | Destination (payout) currency code.            |
| `BaseCurrency`        | `str` | ✅        | Source (origin) currency code.                 |
| `IncludeDynamicRates` | `str` | Optional | Use `"1"` to include updated or special rates. |

**Returns:**
Rate list with ID, Currency, BaseCurrency, RateValue, and EffectiveDate.

---

### `branches()`

List payout branches for a given country and method.

| Parameter    | Type  | Required | Description                                         |
| ------------ | ----- | -------- | --------------------------------------------------- |
| `Country`    | `str` | ✅        | ISO-2 code of the payout country (e.g. `HT`, `DO`). |
| `Type`       | `str` | ✅        | Channel type: `1=Bank`, `2=Cash`, `3=Wallet`.       |
| `MaxResults` | `str` | Optional | Pagination size (default `1000`).                   |
| `NextID`     | `str` | Optional | Cursor for next page.                               |

**Returns:**
Branch list with IDs, payer info, city/state, available currencies, and bank details.

---

### `order_calc()`

Calculate a payout quote based on amount, currency, and corridor.

| Parameter         | Type   | Required | Description                                                                                |
| ----------------- | ------ | -------- | ------------------------------------------------------------------------------------------ |
| `CountryTo`       | `str`  | ✅        | Destination country ISO-2 code.                                                            |
| `PaymentCurrency` | `str`  | ✅        | Destination payout currency (e.g. `HTG`, `USD`).                                           |
| `CalcType`        | `str`  | ✅        | Calculation mode: `1=To pay at destination`, `2=Equivalent base`, `3=Commission included`. |
| `Amount`          | `str`  | ✅        | Amount to send or pay (string with decimals).                                              |
| `CountryFrom`     | `str`  | Optional | Origin country ISO-2 code (if required).                                                   |
| `Attributes`      | `dict` | Optional | Additional partner-specific fields.                                                        |

**Returns:**
List of payout options with network description, payout amounts, currencies, fees, taxes, and exchange rates.

---

### `reserve_key()`

Reserve a transfer key (pre-authorization before sending).

| Parameter   | Type   | Required | Description                                                   |
| ----------- | ------ | -------- | ------------------------------------------------------------- |
| `OrderInfo` | `dict` | ✅        | Order structure with sender, beneficiary, and payout details. |

**Returns:**
`ReserveKey`, expiration info, and any validation messages.

---

### `order_import()`

Confirm and import a reserved transfer order.

| Parameter    | Type   | Required | Description                                                  |
| ------------ | ------ | -------- | ------------------------------------------------------------ |
| `ReserveKey` | `str`  | Optional | Key obtained from `reserve_key()` (if required by corridor). |
| `OrderInfo`  | `dict` | ✅        | Full order info: source, payout, sender, and beneficiary.    |

**Returns:**
Confirmation of successful import with system reference and status codes.

---

### `orders_status()`

Get status for a specific transaction or partner order.

| Parameter        | Type  | Required | Description                        |
| ---------------- | ----- | -------- | ---------------------------------- |
| `OrderPartnerID` | `str` | Optional | Internal partner order ID.         |
| `OrderId`        | `str` | Optional | Provider-generated transaction ID. |

**Returns:**
Order status, timestamps, and transaction details.

---

### `order_update()`

Update a previously imported order (rarely used).

| Parameter    | Type   | Required | Description                   |
| ------------ | ------ | -------- | ----------------------------- |
| `OrderId`    | `str`  | ✅        | Target order ID.              |
| `Attributes` | `dict` | Optional | New values or status updates. |

---

### `order_cancel()`

Cancel or refund an existing order.

| Parameter | Type  | Required | Description                                            |
| --------- | ----- | -------- | ------------------------------------------------------ |
| `OrderId` | `str` | ✅        | Target order ID.                                       |
| `Reason`  | `str` | Optional | Cancel or refund reason (e.g. `"CANCELLED_BY_AGENT"`). |

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
    calc = api.order_calc(CountryTo=payout_country, PaymentCurrency=pay_ccy, CalcType="1", Amount="500")
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
        "OrderPartnerID": "034833",
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
