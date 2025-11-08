#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from datetime import date, datetime, timezone
import logging, random, re, string
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
HOST = "https://www.moresistemas.com:7002"
LOGIN_USER = "WSRSPA"
LOGIN_PASS = "123456"

BRANCH_TYPES = {"Cash": "2", "Bank": "1", "Wallet": "3"}
CALC_TYPES = {"To pay at destination": "1", "Equivalent base": "2", "Commission included": "3"}

BANK_ACCOUNT_TYPES = [
    ("CC",  "Checking account"),
    ("CA",  "Savings account"),
    ("IBAN","IBAN / Other"),
]

# -------------------- HELPERS --------------------
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

def ask_money(prompt: str) -> str:
    while True:
        v = input(f"{prompt}: ").strip()
        vv = v.replace(",", ".")
        try:
            float(vv)
            log.info("INPUT | %s => %s", prompt, vv)
            print(f"Amount confirmed: {vv}")
            return vv
        except ValueError:
            print("  Invalid amount. Example: 1, 5, 300.50")

def confirm(prompt: str) -> bool:
    v = input(f"{prompt} [y/N]: ").strip().lower()
    ok = v in ("y", "yes", "wi", "oui")
    log.info("CONFIRM | %s => %s", prompt, ok)
    return ok

# -------------------- UTIL --------------------
def _as_list(node: Any) -> List[Dict]:
    if not node or node == "":
        return []
    if isinstance(node, list):
        return node
    if isinstance(node, dict):
        return [node]
    return []

def gen_partner_id(prefix="AGENT"):
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    tail = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}-{ts}-{tail}"

def gen_tmp_order_id(prefix="TMP"):
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    tail = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}-{ts}-{tail}"

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

def _to_float(x: Any) -> float:
    if x is None: return 0.0
    if isinstance(x, (int, float)): return float(x)
    s = str(x)
    if "," in s and "." in s:
        if s.find(",") > s.find("."):
            s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    return float(s)

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

# -------------------- API HELPERS --------------------
def fetch_branches_all(api: MoreRemesas, payout_country: str, method_label: str, page_size="1000") -> List[Dict]:
    t = BRANCH_TYPES[method_label]
    all_items: List[Dict] = []
    next_id = "0"
    while True:
        log.info("BRANCHES | Request: Country=%s Type=%s MaxResults=%s NextID=%s",
                 payout_country, t, page_size, next_id)
        resp = api.branches(Country=payout_country, Type=t, MaxResults=page_size, NextID=next_id)
        items = _as_list(resp.get("Branches", {}).get("Branch") or resp.get("Branches", {}).get("BranchItem"))
        for it in items:
            all_items.append({
                "BranchId": str(it.get("BranchId") or it.get("ID") or it.get("Id") or it.get("BranchID") or ""),
                "PayerId": str(it.get("PayerId") or it.get("PayerID") or "0"),
                "Name": it.get("Name") or it.get("BranchName") or "",
                "CityState": it.get("CityState") or it.get("City") or it.get("CityName") or "",
                "Currencies": _as_list((it.get("Currencies") or {}).get("Currency")),
                "BankID": str(it.get("BankID") or "").strip(),
                "BankName": (it.get("BankName") or "").strip(),
            })
        next_id = str(resp.get("NextID") or "0")
        if next_id in ("0", "", None): break
    return [x for x in all_items if x["BranchId"]]

def currencies_from_branches(branches: List[Dict]) -> List[str]:
    codes = set()
    for it in branches:
        for c in it.get("Currencies", []):
            code = c if isinstance(c, str) else (c.get("Currency") or c.get("Code") or "")
            if code: codes.add(code.strip().upper())
    return sorted(codes)

def filter_branches_by_ccy(branches: List[Dict], ccy: str) -> List[Dict]:
    out = []
    for it in branches:
        codes = set()
        for c in it["Currencies"]:
            code = c if isinstance(c, str) else (c.get("Currency") or c.get("Code") or "")
            if code: codes.add(code.strip().upper())
        if ccy.upper() in codes or len(codes) == 0: out.append(it)
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

def build_bank_catalog(branches: List[Dict]) -> List[Dict]:
    catalog: Dict[Tuple[str, str], Dict] = {}
    for it in branches:
        bank_id = it["BankID"]; bank_name = (it["BankName"] or "").strip()
        if not bank_id or bank_id in {"0","00","000","0000"}: continue
        key = (bank_id, bank_name)
        if key not in catalog: catalog[key] = {"BankID": bank_id, "BankName": bank_name, "branches": []}
        catalog[key]["branches"].append(it)
    banks = list(catalog.values())
    banks.sort(key=lambda b: (b["BankName"] or "").upper())
    return banks

