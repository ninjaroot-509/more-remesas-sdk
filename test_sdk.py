#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from datetime import date, datetime, timezone
import logging, re
from typing import Any, Dict, List, Tuple, Optional

from moreremesas import MoreRemesas
from moreremesas.exceptions import MoreError

# -------------------- LOG --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)sZ | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("more-e2e")

# -------------------- CONFIG --------------------
HOST = "..."
LOGIN_USER = "..."
LOGIN_PASS = "..."

BRANCH_TYPES = {"Cash": "2", "Bank": "1", "Wallet": "3"}
CALC_TYPES = {"To pay at destination": "1", "Equivalent base": "2", "Commission included": "3"}

BANK_ACCOUNT_TYPES = [
    ("CC",  "Checking account"),  # CTE
    ("CA",  "Savings account"),   # AHO
    ("IBAN","IBAN / Other"),
]
ACC_TYPE_LABEL = {"CC": "CTE", "CA": "AHO", "IBAN": "IBAN"}

BASE_ORDER_CCY = "CLP"

# -------------------- LIMITS TOGGLE --------------------
APPLY_LIMITS: bool = False

# -------------------- INPUT HELPERS --------------------
def ask(prompt: str, default: str | None = None) -> str:
    sfx = f" [{default}]" if default not in (None, "") else ""
    v = input(f"{prompt}{sfx}: ").strip()
    ans = (default or "") if v == "" and default is not None else v
    log.info("INPUT | %s => %s", prompt, ans or "(empty)")
    return ans

def choose(prompt: str, options: List[str], default_idx: Optional[int] = None) -> int:
    print(prompt)
    for i, opt in enumerate(options, 1):
        mark = " (default)" if default_idx is not None and (i - 1) == default_idx else ""
        print(f"  {i}. {opt}{mark}")
    while True:
        raw = input("→ #: ").strip()
        if raw == "" and default_idx is not None:
            log.info("INPUT | %s => default index %d (%s)", prompt, default_idx, options[default_idx])
            return default_idx
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                log.info("INPUT | %s => index %d (%s)", prompt, idx, options[idx])
                return idx
        print("  Invalid choice.")

def ask_required(prompt: str) -> str:
    while True:
        v = input(f"{prompt}: ").strip()
        if v:
            log.info("INPUT | %s => %s", prompt, v)
            return v
        print("  Required value.")

def _to_float(x: Any) -> float:
    if x is None: return 0.0
    if isinstance(x, (int, float)): return float(x)
    s = str(x)
    if "," in s and "." in s and s.find(",") > s.find("."):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    return float(s)

def ask_money(prompt: str) -> str:
    while True:
        v = input(f"{prompt}: ").strip()
        try:
            _ = _to_float(v)
            log.info("INPUT | %s => %s", prompt, v)
            return v
        except Exception:
            print("  Invalid amount. Example: 1, 5, 300.50")

def ask_money_limited(prompt: str, ccy: str, *, min_amt: Optional[float], max_amt: Optional[float]) -> str:
    tips = []
    if min_amt is not None: tips.append(f"min {min_amt:,.2f} {ccy}")
    if max_amt is not None: tips.append(f"max {max_amt:,.2f} {ccy}")
    hint = f" ({', '.join(tips)})" if tips else ""
    while True:
        raw = ask_money(prompt + hint)
        val = _to_float(raw)
        if min_amt is not None and val < float(min_amt):
            print(f"  Must be ≥ {min_amt:,.2f} {ccy}")
            continue
        if max_amt is not None and val > float(max_amt):
            print(f"  Must be ≤ {max_amt:,.2f} {ccy}")
            continue
        return raw

def confirm(prompt: str) -> bool:
    v = input(f"{prompt} [y/N]: ").strip().lower()
    ok = v in ("y", "yes", "wi", "oui")
    log.info("CONFIRM | %s => %s", prompt, ok)
    return ok

# -------------------- UTIL --------------------
def _as_list(node: Any) -> List[Dict]:
    if not node or node == "": return []
    if isinstance(node, list): return node
    if isinstance(node, dict): return [node]
    return []

def gen_partner_ref_numeric() -> str:
    return datetime.now(timezone.utc).strftime("%H%M%S")

def norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

def split_city_state(val: str) -> Tuple[str, str]:
    parts = (val or "").split("/")
    city = parts[0].strip() if parts else ""
    state = parts[1].strip() if len(parts) > 1 else ""
    return city, state

def city_score(cand_city: str, cand_state: str, want_city: str, want_state: str) -> int:
    score = 0
    if norm(cand_city) == norm(want_city) and cand_city: score += 2
    elif norm(want_city) and norm(cand_city).startswith(norm(want_city)): score += 1
    elif norm(want_city) and norm(want_city) in norm(cand_city): score += 1
    if cand_state and want_state and norm(cand_state) == norm(want_state): score += 1
    return score

def _fmt_money_en(val: float) -> str:
    return f"{val:,.2f}"

def _sum_taxes_for_send_ccy(op: Dict) -> float:
    taxes = _as_list((op.get("Taxes") or {}).get("Tax"))
    total = 0.0
    send_ccy = str(op.get("SendCurrency") or "").upper()
    for t in taxes:
        amt = _to_float(t.get("Amount") or t.get("TaxAmount") or 0)
        ccy = str(t.get("Currency") or t.get("TaxCurrency") or send_ccy).upper()
        if not ccy or ccy == send_ccy:
            total += amt
    return total

