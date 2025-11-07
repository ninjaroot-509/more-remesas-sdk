from __future__ import annotations
from datetime import date, datetime, timezone
import logging, random, re, string
from typing import Any, Dict, List, Tuple, Optional

from moreremesas import MoreRemesas
from moreremesas.exceptions import MoreError


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)sZ | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("more-e2e")


HOST = "..."
LOGIN_USER = "..."
LOGIN_PASS = "..."

BRANCH_TYPES = {"Cash": "2", "Bank": "1", "Wallet": "3"}
CALC_TYPES = {"To pay at destination": "1", "Equivalent base": "2", "Commission included": "3"}


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
        print("  Choix invalide.")

def ask_required(prompt: str) -> str:
    while True:
        v = input(f"{prompt}: ").strip()
        if v:
            log.info("INPUT | %s => %s", prompt, v)
            return v
        print("  Valeur requise.")

def ask_money(prompt: str) -> str:
    while True:
        v = input(f"{prompt}: ").strip()
        vv = v.replace(",", ".")
        try:
            float(vv)
            log.info("INPUT | %s => %s", prompt, vv)
            print(f"Montant confirmé: {vv}")
            return vv
        except ValueError:
            print("  Montant invalide. Ex: 1, 5, 300.50")

def confirm(prompt: str) -> bool:
    v = input(f"{prompt} [y/N]: ").strip().lower()
    ok = v in ("y", "yes", "wi", "oui")
    log.info("CONFIRM | %s => %s", prompt, ok)
    return ok


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
    if norm(cand_city) == norm(want_city) and cand_city:
        score += 2
    elif norm(want_city) and norm(cand_city).startswith(norm(want_city)):
        score += 1
    elif norm(want_city) and norm(want_city) in norm(cand_city):
        score += 1
    if cand_state and want_state and norm(cand_state) == norm(want_state):
        score += 1
    return score


def fetch_branches_once(api: MoreRemesas, payout_country: str, method_label: str, max_results="1000") -> List[Dict]:
    t = BRANCH_TYPES[method_label]
    log.info("BRANCHES | Request: Country=%s Type=%s MaxResults=%s", payout_country, t, max_results)
    resp = api.branches(Country=payout_country, Type=t, MaxResults=max_results)
    items = _as_list(resp.get("Branches", {}).get("Branch") or resp.get("Branches", {}).get("BranchItem"))
    normd = []
    for it in items:
        normd.append({
            "BranchId": str(it.get("BranchId") or it.get("ID") or it.get("Id") or it.get("BranchID") or ""),
            "PayerId": str(it.get("PayerId") or it.get("PayerID") or "0"),
            "Name": it.get("Name") or it.get("BranchName") or "",
            "CityState": it.get("CityState") or it.get("City") or it.get("CityName") or "",
            "Currencies": _as_list((it.get("Currencies") or {}).get("Currency")),
        })
    return [x for x in normd if x["BranchId"]]

def currencies_from_branches(branches: List[Dict]) -> List[str]:
    codes = set()
    for it in branches:
        for c in it.get("Currencies", []):
            code = c if isinstance(c, str) else (c.get("Currency") or c.get("Code") or "")
            if code:
                codes.add(code.strip().upper())
    return sorted(codes)

def filter_branches_by_ccy(branches: List[Dict], ccy: str) -> List[Dict]:
    out = []
    for it in branches:
        codes = set()
        for c in it["Currencies"]:
            code = c if isinstance(c, str) else (c.get("Currency") or c.get("Code") or "")
            if code:
                codes.add(code.strip().upper())
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

def print_calc_options(options: List[Dict]) -> None:
    print("\nOptions CALC (réseaux/pagadores depuis l'API)")
    print("-----+----------+----------+------------------------------------+--------+--------+---------+---------")
    for i, op in enumerate(options, 1):
        oid = str(op.get("OptionID") or op.get("ID") or "")
        print(f"{i:4d} | {oid:<8} | {str(op.get('BranchID','')):<8} | {str(op.get('Description','')):<34} | "
              f"{str(op.get('PaymentCurrency','')):<6} | {str(op.get('PaymentAmount','')):<6} | "
              f"{str(op.get('SendCurrency','')):<7} | {str(op.get('SendAmount','')):<7}")

