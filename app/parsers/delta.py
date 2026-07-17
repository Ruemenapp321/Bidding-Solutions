from __future__ import annotations

import hashlib
import os
import re
from typing import Any

from .base import Leg, Layover, Pairing
from app.pay import parse_delta_pay


PAGE_MARKER = re.compile(r"(?m)^<<<CREWBIDIQ_PAGE:(\d+)>>>\s*$")
HEADER = re.compile(r"(?m)^\s*#([A-Z]?\d{3,5})\b")
LEG = re.compile(
    r"^\s*([A-Z])?\s*(DH\s+)?(\d{3,4})?\s+([A-Z]{3})\s+(\d{4})\s+"
    r"([A-Z]{3})\s+(\d{4})\*?\s+(\d\.\d{2})(.*)$"
)
LAYOVER = re.compile(r"(?m)^\s*([A-Z]{3})\s+(\d{1,2}\.\d{2})/([^\n]+?)\s+\d+\.\d{2}/")
CREDIT = re.compile(r"TOTAL CREDIT\s+(\d{1,2}\.\d{2})TL")
TAFB = re.compile(r"TAFB\s+(\d{1,3}\.\d{2})")
CHECKIN = re.compile(r"CHECK-IN AT\s+(\d{1,2}\.\d{2})")
EFFECTIVE = re.compile(r"EFFECTIVE\s+([A-Z0-9,\-\s]+?)(?:CHECK-IN|$)")

EXAMPLE_SIGNALS = re.compile(
    r"\b(?:below is an example|training example|not for bidding|example|sample|illustration|for reference|published in the 350 bid package)\b",
    re.I,
)
INSTRUCTION_SIGNALS = re.compile(r"\b(?:instructions?|how to|four pilot operations|frms|bid guide)\b", re.I)
INVENTORY_HEADING = re.compile(r"\b(?:MASTER\s+PAIRINGS|PAIRING\s+INVENTORY|ROTATION\s+INVENTORY)\b", re.I)
END_SECTION = re.compile(r"\b(?:HOTEL\s+LIST|APPENDIX|TABLE\s+OF\s+CONTENTS|CONTENTS)\b", re.I)
PRODUCTION_COLUMNS = re.compile(r"\bDAY\s+FLIGHT\b.*\bDEPARTS\b.*\bARRIVES\b", re.I)

LAST_DIAGNOSTICS: list[dict[str, Any]] = []


def detect(text: str) -> float:
    score = 0.0
    up = text.upper()
    if "MASTER PAIRINGS" in up:
        score += .35
    if "TOTAL CREDIT" in up and "TAFB" in up:
        score += .25
    if "CHECK-IN AT" in up:
        score += .15
    if len(HEADER.findall(text)) >= 10:
        score += .25
    return min(score, 1.0)


def _pages(text: str) -> list[tuple[int, str]]:
    matches = list(PAGE_MARKER.finditer(text))
    if not matches:
        return [(1, text)]
    return [
        (int(match.group(1)), text[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(text)])
        for index, match in enumerate(matches)
    ]


def _heading(page: str) -> str:
    return next((line.strip() for line in page.splitlines() if line.strip()), "")[:160]


def _classify_page(page: str) -> str:
    up = page.upper()
    heading = _heading(page)
    if re.search(r"\bTABLE OF CONTENTS\b|^\s*CONTENTS\s*$", up, re.M):
        return "CONTENTS"
    if re.search(r"\bHOTEL LIST\b", up):
        return "HOTEL_LIST"
    if re.search(r"\bAPPENDIX\b", up):
        return "APPENDIX"
    if EXAMPLE_SIGNALS.search(page) or re.search(r"\b350 FOUR PILOT OPERATIONS\s*&\s*FRMS\b", heading, re.I):
        return "EXAMPLE"
    if INSTRUCTION_SIGNALS.search(heading):
        return "INSTRUCTIONS"
    if INVENTORY_HEADING.search(page) or (PRODUCTION_COLUMNS.search(page) and len(HEADER.findall(page)) >= 2):
        return "BIDABLE_INVENTORY"
    if re.search(r"\b(?:REFERENCE|GLOSSARY)\b", heading, re.I):
        return "REFERENCE"
    if not HEADER.search(page) and re.search(r"\b(?:DELTA|BID PACKAGE)\b", up):
        return "COVER"
    return "UNKNOWN"


def _package_context(text: str) -> tuple[str | None, str | None]:
    up = text.upper()
    combined = re.search(
        r"\b(ATL|BOS|DTW|JFK|LAX|LGA|MSP|SEA|SLC)\s*[-_/ ]?\s*(?:BASE\s*)?(A?3(?:19|20|21|30|50)|7[3-7][A-Z0-9]*|B\d)\b",
        up,
    )
    if combined:
        return combined.group(1), combined.group(2)
    fleet_match = re.search(r"\b(A?3(?:19|20|21|30|50)|7[3-7][A-Z0-9]*|B\d)\b", up)
    return None, fleet_match.group(1) if fleet_match else None