def _guess_rate(op: Dict) -> str:
    for k in ("ExchangeRate","Rate","RateValue","FX","FxRate"):
        v = op.get(k)
        try:
            if v is not None:
                return f"{_to_float(v):,.4f}"
        except Exception:
            pass
    pay_amt = _to_float(op.get("PaymentAmount") or 0)
    send_amt = _to_float(op.get("SendAmount") or 0)
    if pay_amt and send_amt:
        return f"{(pay_amt / send_amt):,.4f}"
    return ""

def _pick_ccys_from_options(options: List[Dict]) -> Tuple[str, str]:
    send_ccy = ""
    pay_ccy = ""
    for op in options:
        if not send_ccy:
            send_ccy = str(op.get("SendCurrency") or "").upper().strip()
        if not pay_ccy:
            pay_ccy = str(op.get("PaymentCurrency") or "").upper().strip()
        if send_ccy and pay_ccy:
            break
    return send_ccy or "XXX", pay_ccy or "XXX"

# -------------------- ERROR NORMALIZATION --------------------
def _error_from_response(resp: dict) -> Dict[str, Any]:
    mapper = getattr(MoreRemesas, "error_from_response", None)
    if callable(mapper):
        return mapper(resp)
    code = str(resp.get("ResponseCode") or "").strip() or "?"
    msg = resp.get("ResponseMessage") or ""
    messages = ((resp.get("Messages") or {}).get("Message")) or []
    if isinstance(messages, dict):
        messages = [messages]
    detail = ""
    if messages and isinstance(messages[0], dict):
        detail = str(messages[0].get("MessageText") or "").strip()
    if detail:
        msg = f"{msg} | {detail}" if msg else detail
    return {"code": code, "message": msg or "Unknown error", "details": {}}

def _ensure_ok(resp: dict, ctx: str = "API") -> None:
    code = str(resp.get("ResponseCode") or "")
    if code and code != "1000":
        err = _error_from_response(resp)
        raise MoreError(f"{ctx}: [{err['code']}] {err['message']}")

# -------------------- API HELPERS --------------------
def fetch_branches_all(api: MoreRemesas, payout_country: str, method_label: str, page_size="1000") -> List[Dict]:
    t = BRANCH_TYPES[method_label]
    all_items: List[Dict] = []
    next_id = "0"
    while True:
        log.info("BRANCHES | Request: Country=%s Type=%s MaxResults=%s NextID=%s",
                 payout_country, t, page_size, next_id)
        resp = api.branches(Country=payout_country, Type=t, MaxResults=page_size, NextID=next_id)
        _ensure_ok(resp, "Branches")
        items = _as_list(resp.get("Branches", {}).get("Branch") or resp.get("Branches", {}).get("BranchItem"))
        for it in items:
            all_items.append({
                "BranchId":  str(it.get("BranchId") or it.get("ID") or it.get("Id") or it.get("BranchID") or ""),
                "PayerId":   str(it.get("PayerId") or it.get("PayerID") or "0"),
                "Name":      it.get("Name") or it.get("BranchName") or "",
                "CityState": it.get("CityState") or it.get("City") or it.get("CityName") or "",
                "Currencies": _as_list((it.get("Currencies") or {}).get("Currency")),
                "BankID":    str(it.get("BankID") or "").strip(),
                "BankName":  (it.get("BankName") or "").strip(),
                "Type":      str(it.get("Type") or ""),  # 1 bank, 2 cash, 3 wallet
            })
        next_id = str(resp.get("NextID") or "0")
        if next_id in ("0", "", None): break
    return [x for x in all_items if x["BranchId"]]

def currencies_from_branches(branches: List[Dict]) -> List[str]:
    codes = set()
    for it in branches:
        for c in it.get("Currencies", []):
            code = c if isinstance(c, str) else (c.get("Currency") or c.get("Code") or "")
            code = (str(code) or "").strip().upper()
            if code: codes.add(code)
    return sorted(codes)

def filter_branches_by_ccy(branches: List[Dict], ccy: str) -> List[Dict]:
    out = []
    for it in branches:
        codes = set()
        for c in it["Currencies"]:
            code = c if isinstance(c, str) else (c.get("Currency") or c.get("Code") or "")
            if code: codes.add(str(code).strip().upper())
        if ccy.upper() in codes or len(codes) == 0:
            out.append(it)
    return out or branches

def best_one_per_payer(branches: List[Dict], want_city: str, want_state: str) -> List[Dict]:
    by_payer: Dict[str, Dict] = {}
    for it in branches:
        city, state = split_city_state(it["CityState"])
        sc = city_score(city, state, want_city, want_state)
        cur = by_payer.get(it["PayerId"])
        if cur is None or sc > cur["_score"]:
            by_payer[it["PayerId"]] = {**it, "_score": sc}
    res = list(by_payer.values())
    res.sort(key=lambda x: (-x["_score"], x["Name"]))
    return res

def branches_for_method(
    branches: List[Dict],
    method_label: str,
    *,
    pay_ccy: Optional[str] = None,
    want_city: str = "",
    want_state: str = "",
    best_per_payer: bool = True,
) -> List[Dict]:
    want_type = BRANCH_TYPES[method_label]
    pool = [b for b in branches if str(b.get("Type") or "") == want_type]
    if pay_ccy:
        pool = filter_branches_by_ccy(pool, pay_ccy)
    if best_per_payer:
        ranked = best_one_per_payer(pool, want_city, want_state)
        return ranked or pool
    return pool