def bank_display_name(b: Dict) -> str:
    nm = (b.get("BankName") or "").strip()
    return nm or f"Bank {b.get('BankID','')}"

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

        row = [
            desc,
            rate_s,
            _fmt_money_en(send_amt),
            _fmt_money_en(fees),
            _fmt_money_en(total),
            _fmt_money_en(pay_amt),
        ]
        print(" ".join(f"{cell:<{w}}" for cell, (_, w) in zip(row, cols)))
    print(bar + "\n")

# -------------------- CORE CALC SELECTION --------------------
def _filter_calc_by_method(options: List[Dict], method_label: str, allowed_branch_ids: Optional[set[str]] = None) -> List[Dict]:
    out = []
    for op in options:
        desc = (op.get("Description") or "").upper()
        bid = str(op.get("BranchID") or "")
        if allowed_branch_ids and bid and bid not in allowed_branch_ids: continue
        if method_label == "Wallet":
            if any(k in desc for k in ("DIGICEL", "NATCOM", "WALLET", "MOBILE")): out.append(op)
        elif method_label == "Bank":
            if "DIGICEL" in desc: continue
            out.append(op)
        else:
            out.append(op)
    return out

def select_calc_option(api: MoreRemesas, payout_country: str, pay_ccy: str, calc_type_value: str,
                       user_amt: str, method_label: str, allowed_branch_ids: Optional[set[str]]) -> Dict:
    calc = api.order_calc2(CountryTo=payout_country, PaymentCurrency=pay_ccy, CalcType=calc_type_value, Amount=user_amt)
    options = _as_list((calc.get("Options") or {}).get("Option"))
    if not options and calc_type_value != CALC_TYPES["To pay at destination"]:
        calc = api.order_calc2(CountryTo=payout_country, PaymentCurrency=pay_ccy,
                               CalcType=CALC_TYPES["To pay at destination"], Amount=user_amt)
        options = _as_list((calc.get("Options") or {}).get("Option"))
    if not options:
        raise MoreError(f"CALC failed: {calc}")

    options = _filter_calc_by_method(options, method_label, allowed_branch_ids)
    if not options:
        raise MoreError("No valid CALC option for this method/bank.")

    print_calc_table_portal(options)
    labels = [f"{op.get('Description','')} | receive {op.get('PaymentAmount','')} {op.get('PaymentCurrency','')}" for op in options]
    iop = choose("Pick a network/payer option", labels, 0)
    return options[iop]

def fetch_rate_id(api: MoreRemesas, payer_id: str, branch_id: str, pay_ccy: str, order_ccy: str) -> str:
    try:
        log.info("RATES2 | Request: PayerId=%s BranchID=%s Currency=%s BaseCurrency=%s IncludeDynamicRates=1",
                 payer_id, branch_id, pay_ccy, order_ccy)
        resp = api.rates(PayerId=payer_id, BranchID=branch_id, Currency=pay_ccy,
                         BaseCurrency=order_ccy, IncludeDynamicRates="1")
    except Exception:
        return ""
    rates = _as_list(resp.get("Rates", {}).get("Rate") or resp.get("Rates"))
    for r in rates:
        rid = str(r.get("ID") or r.get("RateID") or "0")
        if rid and rid != "0": return rid
    return ""

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

