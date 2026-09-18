"""
contract_risk_scan.py

Risk layer of the pipeline. Takes a contract address, pulls its verified
source/ABI from Etherscan, and evaluates it against the project rules
derived from EY's Token Due Diligence framework (see
EY_FRAMEWORK_MAPPING.md). Outputs structured records following the
project's core structure:

    Question -> Evidence -> Rule -> Finding -> Risk Level -> Confidence

This script does NOT invent findings. Every Finding is tied to specific
observed evidence (a function present in the ABI, an admin address type,
a multisig threshold). Where evidence can't be obtained (e.g. an eth_call
reverts, or a value can't be determined), the record says so explicitly
rather than guessing.

Requirements:
    pip install -r requirements.txt   (requests, python-dotenv, pycryptodome)

Usage:
    python scripts/risk/contract_risk_scan.py
    python scripts/risk/contract_risk_scan.py --address 0xSomeOtherContract

Output:
    data/risk/<address>_<timestamp>.json   (full structured report)
    data/staging/shobitcoin.db             (adds contract_risk_findings table)
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from Crypto.Hash import keccak
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"
ETHERSCAN_CHAIN_ID = int(os.environ.get("ETHERSCAN_CHAIN_ID", "1"))
DEFAULT_CONTRACT_ADDRESS = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
STAGING_DB_PATH = PROJECT_ROOT / "data" / "staging" / "shobitcoin.db"
RISK_OUTPUT_DIR = PROJECT_ROOT / "data" / "risk"
REQUEST_DELAY_SECONDS = 0.25

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PRIVILEGED_FUNCTION_KEYWORDS = {
    "mint": "Mint / Supply Inflation",
    "burn": "Burn",
    "pause": "Pause / Freeze",
    "unpause": "Pause / Freeze",
    "freeze": "Pause / Freeze",
    "unfreeze": "Pause / Freeze",
    "blacklist": "Blacklist / Address Restriction",
    "blocklist": "Blacklist / Address Restriction",
    "unblacklist": "Blacklist / Address Restriction",
    "upgradeto": "Upgradeability",
    "transferownership": "Ownership Control",
    "renounceownership": "Ownership Control",
    "setadmin": "Admin Control",
    "changeadmin": "Admin Control",
    "grantrole": "Access Control (Role-Based)",
    "revokerole": "Access Control (Role-Based)",
}


def function_selector(signature: str) -> str:
    digest = keccak.new(digest_bits=256)
    digest.update(signature.encode())
    return "0x" + digest.hexdigest()[:8]


OWNER_SELECTOR = function_selector("owner()")
ADMIN_SELECTOR = function_selector("admin()")
GNOSIS_SAFE_THRESHOLD_SELECTOR = function_selector("getThreshold()")


def get_api_key() -> str:
    api_key = os.environ.get("ETHERSCAN_API_KEY")
    if not api_key:
        logger.error("ETHERSCAN_API_KEY not set. Add it to your .env file.")
        sys.exit(1)
    return api_key


def etherscan_get(params: dict, api_key: str) -> dict:
    try:
        response = requests.get(
            ETHERSCAN_BASE_URL,
            params={**params, "chainid": ETHERSCAN_CHAIN_ID, "apikey": api_key},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as error:
        logger.error("Request failed: %s", error)
        return {}


def get_source_code(address: str, api_key: str) -> dict:
    payload = etherscan_get(
        {"module": "contract", "action": "getsourcecode", "address": address},
        api_key,
    )
    result = payload.get("result")
    if payload.get("status") == "1" and isinstance(result, list) and result:
        return result[0]
    logger.warning(
        "Could not retrieve source code for %s: status=%s message=%s result=%s",
        address,
        payload.get("status"),
        payload.get("message"),
        payload.get("result"),
    )
    return {}


def eth_call(to_address: str, data: str, api_key: str) -> str | None:
    payload = etherscan_get(
        {
            "module": "proxy",
            "action": "eth_call",
            "to": to_address,
            "data": data,
            "tag": "latest",
        },
        api_key,
    )
    result = payload.get("result")
    if isinstance(result, str) and result not in ("0x",):
        return result
    return None


def eth_get_code(address: str, api_key: str) -> str:
    payload = etherscan_get(
        {
            "module": "proxy",
            "action": "eth_getCode",
            "address": address,
            "tag": "latest",
        },
        api_key,
    )
    return payload.get("result", "0x") or "0x"


def decode_address_from_result(hex_result: str) -> str | None:
    if not hex_result or len(hex_result) < 66:
        return None
    return "0x" + hex_result[-40:]


def decode_uint_from_result(hex_result: str) -> int | None:
    if not hex_result:
        return None
    try:
        return int(hex_result, 16)
    except ValueError:
        return None


def gather_evidence(address: str, api_key: str) -> dict:
    evidence = {"address": address}
    source_info = get_source_code(address, api_key)
    evidence["is_verified"] = bool(source_info.get("SourceCode"))
    evidence["contract_name"] = source_info.get("ContractName", "")
    evidence["is_proxy"] = source_info.get("Proxy") == "1"
    evidence["implementation_address"] = source_info.get("Implementation") or None

    abi_source = source_info
    if evidence["is_proxy"] and evidence["implementation_address"]:
        time.sleep(REQUEST_DELAY_SECONDS)
        impl_info = get_source_code(evidence["implementation_address"], api_key)
        if impl_info.get("ABI") and impl_info["ABI"] != "Contract source code not verified":
            abi_source = impl_info
            evidence["implementation_verified"] = bool(impl_info.get("SourceCode"))

    privileged_functions_found = []
    raw_abi = abi_source.get("ABI", "")
    if raw_abi and raw_abi != "Contract source code not verified":
        try:
            abi = json.loads(raw_abi)
            for entry in abi:
                if entry.get("type") != "function":
                    continue
                name = entry.get("name", "")
                for keyword, category in PRIVILEGED_FUNCTION_KEYWORDS.items():
                    if keyword in name.lower():
                        privileged_functions_found.append({"function": name, "category": category})
                        break
        except json.JSONDecodeError:
            logger.warning("Could not parse ABI for %s", address)
    evidence["privileged_functions"] = privileged_functions_found

    time.sleep(REQUEST_DELAY_SECONDS)
    admin_address = None
    admin_source = None
    for label, selector in (("owner()", OWNER_SELECTOR), ("admin()", ADMIN_SELECTOR)):
        result = eth_call(address, selector, api_key)
        if result:
            decoded = decode_address_from_result(result)
            if decoded and decoded != "0x" + "0" * 40:
                admin_address = decoded
                admin_source = label
                break
        time.sleep(REQUEST_DELAY_SECONDS)

    evidence["admin_address"] = admin_address
    evidence["admin_source_function"] = admin_source
    if admin_address:
        time.sleep(REQUEST_DELAY_SECONDS)
        code = eth_get_code(admin_address, api_key)
        evidence["admin_is_contract"] = code not in ("0x", "0x0", "")
        if evidence["admin_is_contract"]:
            time.sleep(REQUEST_DELAY_SECONDS)
            threshold_result = eth_call(admin_address, GNOSIS_SAFE_THRESHOLD_SELECTOR, api_key)
            evidence["multisig_threshold"] = decode_uint_from_result(threshold_result) if threshold_result else None
        else:
            evidence["multisig_threshold"] = None
    else:
        evidence["admin_is_contract"] = None
        evidence["multisig_threshold"] = None
    return evidence


CONTROL_TIER_RISK = {
    "single_eoa": "High",
    "multisig_low": "Medium-High",
    "multisig_higher": "Medium",
    "contract_unknown_governance": "Medium",
    "unknown": "Medium",
}
CONTROL_TIER_CONFIDENCE = {
    "single_eoa": "High",
    "multisig_low": "High",
    "multisig_higher": "High",
    "contract_unknown_governance": "Low",
    "unknown": "Low",
}


def _determine_admin_control_tier(evidence: dict) -> tuple[str, str]:
    if evidence["admin_address"] is None:
        return "unknown", "the admin/owner address could not be automatically determined"
    if not evidence["admin_is_contract"]:
        return "single_eoa", f"controlled by a single externally owned account ({evidence['admin_address']})"
    threshold = evidence.get("multisig_threshold")
    if threshold is None:
        return "contract_unknown_governance", f"controlled by a contract ({evidence['admin_address']}) whose governance structure could not be automatically determined"
    if threshold < 3:
        return "multisig_low", f"controlled by a multisig requiring only {threshold} signer(s)"
    return "multisig_higher", f"controlled by a multisig requiring {threshold} signers"


def evaluate_rules(evidence: dict) -> list:
    findings = []
    address = evidence["address"]
    control_tier, control_description = _determine_admin_control_tier(evidence)
    if not evidence["is_verified"]:
        findings.append({"pillar": "Auditability", "question": "Can the contract's logic be independently verified?", "evidence": f"No verified source code found on Etherscan for {address}.", "rule": "Proposed project rule: unverified source means logic cannot be assessed at all.", "finding": "Contract logic cannot be reviewed; all downstream findings for this contract carry Low confidence.", "risk_level": "High", "confidence": "Low", "verification_method": "on-chain deterministic"})
    else:
        findings.append({"pillar": "Auditability", "question": "Can the contract's logic be independently verified?", "evidence": f"Verified source code found for {address} (contract name: {evidence['contract_name']}).", "rule": "Proposed project rule: verified source enables logic review but is not itself an audit.", "finding": "Source is verified. No published third-party audit report was checked automatically.", "risk_level": "Medium", "confidence": "Medium", "verification_method": "on-chain deterministic"})

    if evidence["is_proxy"]:
        findings.append({"pillar": "Technical - Smart Contract Risk", "question": "Is the contract upgradeable, and who controls upgrades?", "evidence": f"Contract is a proxy. Implementation address: {evidence['implementation_address']}. Upgrade authority is {control_description}.", "rule": "Proposed project rule: upgradeable proxy risk depends on who controls the upgrade authority.", "finding": f"Contract logic can be changed after deployment via the proxy pattern. Upgrade authority is {control_description}.", "risk_level": CONTROL_TIER_RISK[control_tier], "confidence": CONTROL_TIER_CONFIDENCE[control_tier], "verification_method": "on-chain deterministic"})

    if evidence["privileged_functions"]:
        function_list = ", ".join(f"{item['function']} ({item['category']})" for item in evidence["privileged_functions"])
        findings.append({"pillar": "Technical - Smart Contract Risk", "question": "Does the contract have privileged functions that could harm users?", "evidence": f"Privileged functions found in ABI: {function_list}. These functions are {control_description}.", "rule": "Proposed project rule: privileged-function risk is escalated based on who controls them.", "finding": f"{len(evidence['privileged_functions'])} privileged function(s) detected, {control_description}.", "risk_level": CONTROL_TIER_RISK[control_tier], "confidence": CONTROL_TIER_CONFIDENCE[control_tier], "verification_method": "on-chain deterministic"})
    else:
        findings.append({"pillar": "Technical - Smart Contract Risk", "question": "Does the contract have privileged functions that could harm users?", "evidence": "No function names matched known privileged-function keywords in the available ABI.", "rule": "Proposed project rule: absence of matched keywords reduces but does not eliminate risk.", "finding": "No common privileged function patterns detected by keyword match.", "risk_level": "Low", "confidence": "Medium", "verification_method": "on-chain deterministic"})

    if control_tier == "unknown":
        findings.append({"pillar": "Cybersecurity", "question": "What administrative/privileged control exists over this contract?", "evidence": "Could not determine an admin/owner address via owner() or admin() calls.", "rule": "Proposed project rule: inability to determine admin control is an evidence gap, not evidence of no control.", "finding": "Admin/owner address undetermined by automated check. Data unavailable.", "risk_level": "Unknown", "confidence": "Low", "verification_method": "on-chain deterministic"})
    elif control_tier == "single_eoa":
        findings.append({"pillar": "Cybersecurity", "question": "What administrative/privileged control exists over this contract?", "evidence": f"Admin/owner address {evidence['admin_address']} (via {evidence['admin_source_function']}) is an externally owned account (EOA), not a contract.", "rule": "Proposed project rule: a single EOA controlling privileged functions is a single point of failure.", "finding": "Privileged functions are controlled by a single private key, not a multisig or governance contract.", "risk_level": "High", "confidence": "High", "verification_method": "on-chain deterministic"})
    else:
        threshold = evidence.get("multisig_threshold")
        if control_tier in ("multisig_low", "multisig_higher"):
            findings.append({"pillar": "Cybersecurity", "question": "What administrative/privileged control exists over this contract?", "evidence": f"Admin/owner address {evidence['admin_address']} is a contract with a detected multisig threshold of {threshold}.", "rule": "Proposed project rule: multisig threshold below 3 signers has low signer diversity.", "finding": f"Privileged functions require {threshold} signer(s) to approve.", "risk_level": CONTROL_TIER_RISK[control_tier], "confidence": CONTROL_TIER_CONFIDENCE[control_tier], "verification_method": "on-chain deterministic"})
        else:
            findings.append({"pillar": "Cybersecurity", "question": "What administrative/privileged control exists over this contract?", "evidence": f"Admin/owner address {evidence['admin_address']} is a contract, but its exact governance structure could not be automatically determined.", "rule": "Proposed project rule: contract-based control is generally an improvement over a single EOA, but the specific structure needs manual confirmation.", "finding": "Admin control is contract-based but its internal governance is undetermined by automated check.", "risk_level": "Medium", "confidence": "Low", "verification_method": "on-chain deterministic"})
    return findings


SEVERITY_ORDER = {"Low": 1, "Unknown": 2, "Medium": 2, "Medium-High": 3, "High": 4}


def compute_overall_risk(findings: list) -> dict:
    if not findings:
        return {"overall_risk": "Unknown", "driven_by": None, "pillar_breakdown": {}, "has_low_confidence_findings": False}
    pillar_breakdown = {}
    for finding in findings:
        pillar = finding["pillar"]
        current = pillar_breakdown.get(pillar)
        if current is None or SEVERITY_ORDER[finding["risk_level"]] > SEVERITY_ORDER[current["risk_level"]]:
            pillar_breakdown[pillar] = {"risk_level": finding["risk_level"], "finding": finding["finding"]}
    worst_pillar = max(pillar_breakdown.items(), key=lambda item: SEVERITY_ORDER[item[1]["risk_level"]])
    return {
        "overall_risk": worst_pillar[1]["risk_level"],
        "driven_by": worst_pillar[0],
        "pillar_breakdown": {pillar: value["risk_level"] for pillar, value in pillar_breakdown.items()},
        "has_low_confidence_findings": any(finding["confidence"] == "Low" for finding in findings),
    }


def build_report(address: str, evidence: dict, findings: list, scanned_at: str) -> dict:
    return {
        "scanned_at_utc": scanned_at,
        "contract_info": {
            "address": address,
            "contract_name": evidence.get("contract_name") or "Unknown",
            "is_verified": evidence["is_verified"],
            "is_proxy": evidence["is_proxy"],
            "implementation_address": evidence.get("implementation_address"),
        },
        "risk_summary": compute_overall_risk(findings),
        "findings": findings,
        "evidence": evidence,
    }


def save_report(address: str, evidence: dict, findings: list) -> Path:
    RISK_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filepath = RISK_OUTPUT_DIR / f"{address.lower()}_{timestamp}.json"
    filepath.write_text(json.dumps(build_report(address, evidence, findings, timestamp), indent=2), encoding="utf-8")
    return filepath


def save_to_sqlite(address: str, findings: list):
    STAGING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(STAGING_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contract_risk_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, contract_address TEXT, scanned_at TEXT,
            pillar TEXT, question TEXT, evidence TEXT, rule TEXT, finding TEXT,
            risk_level TEXT, confidence TEXT, verification_method TEXT
        )
    """)
    scanned_at = datetime.now(timezone.utc).isoformat()
    rows = [(address, scanned_at, f["pillar"], f["question"], f["evidence"], f["rule"], f["finding"], f["risk_level"], f["confidence"], f.get("verification_method", "unspecified")) for f in findings]
    conn.executemany("""
        INSERT INTO contract_risk_findings
        (contract_address, scanned_at, pillar, question, evidence, rule, finding, risk_level, confidence, verification_method)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Scan a contract for smart-contract and admin-control risk indicators.")
    parser.add_argument("--address", default=DEFAULT_CONTRACT_ADDRESS)
    args = parser.parse_args()
    api_key = get_api_key()
    evidence = gather_evidence(args.address, api_key)
    findings = evaluate_rules(evidence)
    report = build_report(args.address, evidence, findings, datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    filepath = save_report(args.address, evidence, findings)
    save_to_sqlite(args.address, findings)
    logger.info("Scan complete. %s finding(s) generated.", len(findings))
    logger.info("Report saved to: %s", filepath.resolve())
    print("\n=== CONTRACT INFO ===")
    print(json.dumps(report["contract_info"], indent=2))
    print("\n=== RISK SUMMARY ===")
    print(json.dumps(report["risk_summary"], indent=2))
    print("\n=== DETAILED FINDINGS ===")
    for finding in findings:
        print(f"[{finding['risk_level']} / confidence: {finding['confidence']}] ({finding['pillar']}) {finding['finding']}")


if __name__ == "__main__":
    main()