# -------- Currency limits ----------
def _extract_currency_limits_from_entry(cur: Dict) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    def _clean(v):
        if v in (None, "", {}):
            return None
        try:
            f = _to_float(v)
            return None if abs(f) < 1e-12 else f
        except Exception:
            return None
    min_raw = cur.get("AmmountOrderMin") or cur.get("AmountOrderMin")
    max_raw = cur.get("AmmountOrderMax") or cur.get("AmountOrderMax")
    day_raw = cur.get("CurrencyAmmountDayLimit") or cur.get("CurrencyAmountDayLimit")
    return _clean(min_raw), _clean(max_raw), _clean(day_raw)

def consolidate_limits(branches: List[Dict], pay_ccy: str) -> Dict[str, Optional[float]]:
    mins, maxs, days = [], [], []
    for b in branches:
        for cur in b.get("Currencies", []):
            if not isinstance(cur, dict): continue
            if str(cur.get("Currency") or "").upper() != pay_ccy.upper(): continue
            mn, mx, dy = _extract_currency_limits_from_entry(cur)
            if mn is not None: mins.append(mn)
            if mx is not None: maxs.append(mx)
            if dy is not None: days.append(dy)
    return {"min": max(mins) if mins else 0,
            "max": min(maxs) if maxs else 0,
            "day": min(days) if days else 0}

# -------------------- CALC TABLE --------------------
def print_calc_table_portal(options: List[Dict]) -> None:
    send_ccy, pay_ccy = _pick_ccys_from_options(options)
    cols = [
        ("Correspondent",         46),
        ("FX Rate",               14),
        (f"To charge {send_ccy}", 18),
        (f"Fees {send_ccy}",      16),
        (f"Total {send_ccy}",     16),
        (f"At dest. {pay_ccy}",   16),
    ]
    bar = " ".join(("=" * w) for _, w in cols)
    print("\n" + bar)
    print(" ".join(f"{title:<{w}}" for title, w in cols))
    print(" ".join(("-" * w) for _, w in cols))
    for op in options:
        desc = str(op.get("Description") or op.get("Network") or op.get("PayerName") or "").upper().strip()
        send_amt = _to_float(op.get("SendAmount") or 0.0)
        pay_amt  = _to_float(op.get("PaymentAmount") or 0.0)
        fees     = _sum_taxes_for_send_ccy(op)
        total    = send_amt + fees
        rate_s   = _guess_rate(op)
        row = [desc, rate_s, _fmt_money_en(send_amt), _fmt_money_en(fees), _fmt_money_en(total), _fmt_money_en(pay_amt)]
        print(" ".join(f"{cell:<{w}}" for cell, (_, w) in zip(row, cols)))
    print(bar + "\n")

# -------------------- CORE CALC SELECTION --------------------
def _filter_calc_by_method(
    options: List[Dict],
    method_label: str,
    allowed_branch_ids: Optional[set[str]] = None,
    allowed_payer_ids: Optional[set[str]] = None,
    allowed_bank_ids: Optional[set[str]] = None,
) -> List[Dict]:
    if not options:
        return []

    if method_label == "Bank":
        any_bank_in_options = any(str(op.get("BankID") or "").strip() for op in options)
        if not any_bank_in_options:
            return options

    out = []
    for op in options:
        bid = str(op.get("BranchID") or "").strip()
        pid = str(op.get("PayerID") or op.get("PayerId") or "").strip()
        bankid = str(op.get("BankID") or "").strip()
        ok = True
        if method_label in ("Bank", "Wallet"):
            ok = False
            if allowed_branch_ids and bid and bid in allowed_branch_ids: ok = True
            if not ok and allowed_payer_ids and pid and pid in allowed_payer_ids: ok = True
            if not ok and allowed_bank_ids and bankid and bankid in allowed_bank_ids: ok = True
        if ok:
            out.append(op)

    if method_label in ("Bank", "Wallet") and not out:
        raise MoreError("No CALC options match the selected payout method for this currency.")
    return out

def select_calc_option(
    api: MoreRemesas,
    payout_country: str,
    pay_ccy: str,
    calc_type_value: str,
    user_amt: str,
    method_label: str,
    allowed_branch_ids: Optional[set[str]],
    allowed_payer_ids: Optional[set[str]],
    bank_id: Optional[str] = None,
) -> Dict:
    params = dict(CountryTo=payout_country, PaymentCurrency=pay_ccy,
                  CalcType=calc_type_value, Amount=user_amt)
    if method_label == "Bank" and bank_id:
        params["BankID"] = bank_id

    calc = api.order_calc(**params)
    _ensure_ok(calc, "OrderCalc")
    options = _as_list((calc.get("Options") or {}).get("Option"))

    if not options:
        err = _error_from_response(calc)
        raise MoreError(f"CALC failed: [{err['code']}] {err['message']}")

    allowed_bank_ids = {bank_id} if bank_id else None
    options = _filter_calc_by_method(
        options, method_label, allowed_branch_ids, allowed_payer_ids, allowed_bank_ids
    )

    print_calc_table_portal(options)
    labels = [f"{op.get('Description','')} | receive {op.get('PaymentAmount','')} {op.get('PaymentCurrency','')}" for op in options]
    iop = choose("Pick a network/payer option", labels, 0)
    return options[iop]

