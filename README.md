# More Remesas SDK (Python)

> Official-style Python SDK for **More Payment Evolution — Remittance API v2.0**
> Developed by [**Stanley Castin (n1n24)**](https://github.com/ninjaroot-509)
> Email: [stanleycastin19@gmail.com](mailto:stanleycastin19@gmail.com)

---

## ⚡ Overview

This SDK provides a clean, secure, and typed interface for the **Remittance SOAP API** used by **More Payment Evolution**.
It automatically handles authentication, SOAP envelope creation, retries, and error handling — giving you JSON-like responses instantly.

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
✅ SOAP 1.1 to Python dict converter
✅ 8 API endpoints from Remittance v2.0
✅ Full code tables (status, purpose, relationship, etc.)
✅ Secure logging (no credentials leaked)
✅ Built-in retry + timeout
✅ Custom exceptions for clarity
✅ Light data validation
✅ Ready for `pip install git+...` deployment

---

## Supported func

| Category       | Method            |
| -------------- | ----------------- |
| Authentication | `auth`            |
| Regular APIs   | `rates()`         |
|                | `branches()`      |
|                | `orders_status()` |
| Send Money     | `order_import()`  |
|                | `order_calc()`    |
| Optional APIs  | `order_cancel()`  |
|                | `order_update()`  |

---

## Usage Example

```python
from moreremesas import MoreRemesas

api = MoreRemesas(
    host="...",
    login_user="...",
    login_pass="..."
)

# Get rates
rates = api.rates(SourceCountry="CL", DestinationCountry="HT", Currency="USD")
print("Rates:", rates)

# Prepare sender and receiver
sender = api.person_min(FirstName="JUAN", LastName="RODRIGUEZ", Nationality="UY", Gender="M")
bene   = api.person_min(FirstName="ANA", LastName="PEREZ", Nationality="HT", Gender="F")

# Build order
order = api.order_info_min(
    OrderDate="2025-11-05",
    SourceCountry="CL",
    SourceBranchID="123456",
    OrderCurrency="USD",
    OrderAmount="100.00",
    PayoutBranchID="5091025",
    Customer=sender,
    Beneficiary=bene,
    PayoutCountry="HT",
    PayoutCurrency="USD"
)

# Calculate fees
calc = api.order_calc(**order)
print("Calculation:", calc)

# Send money
resp = api.order_import(**order)
print("Order Response:", resp)

# Check status
status = api.orders_status(OrderPartnerID="ORD001")
print("Status:", status)
```

---

## Code Tables

### OrderStatus

| Code | Meaning            |
| ---- | ------------------ |
| P    | Pending            |
| F    | Paid               |
| R    | Withheld           |
| A    | Canceled           |
| I    | Incidence          |
| N    | Pending Activation |
| T    | In transit         |

### Relationship

`1=Spouse`, `2=Son/Daughter`, `3=Parents`, `8=Friend`, `9999=No information`, etc.

### Purpose

`1=Other`, `2=Family Aid`, `5=Goods purchase`, `9=Fees and services`, etc.

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
| FirstName   | str  | “JUAN”       |
| LastName    | str  | “RODRIGUEZ”  |
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

## Testing

To run tests locally:

```bash
pip install -e .
pytest -v
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
