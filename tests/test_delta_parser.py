from pathlib import Path
import fitz
from app.parsers import delta
from app.main import score_pairing, sort_pdf_text_for_airline


ROTATION_5354 = """#5354  TU              EFFECTIVE AUG25 ONLY                  CHECK-IN AT 14.15
 DAY   FLIGHT T  DEPARTS   ARRIVES C BLK.  TURN BLK/MAX FDP/MAX PWA FDP/MAX
  A      2047    ATL 1515  ROC 1720  2.05   .55 320 M                         2
                 ROC 1815  ATL 2035  2.20  2.25                               2
         2372    ATL 2300  ROA 0027  1.27       319   10.12/12.00 10.12/11.30 2
          ROA 28.03/HAMPTON INN DTWN              5.52/ 9.00  .00CRD  5.52TL
  C      2818    ROA 0600  ATL 0725  1.25   .58                               2
         2632    ATL 0823  OMA 0942* 2.19           M  5.42/12.00  5.42/11.30 2
          OMA 18.18/HILTON OMAHA                  3.44/ 9.00  .00CRD  3.44TL
  D      1136    OMA 0530  ATL 0845  2.15  1.00                               2
         1444    ATL 0945  IAD 1133  1.48   .57     M                         2
                 IAD 1230  ATL 1420  1.50              8.50/12.00  8.50/11.30 2
                                                  5.53/ 9.00  .00CRD  5.53TL
                                             2.30MCD 2.45TRP  .00DPA  .16ADG
  TOTAL CREDIT 21.00TL  15.29BL    5.31CR   24.44FDP                TAFB  72.35
  TOTAL PAY    21:55TL    .13SIT    .42EDP    .00HOL    .00CARVE
"""

ROTATION_4497 = """#4497  TH              EFFECTIVE AUG27 ONLY                  CHECK-IN AT  6.25
 DAY   FLIGHT T  DEPARTS   ARRIVES C BLK.  TURN BLK/MAX FDP/MAX PWA FDP/MAX
  A      1380    ATL 0725  PIT 0905  1.40   .55 320 M                         2
                 PIT 1000  ATL 1147  1.47  1.23                               2
          360    ATL 1310  DCA 1453* 1.43       319    8.28/12.00  8.28/11.30 2
          DCA 13.42/GAYLORD NATIONAL               5.10/ 9.00  .00CRD  5.10TL
  B      1193    DCA 0605  MSP 0740  2.35  1.25 320 M                         2
         2482    MSP 0905  YVR 1050  3.45          8.45/12.00  8.45/11.30 2
          YVR 17.40/PINNACLE HOTEL                6.20/ 9.00  .00CRD  6.20TL
  C      2875    YVR 0600  MSP 1121  3.21  1.39                               2
          402    MSP 1300  RSW 1723* 3.23       321    9.23/14.00  9.23/13.00 2
          RSW 11.53/LUMINARY HOTEL RSW            6.44/ 9.00  .00CRD  6.44TL
  D      1361    RSW 0646  ATL 0835  1.49            M  2.49/12.00  2.49/11.30 2
                                                  1.49/ 9.00  .11DPM  2.00TL
  TOTAL CREDIT 21.20TL  20.03BL    1.17CR   29.25FDP                TAFB  74.40
  TOTAL PAY    21:20TL    .00SIT    .00EDP    .00HOL    .00CARVE
"""


def test_delta_rotation_5354_preserves_its_own_column_and_pay_data():
    pairing = delta.parse(ROTATION_5354)[0]
    assert pairing["credit"] == "21.00"
    assert pairing["tafb"] == "72.35"
    assert pairing["total_pay"] == "21:55"
    assert pairing["additional_pay"] == "0:55"
    assert pairing["pay_components"] == {"SIT": "0:13", "EDP": "0:42", "HOL": "0:00"}
    assert [layover["city"] for layover in pairing["layovers"]] == ["ROA", "OMA"]

    result = score_pairing(pairing, {
        "elite_cities": ["OMA"],
        "preferred_trip_lengths": ["4"],
        "prefer_operate": False,
    })
    assert result["start_airport"] == "ATL"
    assert result["trip_length"] == 4
    assert result["duty_legs"] == [3, 2, 3]
    assert result["equipment_codes"] == ["320", "319"]
    assert result["cities"] == ["ROA", "OMA"]
    assert "Matches your preferred 4-day trip length" in result["reasons"]
    assert all("5-day" not in reason for reason in result["reasons"])


def test_delta_and_auto_pdf_extraction_preserve_native_column_order():
    assert sort_pdf_text_for_airline("delta") is False
    assert sort_pdf_text_for_airline("auto") is False
    assert sort_pdf_text_for_airline("generic") is True


def test_delta_rotation_4497_uses_its_own_start_length_layovers_and_pay():
    pairing = delta.parse(ROTATION_4497)[0]
    result = score_pairing(pairing, {"preferred_trip_lengths": ["4"], "prefer_operate": False})
    assert result["start_airport"] == "ATL"
    assert result["trip_length"] == 4
    assert result["duty_legs"] == [3, 2, 2, 1]
    assert result["cities"] == ["DCA", "YVR", "RSW"]
    assert result["equipment_codes"] == ["320", "319", "321"]
    assert result["tafb"] == "74.40"
    assert result["trip_credit"] == "21.20"
    assert result["additional_pay"] == "0:00"
    assert result["total_pay"] == "21:20"
    assert "Matches your preferred 4-day trip length" in result["reasons"]


def test_delta_august_package():
    path = Path("/mnt/data/DTW320 AUG 2026.pdf")
    if not path.exists():
        return
    doc = fitz.open(path)
    text = "\n".join(page.get_text("text", sort=True) for page in doc)
    parsed = delta.parse(text)
    ids = {p["id"] for p in parsed}
    assert "4913" in ids
    assert len(parsed) > 200
    assert sum(bool(p["legs"]) for p in parsed) > 150