# ---- RATES ----
def fetch_rate_id_and_value(api: MoreRemesas, payer_id: str, branch_id: str, pay_ccy: str, order_ccy: str) -> Tuple[str, float]:
    try:
        log.info("RATES2 | Request: PayerId=%s BranchID=%s Currency=%s BaseCurrency=%s IncludeDynamicRates=1",
                 payer_id, branch_id, pay_ccy, order_ccy)
        resp = api.rates(PayerId=payer_id, BranchID=branch_id, Currency=pay_ccy,
                         BaseCurrency=order_ccy, IncludeDynamicRates="1")
        _ensure_ok(resp, "Rates")
    except Exception:
        return "", 0.0
    rates = _as_list(resp.get("Rates", {}).get("Rate") or resp.get("Rates"))
    for r in rates:
        rid = str(r.get("ID") or r.get("RateID") or "0")
        val = 0.0
        for k in ("ExchangeRate","Rate","RateValue","FX","FxRate"):
            try:
                if r.get(k) is not None:
                    val = _to_float(r.get(k))
                    break
            except Exception:
                pass
        if rid and rid != "0":
            return rid, val
        if val:
            return "", val
    return "", 0.0

def extract_reserve_key(resv: dict) -> str:
    attrs = resv.get("Attributes"); attr_key = ""
    if isinstance(attrs, dict):
        attr_key = attrs.get("ReserveKey") or attrs.get("ReservationKey") or ""
    return (resv.get("ReservationKey") or resv.get("ReserveKey") or
            resv.get("PaymentKey") or resv.get("OrderPayoutKey") or attr_key or "")

def message_codes(payload: dict) -> set[str]:
    msgs = (payload.get("Messages") or {}).get("Message") or []
    if isinstance(msgs, dict): msgs = [msgs]
    return {str(m.get("MessageCode")) for m in msgs if isinstance(m, dict)}

# ---- BankInfo validation ----
def validate_bankinfo_fields(bankinfo: Dict[str, Any]) -> None:
    req = ["BankName", "BankAccType", "BankAccount", "BankBranch", "BankCity"]
    for k in req:
        v = str(bankinfo.get(k) or "").strip()
        if not v:
            raise MoreError(f"{k} is required for Bank payouts.")
    if bankinfo["BankAccType"].upper() not in {"CC", "CA", "IBAN"}:
        raise MoreError("BankAccType must be one of: CC, CA, IBAN.")

# ---- Country quick validation rules & prompts ----
def _re_digits(n: int) -> re.Pattern:
    return re.compile(rf"^\d{{{n}}}$")

RE_CBU_22    = _re_digits(22)                              # Argentina
RE_CPF_11    = _re_digits(11)                              # Brasil
RE_ROUTING9  = _re_digits(9)                               # USA
RE_IFSC_11   = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$", re.I) # India
RE_RUT       = re.compile(r"^\d{7,8}-[\dkK]$")             # Chile

def collect_country_bank_extras(payout_country: str, bank_name_default: str) -> Dict[str, Any]:
    """
    Ask only once after Bank selection. Return a dict for BankInfo.
      - AR: BankName, CBU(22), AccountType (AHO|CTE|IBAN), CUIT/CUIL, BankAccount
      - BR: BankName, Agency->BankBranch, AccountNumber->BankAccount, AccountType, CPF(11)
      - CL: BankName, BankAccount, AccountType, RUT
      - US: BankName, BankAccount, AccountType, RoutingNumber(9)
      - IN: BankName, BankAccount, AccountType, IFSC(11)
    BankBranch/BankCity are auto-filled later from the chosen Branch.
    """
    c = payout_country.upper().strip()
    extras: Dict[str, Any] = {}

    extras["BankName"] = bank_name_default or ask_required("Bank name")

    acct_labels = [lbl for _, lbl in BANK_ACCOUNT_TYPES]
    ai = choose("Account Type", acct_labels, 0)
    acct_code, _ = BANK_ACCOUNT_TYPES[ai]
    extras["BankAccType"] = acct_code

    extras["BankBranch"] = ""
    extras["BankCity"]   = ""

    if c == "AR":
        cbu  = ask_required("CBU (22 digits)")
        if not RE_CBU_22.match(cbu):
            raise MoreError("Invalid CBU. Must be 22 digits.")
        cuit = ask_required("CUIT/CUIL")
        acc  = ask_required("Account number")
        extras.update({"BankAccount": acc, "BankDocument": cuit, "CBU": cbu})

    elif c == "BR":
        agency = ask_required("Agency")
        acc    = ask_required("Account number")
        cpf    = ask_required("CPF (11 digits)")
        if not RE_CPF_11.match(cpf):
            raise MoreError("Invalid CPF. Must be 11 digits.")
        extras.update({"BankBranch": agency, "BankAccount": acc, "BankDocument": cpf, "CPF": cpf})

    elif c == "CL":
        acc = ask_required("Account number")
        rut = ask_required("RUT (e.g., 12345678-K)")
        if not RE_RUT.match(rut):
            raise MoreError("Invalid RUT format. Expected ########-X.")
        extras.update({"BankAccount": acc, "BankDocument": rut, "RUT": rut})

    elif c in ("US", "USA", "UNITED STATES"):
        acc = ask_required("Account number")
        rn  = ask_required("Routing number (9 digits)")
        if not RE_ROUTING9.match(rn):
            raise MoreError("Invalid routing number, must be 9 digits.")
        extras.update({"BankAccount": acc, "RoutingNumber": rn, "BankDocument": rn})

    elif c in ("IN", "INDIA"):
        acc  = ask_required("Account number")
        ifsc = ask_required("IFSC (11 chars, e.g., SBIN0000001)")
        if not RE_IFSC_11.match(ifsc):
            raise MoreError("Invalid IFSC format.")
        extras.update({"BankAccount": acc, "IFSC": ifsc, "BankDocument": ifsc})

    else:
        acc = ask_required("Account number / IBAN")
        extras.update({"BankAccount": acc, "BankDocument": acc})

    return extras