# -------------------- FLOWS --------------------
def flow_calculate(api: MoreRemesas):
    payout_country = ask("Payout Country (ISO-2)", "HT")
    method_ui = ["Cash window", "Bank", "Wallet"]
    mi = choose("Payout method", method_ui, 0)
    method_label = ["Cash", "Bank", "Wallet"][mi]

    branches_raw = fetch_branches_all(api, payout_country, method_label, "1000")
    all_ccys = currencies_from_branches(branches_raw)
    if not all_ccys: raise MoreError("No payout currencies returned by API for these branches/methods.")
    idx_ccy = choose("Payout Currency (from API)", all_ccys, 0)
    pay_ccy = all_ccys[idx_ccy]
    branches_ccy = filter_branches_by_ccy(branches_raw, pay_ccy)

    allowed_branch_ids: Optional[set[str]] = None
    if method_label == "Bank":
        bank_catalog = build_bank_catalog(branches_ccy)
        names = [bank_display_name(b) for b in bank_catalog] or ["-- NO BANKS --"]
        _ = choose("Bank (from API)", names, 0)
        bank_id = bank_catalog[_]["BankID"] if bank_catalog else None
        if bank_id:
            allowed_branch_ids = {it["BranchId"] for it in branches_ccy if it["BankID"] == bank_id and it["BranchId"]}
    elif method_label == "Wallet":
        like = [it for it in branches_ccy if any(k in (it.get("Name") or "").upper() for k in ("DIGICEL","WALLET","MOBILE"))]
        if like: allowed_branch_ids = {like[0]["BranchId"]}

    calc_ui = ["To pay at destination", "Equivalent base", "Commission included"]
    ci = choose("Operation Type", calc_ui, 0)
    calc_type_value = CALC_TYPES[calc_ui[ci]]

    amt = ask_money("Amount (exact string for API)")
    print(f"\nEntered amount: {amt} {pay_ccy} (CalcType={calc_type_value})")

    op = select_calc_option(api, payout_country, pay_ccy, calc_type_value, amt, method_label, allowed_branch_ids)
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
    if not all_ccys: raise MoreError("No payout currencies returned by API for these branches/methods.")
    idx_ccy = choose("Payout Currency (from API)", all_ccys, 0)
    pay_ccy = all_ccys[idx_ccy]
    branches_ccy = filter_branches_by_ccy(branches_raw, pay_ccy)

    bank_choice_id = None
    bank_account_type_code = None
    bank_account_type_label = None
    bank_account = None
    bank_agency = None
    wallet_phone = None
    wallet_provider_branch: Optional[Dict] = None

    if method_label == "Bank":
        bank_catalog = build_bank_catalog(branches_ccy)
        if not bank_catalog: raise MoreError("No bank available from API for this corridor/currency.")
        names = [bank_display_name(b) for b in bank_catalog]
        default_idx = next((i for i, b in enumerate(bank_catalog) if b["BankID"] == "1150"), 0)
        bi = choose("Bank (from API)", names, default_idx)
        picked_bank = bank_catalog[bi]
        bank_choice_id = picked_bank["BankID"]

        acct_labels = [lbl for _, lbl in BANK_ACCOUNT_TYPES]
        ai = choose("Account Type", acct_labels, 0)
        bank_account_type_code, bank_account_type_label = BANK_ACCOUNT_TYPES[ai]
        bank_account = ask_required("Account (IBAN/CBU/Account number)")
        bank_agency  = ask("Agency/Branch (if required)", "1234")

    elif method_label == "Wallet":
        wallet_phone = ask_required("Wallet phone (full MSISDN)")
        wallet_like = []
        for it in branches_ccy:
            n = (it.get("Name") or "").upper()
            if any(k in n for k in ("DIGICEL", "WALLET", "MOBILE")): wallet_like.append(it)
        if wallet_like:
            b_city = beneficiary["Address"]["City"]; b_state = beneficiary["Address"]["State"]
            wallet_like.sort(key=lambda it: -city_score(split_city_state(it["CityState"])[0],
                                                        split_city_state(it["CityState"])[1], b_city, b_state))
            wallet_provider_branch = wallet_like[0]
        else:
            ranked = best_one_per_payer(branches_ccy, beneficiary["Address"]["City"], beneficiary["Address"]["State"])
            wallet_provider_branch = ranked[0] if ranked else branches_ccy[0]

    allowed_branch_ids: Optional[set[str]] = None
    if method_label == "Bank":
        allowed_branch_ids = {it["BranchId"] for it in branches_ccy if it["BankID"] == bank_choice_id and it["BranchId"]}
    elif method_label == "Wallet" and wallet_provider_branch:
        allowed_branch_ids = {wallet_provider_branch["BranchId"]}

    user_amt = ask_money("Amount (exact string for API)")
    print(f"\nEntered amount: {user_amt} {pay_ccy} (CalcType={calc_type_value})")
    bene_msg = ask("BeneMessage (payment note for beneficiary)", "Gift transaction")
    print(f"  BeneMessage               : {bene_msg}")

    op = select_calc_option(api, payout_country, pay_ccy, calc_type_value, user_amt, method_label, allowed_branch_ids)

    payer_choice_branch = str(op.get("BranchID") or "")
    final_branch: Optional[Dict] = next((it for it in branches_ccy if it["BranchId"] == payer_choice_branch), None)
    if not final_branch:
        payer_id = None; desc = (op.get("Description") or "").lower()
        for it in branches_ccy:
            if (it["Name"] or "").lower().split("/")[0] in desc: payer_id = it["PayerId"]; break
        ranked = [it for it in branches_ccy if (not payer_id or it["PayerId"] == payer_id)]
        if allowed_branch_ids: ranked = [it for it in ranked if it["BranchId"] in allowed_branch_ids]
        final_branch = ranked[0] if ranked else branches_ccy[0]

    payout_branch_id = final_branch["BranchId"]
    payer_id_final   = final_branch["PayerId"]
    name_final       = final_branch["Name"]

    print("\nSUMMARY")
    print(f"  Source Country / Currency : {source_country} / {origin_ccy}")
    print(f"  Payout Country            : {payout_country} (from beneficiary)")
    print(f"  Network (API CALC)        : {op.get('Description','')}")
    print(f"  BranchID                  : {payout_branch_id}  ({name_final})")
    print(f"  PayerID                   : {payer_id_final}")
    print(f"  Entered (API)             : {user_amt} {pay_ccy}")
    print(f"  Payout (calc)             : {op.get('PaymentAmount','')} {op.get('PaymentCurrency','')}")
    print(f"  Send (calc)               : {op.get('SendAmount','')} {op.get('SendCurrency','')}")
    print(f"  Note                      : {bene_msg}")

    if not confirm("Proceed to send the money now?"):
        print("Cancelled by user."); return

    order_ccy  = str(op.get("SendCurrency") or origin_ccy)
    order_amt  = f"{float(op.get('SendAmount') or 0):.2f}"
    rate_id_calc  = str(op.get("RateID") or op.get("OptionID") or "")
    rate_id_rates = fetch_rate_id(api, payer_id_final, payout_branch_id, pay_ccy, order_ccy)
    order_rate_id = rate_id_rates or (rate_id_calc if rate_id_calc and rate_id_calc != "0" else "")

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
        "OrderID": gen_tmp_order_id("TMP"),
        "OrderPartnerID": gen_partner_id("AGENT"),
        "PayoutCountry": payout_country,
        "PayoutCurrency": pay_ccy,
        "PayoutAmount": f"{float(op.get('PaymentAmount') or user_amt):.2f}",
        "Relationship": "2",
        "PourposeCode": "1",
        "PayerID": payer_id_final,
        "PayoutMethod": BRANCH_TYPES["Cash" if method_label not in BRANCH_TYPES else method_label],
        "BeneMessage": bene_msg
    }
    if order_rate_id: order_info["OrderRateID"] = order_rate_id

    if method_label == "Bank":
        order_info["Bank"] = {
            "BankID": bank_choice_id or "",
            "Agency": bank_agency or "",
            "BankAccount": bank_account or "",
            "AccountType": bank_account_type_code or "",
            "BankAccountType": bank_account_type_code or "",
            "AccountTypeLabel": bank_account_type_label or "",
        }
    if method_label == "Wallet":
        order_info["Wallet"] = { "Phone": wallet_phone or "" }

    resv = api.reserve_key(OrderInfo=order_info)
    print("\nReserveKey result:", resv)
    rk = extract_reserve_key(resv)
    if not rk: raise MoreError("Empty ReserveKey: destination requires prior reservation.")

    preview = { **{k: v for k, v in order_info.items() if k not in ("Customer","Beneficiary")},
                "Customer": order_info["Customer"], "Beneficiary": order_info["Beneficiary"] }
    print("\nORDER IMPORT | Payload:", preview)

    imp = api.order_import(ReserveKey=rk, **order_info)
    print("\nImport result:", imp)

    codes = message_codes(imp)
    if "22" in codes: raise MoreError("Agent credit limit exceeded (code 22). Reduce amount or increase ceiling.")

    status = api.orders_status(OrderPartnerID=order_info["OrderPartnerID"])
    print("\nStatus:", status)
    print("\nDone.")

def flow_cancel_or_refund(api: MoreRemesas, mode: str):
    print(f"{mode} order")
    order_id = ask_required("OrderId")
    reason = ask("Reason", "REFUND" if mode == "Refund" else "CANCELLED_BY_AGENT")
    resp = api.order_cancel(OrderId=order_id, Reason=reason)
    print(f"\n{mode} response:", resp)

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
            "Refund order",
            "Exit",
        ], 1)
        if action_idx == 0: flow_send(api)
        elif action_idx == 1: flow_calculate(api)
        elif action_idx == 2: flow_status(api)
        elif action_idx == 3: flow_cancel_or_refund(api, "Cancel")
        elif action_idx == 4: flow_cancel_or_refund(api, "Refund")
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