def select_calc_option(api: MoreRemesas, payout_country: str, pay_ccy: str, calc_type_value: str, user_amt: str) -> Dict:
    calc = api.order_calc2(CountryTo=payout_country, PaymentCurrency=pay_ccy, CalcType=calc_type_value, Amount=user_amt)
    options = _as_list((calc.get("Options") or {}).get("Option"))
    if not options and calc_type_value != CALC_TYPES["To pay at destination"]:
        calc = api.order_calc2(CountryTo=payout_country, PaymentCurrency=pay_ccy,
                               CalcType=CALC_TYPES["To pay at destination"], Amount=user_amt)
        options = _as_list((calc.get("Options") or {}).get("Option"))
    if not options:
        raise MoreError(f"CALC échec: {calc}")
    print_calc_options(options)
    labels = [f"{op.get('Description','')} | pay {op.get('PaymentAmount','')} {op.get('PaymentCurrency','')}" for op in options]
    iop = choose("Choisir un réseau/pagador (Option)", labels, 0)
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
        if rid and rid != "0":
            return rid
    return ""

def extract_reserve_key(resv: dict) -> str:
    attrs = resv.get("Attributes")
    attr_key = ""
    if isinstance(attrs, dict):
        attr_key = attrs.get("ReserveKey") or attrs.get("ReservationKey") or ""
    return (
        resv.get("ReservationKey") or
        resv.get("ReserveKey") or
        resv.get("PaymentKey") or
        resv.get("OrderPayoutKey") or
        attr_key or
        ""
    )

def message_codes(payload: dict) -> set[str]:
    msgs = (payload.get("Messages") or {}).get("Message") or []
    if isinstance(msgs, dict):
        msgs = [msgs]
    return {str(m.get("MessageCode")) for m in msgs if isinstance(m, dict)}