# ---- Reserve + retry if bad rate ----
def try_reserve_and_import(
    api: MoreRemesas,
    order_info: Dict[str, Any],
    *,
    payout_country: str,
    pay_ccy: str,
    calc_type_value: str,
    method_label: str,
    allowed_branch_ids: Optional[set[str]],
    allowed_payer_ids: Optional[set[str]],
) -> None:
    if method_label == "Bank":
        validate_bankinfo_fields(order_info.get("BankInfo") or {})

    resv = api.reserve_key(OrderInfo=order_info)
    log.info("RESERVE | %s", resv)
    _ensure_ok(resv, "ReserveKey")
    rk = extract_reserve_key(resv)
    codes = message_codes(resv)

    payment_key = resv.get("PaymentKey") or resv.get("OrderPayoutKey") or ""
    if payment_key:
        print(f"PaymentKey (customer must present this code at payout): {payment_key}")

    if rk:
        preview = {**{k: v for k, v in order_info.items() if k not in ("Customer","Beneficiary")},
                   "Customer": order_info["Customer"], "Beneficiary": order_info["Beneficiary"]}
        print("\nORDER IMPORT | Payload:", preview)
        imp = api.order_import(ReserveKey=rk, **order_info)
        print("\nImport result:", imp)
        _ensure_ok(imp, "OrderImport")
        codes_imp = message_codes(imp)
        if "22" in codes_imp:
            raise MoreError("Agent credit limit exceeded (code 22). Reduce amount or increase ceiling.")
        return

    if "103" in codes:
        log.warning("Reserve failed with 103: refreshing CALC and retrying with latest rate/amounts.")
        calc = api.order_calc(CountryTo=payout_country, PaymentCurrency=pay_ccy, CalcType=calc_type_value, Amount=order_info["PayoutAmount"])
        _ensure_ok(calc, "OrderCalc (retry)")
        options = _as_list((calc.get("Options") or {}).get("Option"))
        options = _filter_calc_by_method(options, method_label, allowed_branch_ids, allowed_payer_ids)
        if not options:
            raise MoreError("No CALC options after refresh.")
        same_bid = str(order_info.get("PayoutBranchID") or "")
        opt = next((o for o in options if str(o.get("BranchID") or "") == same_bid), options[0])
        send_ccy = str(opt.get("SendCurrency") or order_info["OrderCurrency"])
        send_amt = f"{_to_float(opt.get('SendAmount') or 0):.2f}"
        pay_amt  = f"{_to_float(opt.get('PaymentAmount') or order_info['PayoutAmount']):.2f}"
        order_info["OrderCurrency"] = send_ccy
        order_info["OrderAmount"]   = send_amt
        order_info["PayoutAmount"]  = pay_amt
        rid, rval = fetch_rate_id_and_value(
            api,
            str(order_info.get("PayerID") or ""),
            str(order_info.get("PayoutBranchID") or ""),
            pay_ccy,
            order_info["OrderCurrency"],
        )
        if rid:
            order_info["OrderRateID"] = rid
        if rval:
            order_info["ExchangeRate"] = f"{float(rval):.6f}"
        resv2 = api.reserve_key(OrderInfo=order_info)
        log.info("RESERVE-RETRY | %s", resv2)
        _ensure_ok(resv2, "ReserveKey (retry)")
        rk2 = extract_reserve_key(resv2)
        if not rk2:
            err = _error_from_response(resv2)
            raise MoreError(f"Reserve retry failed: [{err['code']}] {err['message']}")
        preview = {**{k: v for k, v in order_info.items() if k not in ("Customer","Beneficiary")},
                   "Customer": order_info["Customer"], "Beneficiary": order_info["Beneficiary"]}
        print("\nORDER IMPORT | Payload:", preview)
        imp2 = api.order_import(ReserveKey=rk2, **order_info)
        print("\nImport result:", imp2)
        _ensure_ok(imp2, "OrderImport (retry)")
        codes_imp2 = message_codes(imp2)
        if "22" in codes_imp2:
            raise MoreError("Agent credit limit exceeded (code 22). Reduce amount or increase ceiling.")
        return

    err = _error_from_response(resv)
    raise MoreError(f"Reserve failed: [{err['code']}] {err['message']}")

# -------------------- FLOWS --------------------
def _choose_bank_from_branches(branches: List[Dict]) -> Tuple[Optional[str], Optional[str]]:
    uniq: Dict[str, str] = {}
    for b in branches:
        bid = str(b.get("BankID") or "").strip()
        bname = (b.get("BankName") or "").strip()
        if not bid or bid == "0":
            continue
        uniq[bid] = bname or f"Bank {bid}"
    if not uniq:
        return None, None
    ordered = sorted(uniq.items(), key=lambda x: x[1].lower())
    labels = [f"{name} (BankID={bid})" for bid, name in ordered]
    idx = choose("Bank (destination)", labels, 0)
    bid, name = ordered[idx]
    return bid, name

