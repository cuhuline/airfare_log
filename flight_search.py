# flight_search.py
from amadeus import Client, ResponseError
from dotenv import load_dotenv, find_dotenv
from datetime import datetime
from zoneinfo import ZoneInfo
import os, csv
from typing import Any

# .env(로컬) → Actions에선 secrets로 주입됨
load_dotenv(find_dotenv())

CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID")
CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET")
HOSTNAME = os.getenv("AMADEUS_HOSTNAME", "test")     # test | production

# 검색 파라미터(원하면 Actions env에서 바꿔주면 됨)
ORIGIN = os.getenv("ORIGIN", "ICN")
DEST   = os.getenv("DEST", "NRT")
CURRENCY = os.getenv("CURRENCY", "KRW")
AIRLINE  = os.getenv("AIRLINE", "")                  # 특정 항공사만 원하면 예: "7C"
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "5"))     # 저장 개수
DEPARTURE_DATE = os.getenv("DEPARTURE_DATE", "")     # 고정 날짜가 필요하면 YYYY-MM-DD. 빈 값이면 '오늘(서울)'

CSV_PATH = "flight_offers.csv"

if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError("AMADEUS_CLIENT_ID / AMADEUS_CLIENT_SECRET 이 필요합니다.")

amadeus = Client(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, hostname=HOSTNAME)

def ensure_csv(path: str):
    header = [
        "logged_at","search_date","origin","destination",
        "dep_airport","dep_time","arr_airport","arr_time",
        "airline","flight_no","stops","duration",
        "price_total","currency","baggage"
    ]
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

def carrier_name(code: str, dictionaries: dict[str, Any]) -> str:
    return dictionaries.get("carriers", {}).get(code, code)

def parse_baggage(offer: dict[str, Any]) -> str:
    for tp in offer.get("travelerPricings", []):
        for fd in tp.get("fareDetailsBySegment", []):
            inc = (fd.get("includedCheckedBags") or {})
            if "quantity" in inc:
                return f'Checked x{inc["quantity"]}'
            if "weight" in inc and "weightUnit" in inc:
                return f'Checked {inc["weight"]}{inc["weightUnit"]}'
    return ""

def pick_first(offer: dict[str, Any]):
    it = offer["itineraries"][0]
    segs = it["segments"]
    dep = segs[0]["departure"]
    arr = segs[-1]["arrival"]
    return it, segs, dep, arr

def main():
    ensure_csv(CSV_PATH)

    kr_now = datetime.now(ZoneInfo("Asia/Seoul"))
    search_date = DEPARTURE_DATE or kr_now.date().isoformat()  # 오늘 또는 지정일
    params = {
        "originLocationCode": ORIGIN,
        "destinationLocationCode": DEST,
        "departureDate": search_date,
        "adults": 1,
        "currencyCode": CURRENCY,
        "max": MAX_RESULTS
    }
    if AIRLINE:
        params["includedAirlineCodes"] = AIRLINE

    try:
        resp = amadeus.shopping.flight_offers_search.get(**params)
        offers = resp.data
        dic = getattr(resp, "result", {}).get("dictionaries", {})
        if not offers:
            print("검색 결과 없음")
            return

        with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for o in offers:
                it, segs, dep, arr = pick_first(o)
                dep_airport, arr_airport = dep["iataCode"], arr["iataCode"]
                dep_time, arr_time = dep["at"], arr["at"]
                airline = carrier_name(segs[0]["carrierCode"], dic)
                flight_no = f'{segs[0]["carrierCode"]}{segs[0]["number"]}'
                stops = len(segs) - 1
                duration = it.get("duration", "")
                price_total = o["price"]["grandTotal"]
                currency = o["price"]["currency"]
                baggage = parse_baggage(o)

                w.writerow([
                    kr_now.strftime("%Y-%m-%d %H:%M:%S"),
                    search_date, ORIGIN, DEST,
                    dep_airport, dep_time, arr_airport, arr_time,
                    airline, flight_no, stops, duration,
                    price_total, currency, baggage
                ])

        print(f"✅ Saved {len(offers)} to {CSV_PATH} (date={search_date}, {ORIGIN}->{DEST})")

    except ResponseError as e:
        # 디버깅이 필요하면 아래 주석 해제
        # print(e.response.result)
        raise

if __name__ == "__main__":
    main()