def _diagnose(rotation: str, page: int, heading: str, classification: str, accepted: bool, reason: str, confidence: float) -> None:
    if os.environ.get("PARSER_DEBUG_ENABLED", "false").lower() != "true":
        return
    LAST_DIAGNOSTICS.append({
        "candidate_rotation": rotation,
        "source_page": page,
        "source_heading": heading,
        "page_classification": classification,
        "result": "ACCEPTED" if accepted else "REJECTED",
        "rejection_reason": None if accepted else reason,
        "confidence": confidence,
    })


def get_diagnostics() -> list[dict[str, Any]]:
    return list(LAST_DIAGNOSTICS)


def parse(text: str) -> list[dict]:
    normalized = text.replace("\r", "\n")
    LAST_DIAGNOSTICS.clear()
    package_base, package_fleet = _package_context(normalized)
    package_id = "delta:" + hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()[:16]
    results: list[dict[str, Any]] = []
    inventory_open = False

    for page_number, page in _pages(normalized):
        classification = _classify_page(page)
        heading = _heading(page)
        if END_SECTION.search(heading) or classification in {"CONTENTS", "INSTRUCTIONS", "REFERENCE", "EXAMPLE", "HOTEL_LIST", "APPENDIX"}:
            inventory_open = False
        if INVENTORY_HEADING.search(page) and classification == "BIDABLE_INVENTORY":
            inventory_open = True

        matches = list(HEADER.finditer(page))
        standalone_production = (
            len(_pages(normalized)) == 1
            and bool(CREDIT.search(page) and TAFB.search(page))
            and (bool(PRODUCTION_COLUMNS.search(page)) or any(LEG.match(line) for line in page.splitlines()))
            and not EXAMPLE_SIGNALS.search(page)
        )
        page_inventory = classification == "BIDABLE_INVENTORY" or (inventory_open and classification == "UNKNOWN") or standalone_production
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(page)
            block = page[match.start():end]
            rotation = match.group(1).upper()
            has_detail_row = any(LEG.match(line) for line in block.splitlines())
            production_layout = bool(
                CREDIT.search(block) and TAFB.search(block)
                and (PRODUCTION_COLUMNS.search(block) or has_detail_row or (INVENTORY_HEADING.search(page) and CHECKIN.search(block)))
            )
            instructional = bool(EXAMPLE_SIGNALS.search(page) or classification in {"EXAMPLE", "INSTRUCTIONS"})
            confidence = .35 + (.3 if production_layout else 0) + (.2 if page_inventory else 0) + (.1 if package_base else 0) + (.05 if package_fleet else 0)
            confidence = min(confidence, 1.0)
            accepted = page_inventory and production_layout and not instructional and confidence >= .75
            reason = "accepted_confirmed_bidable_inventory"
            if instructional and not page_inventory:
                reason = "instructional_example_outside_bidable_inventory"
            elif not page_inventory:
                reason = "outside_bidable_inventory"
            elif instructional:
                reason = "instructional_or_example_language"
            elif not production_layout:
                reason = "rotation_candidate_does_not_match_production_layout"
            elif confidence < .75:
                reason = "insufficient_package_context_confidence"
            _diagnose(rotation, page_number, heading, classification, accepted, reason, confidence)
            if not accepted:
                continue

            legs, current_day = [], None
            for line in block.splitlines():
                leg_match = LEG.match(line)
                if not leg_match:
                    continue
                if leg_match.group(1):
                    current_day = leg_match.group(1)
                rest = leg_match.group(9)
                equipment = re.search(r"\b(3NE|3N1|3NP|321|320|319|75D|73R|73J|221|223)\b", rest)
                legs.append(Leg(
                    day=current_day, deadhead=bool(leg_match.group(2)), flight=leg_match.group(3),
                    departure=leg_match.group(4), departure_time=leg_match.group(5), arrival=leg_match.group(6),
                    arrival_time=leg_match.group(7), block=leg_match.group(8),
                    aircraft=equipment.group(1) if equipment else None,
                ))
            layovers = [Layover(city=x.group(1), duration=x.group(2), hotel=x.group(3).strip()) for x in LAYOVER.finditer(block)]
            credit, tafb, checkin, effective = CREDIT.search(block), TAFB.search(block), CHECKIN.search(block), EFFECTIVE.search(block)
            result = Pairing(
                pairing_id=rotation, raw=block, legs=legs, layovers=layovers,
                credit=credit.group(1) if credit else None, tafb=tafb.group(1) if tafb else None,
                checkin=checkin.group(1) if checkin else None,
                effective=effective.group(1).strip() if effective else None,
                parser="delta_master_pairing", confidence=confidence,
            ).to_dict()
            result.update(parse_delta_pay(block, result["credit"]))
            result.update({
                "airline": "delta", "package_id": package_id, "source_page": page_number,
                "source_pdf_page": page_number, "source_section": heading or "MASTER PAIRINGS",
                "page_classification": "BIDABLE_INVENTORY", "package_base": package_base,
                "package_fleet": package_fleet, "fleet": package_fleet, "rotation_number": rotation,
                "parser_confidence": confidence, "bidable_inventory_confirmed": True,
                "inventory_key": f"{package_id}:{rotation}",
            })
            results.append(result)
    return results