def flow_calculate(api: MoreRemesas):
    payout_country = ask("Payout Country (ISO-2)", "HT")
    method_ui = ["Cash window", "Bank", "Wallet"]
    mi = choose("Payout method", method_ui, 0)
    method_label = ["Cash", "Bank", "Wallet"][mi]

    branches_raw = fetch_branches_all(api, payout_country, method_label, "1000")

    all_ccys = currencies_from_branches(branches_raw)
    if not all_ccys: raise MoreError("No payout currencies returned by API.")
    idx_ccy = choose("Payout Currency", all_ccys, 0)
    pay_ccy = all_ccys[idx_ccy]

    if method_label == "Bank":
        branches_all_for_filter = branches_for_method(branches_raw, method_label, pay_ccy=pay_ccy, best_per_payer=False)
    else:
        branches_all_for_filter = branches_for_method(branches_raw, method_label, pay_ccy=pay_ccy, best_per_payer=True)

    allowed_branch_ids = {b["BranchId"] for b in branches_all_for_filter if b.get("BranchId")}
    allowed_payer_ids  = {b["PayerId"] for b in branches_all_for_filter if b.get("PayerId")}

    bank_id = None
    if method_label == "Bank":
        has_any_bank = any((str(b.get("BankID") or "").strip() not in ("", "0")) for b in branches_all_for_filter)
        if not has_any_bank:
            raise MoreError(f"Bank mode unavailable for {payout_country}/{pay_ccy}. Try Cash or Wallet.")
        bank_id, _ = _choose_bank_from_branches(branches_all_for_filter)
        if not bank_id:
            raise MoreError("No bank selected. BankID is required for Bank mode.")

    limits = consolidate_limits(branches_all_for_filter, pay_ccy)
    print(f"Daily payout limit for {pay_ccy}: {limits['day']:,.2f}")

    calc_type_value = CALC_TYPES["To pay at destination"]
    amt = ask_money(f"Amount API in {pay_ccy}")
    print(f"\nEntered amount: {amt} {pay_ccy} (CalcType={calc_type_value})")

    op = select_calc_option(
        api, payout_country, pay_ccy, calc_type_value,
        amt, method_label, allowed_branch_ids, allowed_payer_ids, bank_id,
    )
    print("\nChosen option:")
    print_calc_table_portal([op])

def flow_status(api: MoreRemesas):
    print("Order status lookup")
    partner_id = ask("OrderPartnerID (leave empty to skip)", "")
    order_id = ask("OrderId (leave empty to skip)", "")
    params: Dict[str, Any] = {}
    if partner_id: params["OrderPartnerID"] = partner_id
    if order_id: params["OrderId"] = order_id
    if not params:
        print("Nothing to query."); return
    resp = api.orders_status(**params)
    _ensure_ok(resp, "OrdersStatus")
    print("\nStatus:", resp)

def _collect_sender_bene(source_country_default="CL") -> tuple[dict, dict]:
    s_first = ask("Sender First Name", "JEAN RICHARD")
    s_last  = ask("Sender Last Name", "MERCIDIEU")
    s_gender= ["M","F"][choose("Sender Gender", ["Male(M)", "Female(F)"], 0)]
    s_national = ask("Sender Nationality (ISO-2)", source_country_default)
    s_email = ask("Sender Email", "sender@example.com")
    s_phone = ask("Sender Phone", "957540283")
    s_state = ask("Sender State/Dept", "SANTIAGO")
    s_city  = ask("Sender City", "SANTIAGO")
    s_addr  = ask("Sender Street and Number", "CALLE 5, 123")
    doc_types = ["Passport", "DNI-AR", "CI-CL", "Foreigner", "CPF"]
    dt_idx = choose("Sender Document Type", doc_types, 0)
    s_doc_num = ask("Sender Document Number", "X258881311")
    sender = {
        "FirstName": s_first, "LastName": s_last, "Gender": s_gender,
        "Nationality": s_national, "Email": s_email, "Phone": s_phone,
        "Address": {"State": s_state, "City": s_city, "StreetAndNumber": s_addr},
        "Document": {"Type": "99" if dt_idx == 0 else "561", "Number": s_doc_num, "IssueCountry": s_national},
    }
    b_first = ask("Beneficiary First Name", "STANLEY")
    b_last  = ask("Beneficiary Last Name", "CASTIN")
    b_gender= ["M","F"][choose("Beneficiary Gender", ["Male(M)", "Female(F)"], 0)]
    b_national = ask("Beneficiary Nationality (ISO-2)", "HT")
    b_email = ask("Beneficiary Email", "bene@example.com")
    b_phone = ask("Beneficiary Phone", "50947929400")
    b_state = ask("Beneficiary State/Dept", "PORT AU PRINCE")
    b_city  = ask("Beneficiary City", "PORT AU PRINCE")
    b_addr  = ask("Beneficiary Street and Number", "RUE 1, 123")
    b_doc_idx = choose("Beneficiary Document Type", doc_types, 0)
    b_doc_num = ask("Beneficiary Document Number", "X258881311")
    beneficiary = {
        "FirstName": b_first, "LastName": b_last, "Gender": b_gender,
        "Nationality": b_national, "Email": b_email, "Phone": b_phone,
        "Address": {"State": b_state, "City": b_city, "StreetAndNumber": b_addr},
        "Document": {"Type": "99" if b_doc_idx == 0 else "561", "Number": b_doc_num, "IssueCountry": b_national},
    }
    return sender, beneficiary