def main():
    print("🧭 Flow Remesas — clean & unique")
    sandbox = ask("Use SANDBOX? [y/N]", "y").lower().startswith("y")
    api = MoreRemesas(host=HOST, login_user=LOGIN_USER, login_pass=LOGIN_PASS,
                      sandbox=sandbox, auto_auth=True)
    api._ensure_token()
    log.info("AUTH | Ok | token_prefix=%s exp=%s", api.token[:8], api.token_due)

    source_country = ask("Source Country (ISO-2)", "CL")
    origin_ccy     = ask("Origin Currency (ISO-4217)", "CLP")

    shipment_ui = ["Cash window (Cash)", "Bank (Bank)", "Wallet (Wallet)"]
    mi = choose("Shipment Type", shipment_ui, 0)
    method_label = ["Cash", "Bank", "Wallet"][mi]

    calc_ui = ["To pay at destination", "Equivalent base", "Commission included"]
    ci = choose("Operation Type", calc_ui, 0)
    calc_type_value = CALC_TYPES[calc_ui[ci]]

    
    s_first = ask("Sender First Name", "JEAN RICHARD")
    s_last  = ask("Sender Last Name", "MERCIDIEU")
    s_gender= ["M","F"][choose("Sender Gender", ["Male(M)", "Female(F)"], 0)]
    s_national = ask("Sender Nationality (ISO-2)", source_country)
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

    payout_country = b_national
    log.info("AUTO | Payout Country set from beneficiary => %s", payout_country)

    branches_raw = fetch_branches_once(api, payout_country, method_label, max_results="1000")
    all_ccys = currencies_from_branches(branches_raw)
    if not all_ccys:
        raise MoreError("Aucune devise de paiement renvoyée par l’API pour ces branches/méthodes.")
    idx_ccy = choose("Payout Currency (from API)", all_ccys, 0)
    pay_ccy = all_ccys[idx_ccy]


    branches_ccy = filter_branches_by_ccy(branches_raw, pay_ccy)
    want_city, want_state = b_city, b_state

    user_amt = ask_money("Amount (exact string for API)")
    print(f"\nMontant saisi: {user_amt} {pay_ccy} (CalcType={calc_type_value})")

    bene_msg = ask("BeneMessage (payment note for beneficiary)", "Gift transaction")
    print(f"  BeneMessage               : {bene_msg}")

    
    op = select_calc_option(api, payout_country, pay_ccy, calc_type_value, user_amt)

    
    payer_choice_branch = str(op.get("BranchID") or "")
    final_branch: Optional[Dict] = next((it for it in branches_ccy if it["BranchId"] == payer_choice_branch), None)
    if not final_branch:
        payer_id = None
        desc = (op.get("Description") or "").lower()
        for it in branches_ccy:
            if (it["Name"] or "").lower().split("/")[0] in desc:
                payer_id = it["PayerId"]
                break
        ranked = [it for it in branches_ccy if not payer_id or it["PayerId"] == payer_id]
        final_branch = ranked[0] if ranked else branches_ccy[0]

    payout_branch_id = final_branch["BranchId"]
    payer_id_final   = final_branch["PayerId"]
    name_final       = final_branch["Name"]

    print("\nRÉCAPITULATIF")
    print(f"  Source Country / Currency : {source_country} / {origin_ccy}")
    print(f"  Payout Country            : {payout_country} (auto depuis bénéficiaire)")
    print(f"  Réseau/Pagador (API CALC) : {op.get('Description','')}")
    print(f"  BranchID                  : {payout_branch_id}  ({name_final})")
    print(f"  PayerID                   : {payer_id_final}")
    print(f"  Montant saisi (API)       : {user_amt} {pay_ccy}")
    print(f"  Payout (calcul)           : {op.get('PaymentAmount','')} {op.get('PaymentCurrency','')}")
    print(f"  Send (calcul)             : {op.get('SendAmount','')} {op.get('SendCurrency','')}")
    print(f"  Motif (BeneMessage)       : {bene_msg}")

    if not confirm("Tu es d’accord pour envoyer l’argent maintenant ?"):
        print("Opération annulée par l’utilisateur.")
        return

    
    order_ccy  = str(op.get("SendCurrency") or origin_ccy)
    order_amt  = f"{float(op.get('SendAmount') or 0):.2f}"
    rate_id_calc  = str(op.get("RateID") or op.get("OptionID") or "")
    rate_id_rates = fetch_rate_id(api, payer_id_final, payout_branch_id, pay_ccy, order_ccy)
    order_rate_id = rate_id_rates or (rate_id_calc if rate_id_calc and rate_id_calc != "0" else "")

    source_branch_id = ask_required("SourceBranchID (your agent code)")

    order_info = {
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
    if order_rate_id:
        order_info["OrderRateID"] = order_rate_id

    
    resv = api.reserve_key(OrderInfo=order_info)
    print("\nReserveKey result:", resv)
    rk = extract_reserve_key(resv)
    if not rk:
        raise MoreError("ReserveKey vide: le destinataire exige une réservation préalable.")

    
    preview = {
        **{k: v for k, v in order_info.items() if k not in ("Customer", "Beneficiary")},
        "Customer": order_info["Customer"],
        "Beneficiary": order_info["Beneficiary"],
    }
    print("\nORDER IMPORT | Payload:", preview)

    imp = api.order_import(ReserveKey=rk, **order_info)
    print("\nImport result:", imp)

    
    codes = message_codes(imp)
    if "22" in codes:
        raise MoreError("Agent credit limit exceeded (code 22). Réduire le montant ou demander une hausse de plafond.")

    
    status = api.orders_status(OrderPartnerID=order_info["OrderPartnerID"])
    print("\nStatus:", status)
    print("\nTerminé.")

if __name__ == "__main__":
    try:
        main()
    except MoreError as e:
        log.error("MoreError: %s", e)
        print(f"SDK error: {e}")
    except Exception as e:
        log.exception("Unexpected exception")
        print(f"Unexpected exception: {e}")