def flow_send(api: MoreRemesas):
    source_country = ask("Source Country (ISO-2)", "CL")
    origin_ccy     = ask("Origin Currency (ISO-4217)", "CLP")

    shipment_ui = ["Cash window (Cash)", "Bank", "Wallet"]
    mi = choose("Shipment Type", shipment_ui, 0)
    method_label = ["Cash", "Bank", "Wallet"][mi]

    calc_ui = ["To pay at destination", "Equivalent base", "Commission included"]
    ci = choose("Operation Type", calc_ui, 0)
    calc_type_value = CALC_TYPES[calc_ui[ci]]

    sender, beneficiary = _collect_sender_bene(source_country)
    payout_country = beneficiary["Nationality"]
    log.info("AUTO | Payout Country set from beneficiary => %s", payout_country)

    branches_raw = fetch_branches_all(api, payout_country, method_label, page_size="1000")

    all_ccys = currencies_from_branches(branches_raw)
    if not all_ccys:
        raise MoreError("No payout currencies returned by API.")
    idx_ccy = choose("Payout Currency", all_ccys, 0)
    pay_ccy = all_ccys[idx_ccy]

    if method_label == "Bank":
        branches_all_for_filter = branches_for_method(
            branches_raw, method_label, pay_ccy=pay_ccy, best_per_payer=False
        )
    else:
        branches_all_for_filter = branches_for_method(
            branches_raw, method_label, pay_ccy=pay_ccy, best_per_payer=True
        )

    allowed_branch_ids = {b["BranchId"] for b in branches_all_for_filter if b.get("BranchId")}
    allowed_payer_ids  = {b["PayerId"] for b in branches_all_for_filter if b.get("PayerId")}

    bank_id = None
    bank_name = ""
    bankinfo_extras: Dict[str, Any] = {}
    if method_label == "Bank":
        has_any_bank = any((str(b.get("BankID") or "").strip() not in ("", "0")) for b in branches_all_for_filter)
        if not has_any_bank:
            raise MoreError(f"Bank mode unavailable for {payout_country}/{pay_ccy}. Try Cash or Wallet.")
        bank_id, bank_name = _choose_bank_from_branches(branches_all_for_filter)
        if not bank_id:
            raise MoreError("No bank selected. BankID is required for Bank mode.")
        bankinfo_extras = collect_country_bank_extras(payout_country, bank_name or "")

    limits = consolidate_limits(branches_all_for_filter, pay_ccy)
    print(f"Daily payout limit for {pay_ccy}: {limits['day']:,.2f}")

    if calc_type_value == CALC_TYPES["To pay at destination"]:
        user_amt = ask_money(f"Amount API in {pay_ccy}")
        print(f"\nEntered amount: {user_amt} {pay_ccy} (CalcType={calc_type_value})")
    else:
        user_amt = ask_money(f"Amount API in {BASE_ORDER_CCY}")
        print(f"\nEntered amount: {user_amt} {BASE_ORDER_CCY} (CalcType={calc_type_value})")

    bene_msg = ask("BeneMessage (payment note for beneficiary)", "Gift transaction")
    print(f"  BeneMessage               : {bene_msg}")

    op = select_calc_option(
        api, payout_country, pay_ccy, calc_type_value, user_amt,
        method_label, allowed_branch_ids, allowed_payer_ids, bank_id
    )

    payer_choice_branch = str(op.get("BranchID") or "")
    final_branch: Optional[Dict] = next((it for it in branches_all_for_filter if it["BranchId"] == payer_choice_branch), None)
    if not final_branch:
        ranked = branches_for_method(
            branches_raw, method_label, pay_ccy=pay_ccy,
            want_city=beneficiary["Address"]["City"], want_state=beneficiary["Address"]["State"],
            best_per_payer=True,
        )
        final_branch = ranked[0] if ranked else (branches_all_for_filter[0] if branches_all_for_filter else None)
    if not final_branch:
        raise MoreError("No compatible branch found for the selected CALC option.")

    payout_branch_id = final_branch["BranchId"]
    payer_id_final   = final_branch["PayerId"]
    name_final       = final_branch["Name"]

    if method_label == "Bank":
        city_str = (final_branch.get("CityState") or "").strip()
        city_part, state_part = split_city_state(city_str)
        bankinfo_extras.setdefault("BankBranch", payout_branch_id)
        bankinfo_extras.setdefault("BankCity", city_part or state_part or "")
        bankinfo_extras.setdefault("BankName", bank_name or "")
        bankinfo_extras.setdefault("BankAccType", bankinfo_extras.get("BankAccType", "CC"))  # fallback

    order_ccy  = str(op.get("SendCurrency") or origin_ccy)
    order_amt  = f"{_to_float(op.get('SendAmount') or 0):.2f}"

    rate_id, rate_val = fetch_rate_id_and_value(api, payer_id_final, payout_branch_id, pay_ccy, order_ccy)

    print("\nSUMMARY")
    print(f"  Source Country / Currency : {source_country} / {order_ccy}")
    print(f"  Payout Country            : {payout_country} (from beneficiary)")
    print(f"  Network (API CALC)        : {op.get('Description','')}")
    print(f"  BranchID                  : {payout_branch_id}  ({name_final})")
    print(f"  PayerID                   : {payer_id_final}")
    print(f"  Entered (API)             : {user_amt} {pay_ccy if calc_type_value == CALC_TYPES['To pay at destination'] else BASE_ORDER_CCY}")
    print(f"  Payout (calc)             : {op.get('PaymentAmount','')} {op.get('PaymentCurrency','')}")
    print(f"  Send (calc)               : {order_amt} {order_ccy}")
    print(f"  Note                      : {bene_msg}")

    if not confirm("Proceed to send the money now?"):
        print("Cancelled by user."); return

    source_branch_id = ask("SourceBranchID (your agent code)", "1234") or "1234"

    order_info: Dict[str, Any] = {
        "OrderDate": str(date.today()),
        "SourceCountry": source_country,
        "SourceBranchID": source_branch_id,
        "OrderCurrency": order_ccy,
        "OrderAmount": order_amt,
        "PayoutBranchID": payout_branch_id,
        "Customer": sender,
        "Beneficiary": beneficiary,
        # IMPORTANT: partner ref must be digits only
        "OrderPartnerID": gen_partner_ref_numeric(),
        "PayoutCountry": payout_country,
        "PayoutCurrency": pay_ccy,
        "PayoutAmount": f"{_to_float(op.get('PaymentAmount') or user_amt):.2f}",
        "Relationship": "8",
        "PourposeCode": "1",
        "PayerID": payer_id_final,
        "PayoutMethod": BRANCH_TYPES[method_label],
        "BeneMessage": bene_msg
    }
    if rate_id:
        order_info["OrderRateID"] = rate_id
    if rate_val:
        order_info["ExchangeRate"] = f"{float(rate_val):.6f}"

    # BankInfo payload conforme à la doc
    if method_label == "Bank":
        acct_code = bankinfo_extras.get("BankAccType","CC")
        order_info["BankInfo"] = {
            "BankID": bank_id or "",
            "BankName": bankinfo_extras.get("BankName",""),
            "BankBranch": payout_branch_id,
            "BankCity": beneficiary["Address"]["City"],
            "BankAccType": acct_code,
            "BankAccount": bankinfo_extras.get("BankAccount",""),
            "BankDocument": bankinfo_extras.get("BankDocument",""),
            "CBU": bankinfo_extras.get("CBU",""),
            "RoutingNumber": bankinfo_extras.get("RoutingNumber",""),
            "IFSC": bankinfo_extras.get("IFSC",""),
            "CPF": bankinfo_extras.get("CPF",""),
            "RUT": bankinfo_extras.get("RUT",""),
            "AccountTypeLabel": ACC_TYPE_LABEL.get(acct_code, acct_code),
        }

    if method_label == "Wallet":
        wallet_phone = ask_required("Wallet phone")
        order_info["Wallet"] = {"Phone": wallet_phone}

    try_reserve_and_import(
        api, order_info,
        payout_country=payout_country, pay_ccy=pay_ccy, calc_type_value=calc_type_value,
        method_label=method_label, allowed_branch_ids=allowed_branch_ids, allowed_payer_ids=allowed_payer_ids,
    )

    status = api.orders_status(OrderPartnerID=order_info["OrderPartnerID"])
    _ensure_ok(status, "OrdersStatus (post-import)")
    print("\nStatus:", status)
    print("\nDone.")

def flow_cancel(api: MoreRemesas):
    print(f"cancel order")
    order_id = ask_required("OrderId")
    order_partner_id = ask("OrderPartnerID (leave empty to skip)", "")
    reason = ask("Reason", "CANCELLED_BY_AGENT")
    resp = api.order_cancel(OrderId=order_id, OrderPartnerID=order_partner_id, Reason=reason)
    print(f"response raw: {resp}")
    _ensure_ok(resp, f"OrderCancel")
    print(f"\nCancel response:", resp)

def build_attributes_for_update() -> dict:
    fields = [
        ("BeneFirstName", "Name - Char(32)"),
        ("BeneLastName",  "Surname - Char(32)"),
        ("BeneAddress",   "Address - Char(64)"),
        ("BenePhone",     "Phone - Char(32)"),
    ]
    print("Attributes used to modify:")
    for k, desc in fields:
        print(f"  {k}: {desc}")

    attrs = []
    for k, _ in fields:
        v = ask(f"{k} (leave empty to skip)", "")
        if v.strip():
            attrs.append({"AttributeKey": k, "AttributeValue": v.strip()})

    while True:
        more_key = ask("Add another attribute key? (empty to stop)", "")
        if not more_key.strip():
            break
        more_val = ask_required(f"Value for {more_key.strip()}")
        attrs.append({"AttributeKey": more_key.strip(), "AttributeValue": more_val})

    return {"Attribute": attrs}

def flow_update(api: MoreRemesas):
    print("update order")
    order_id = ask_required("OrderId")
    attrs = build_attributes_for_update()
    if not attrs.get("Attribute"):
        raise MoreError("No attributes provided.")

    resp = api.order_update(
        OrderId=order_id,
        Attributes=attrs,
    )
    print(f"response raw: {resp}")
    _ensure_ok(resp, "OrderUpdate")
    print("\nUpdate response:", resp)

# -------------------- MAIN --------------------
def main():
    print("Remittances")
    sandbox = ask("Use SANDBOX? [y/N]", "y").lower().startswith("y")
    api = MoreRemesas(host=HOST, login_user=LOGIN_USER, login_pass=LOGIN_PASS,
                      sandbox=sandbox, auto_auth=True)
    api._ensure_token()
    log.info("AUTH | Ok | token_prefix=%s exp=%s", api.token[:8], api.token_due)

    while True:
        print("\n=== Main Menu ===")
        action_idx = choose("Pick an action", [
            "Send money",
            "Calculate transfer",
            "Order status",
            "Cancel order",
            "Update order",
            "Exit",
        ], 1)
        if action_idx == 0: flow_send(api)
        elif action_idx == 1: flow_calculate(api)
        elif action_idx == 2: flow_status(api)
        elif action_idx == 3: flow_cancel(api)
        elif action_idx == 4: flow_update(api)
        else:
            print("Bye."); break

if __name__ == "__main__":
    try:
        main()
    except MoreError as e:
        log.error("MoreError: %s", e)
        print(f"SDK error: {e}")
    except Exception as e:
        log.exception("Unexpected exception")
        print(f"Unexpected exception: {e}")
