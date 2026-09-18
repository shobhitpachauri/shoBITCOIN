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

ETHERSCAN_BASE_URL = "https://api.etherscan.io/api"
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
            params={**params, "apikey": api_key},
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
    logger.warning("Could not retrieve source code for %s: %s", address, payload.get("message"))
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


def evaluate_rules(evidence: dict) -> list:
    findings = []
    address = evidence["address"]
    if not evidence["is_verified"]:
        findings.append({"pillar": "Auditability", "question": "Can the contract's logic be independently verified?", "evidence": f"No verified source code found on Etherscan for {address}.", "rule": "Proposed project rule: unverified source means logic cannot be assessed at all.", "finding": "Contract logic cannot be reviewed; all downstream findings for this contract carry Low confidence.", "risk_level": "High", "confidence": "Low", "verification_method": "on-chain deterministic"})
    else:
        findings.append({"pillar": "Auditability", "question": "Can the contract's logic be independently verified?", "evidence": f"Verified source code found for {address} (contract name: {evidence['contract_name']}).", "rule": "Proposed project rule: verified source enables logic review but is not itself an audit.", "finding": "Source is verified. No published third-party audit report was checked automatically.", "risk_level": "Medium", "confidence": "Medium", "verification_method": "on-chain deterministic"})

    if evidence["is_proxy"]:
        findings.append({"pillar": "Technical - Smart Contract Risk", "question": "Is the contract upgradeable, and who controls upgrades?", "evidence": f"Contract is a proxy. Implementation address: {evidence['implementation_address']}.", "rule": "Proposed project rule: upgradeable proxies allow logic changes after deployment; risk depends on who controls the upgrade authority.", "finding": "Contract logic can be changed after deployment via the proxy pattern.", "risk_level": "Medium", "confidence": "High", "verification_method": "on-chain deterministic"})

    if evidence["privileged_functions"]:
        function_list = ", ".join(f"{item['function']} ({item['category']})" for item in evidence["privileged_functions"])
        findings.append({"pillar": "Technical - Smart Contract Risk", "question": "Does the contract have privileged functions that could harm users?", "evidence": f"Privileged functions found in ABI: {function_list}", "rule": "Proposed project rule: presence of privileged functions is a risk factor whose severity depends on who controls them.", "finding": f"{len(evidence['privileged_functions'])} privileged function(s) detected.", "risk_level": "Medium", "confidence": "High", "verification_method": "on-chain deterministic"})
    else:
        findings.append({"pillar": "Technical - Smart Contract Risk", "question": "Does the contract have privileged functions that could harm users?", "evidence": "No function names matched known privileged-function keywords in the available ABI.", "rule": "Proposed project rule: absence of matched keywords reduces but does not eliminate risk.", "finding": "No common privileged function patterns detected by keyword match.", "risk_level": "Low", "confidence": "Medium", "verification_method": "on-chain deterministic"})

    if evidence["admin_address"] is None:
        findings.append({"pillar": "Cybersecurity", "question": "What administrative/privileged control exists over this contract?", "evidence": "Could not determine an admin/owner address via owner() or admin() calls.", "rule": "Proposed project rule: inability to determine admin control is an evidence gap, not evidence of no control.", "finding": "Admin/owner address undetermined by automated check. Data unavailable.", "risk_level": "Unknown", "confidence": "Low", "verification_method": "on-chain deterministic"})
    elif not evidence["admin_is_contract"]:
        findings.append({"pillar": "Cybersecurity", "question": "What administrative/privileged control exists over this contract?", "evidence": f"Admin/owner address {evidence['admin_address']} (via {evidence['admin_source_function']}) is an externally owned account (EOA), not a contract.", "rule": "Proposed project rule: a single EOA controlling privileged functions is a single point of failure.", "finding": "Privileged functions are controlled by a single private key, not a multisig or governance contract.", "risk_level": "High", "confidence": "High", "verification_method": "on-chain deterministic"})
    else:
        threshold = evidence.get("multisig_threshold")
        if threshold:
            risk = "Medium-High" if threshold < 3 else "Medium"
            findings.append({"pillar": "Cybersecurity", "question": "What administrative/privileged control exists over this contract?", "evidence": f"Admin/owner address {evidence['admin_address']} is a contract with a detected multisig threshold of {threshold}.", "rule": "Proposed project rule: multisig threshold below 3 signers has low signer diversity.", "finding": f"Privileged functions require {threshold} signer(s) to approve.", "risk_level": risk, "confidence": "High", "verification_method": "on-chain deterministic"})
        else:
            findings.append({"pillar": "Cybersecurity", "question": "What administrative/privileged control exists over this contract?", "evidence": f"Admin/owner address {evidence['admin_address']} is a contract, but its exact governance structure could not be automatically determined.", "rule": "Proposed project rule: contract-based control is generally an improvement over a single EOA, but the specific structure needs manual confirmation.", "finding": "Admin control is contract-based but its internal governance is undetermined by automated check.", "risk_level": "Medium", "confidence": "Low", "verification_method": "on-chain deterministic"})
    return findings


def save_report(address: str, evidence: dict, findings: list) -> Path:
    RISK_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filepath = RISK_OUTPUT_DIR / f"{address.lower()}_{timestamp}.json"
    filepath.write_text(json.dumps({"scanned_at_utc": timestamp, "address": address, "evidence": evidence, "findings": findings}, indent=2), encoding="utf-8")
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
    filepath = save_report(args.address, evidence, findings)
    save_to_sqlite(args.address, findings)
    logger.info("Scan complete. %s finding(s) generated.", len(findings))
    logger.info("Report saved to: %s", filepath.resolve())
    for finding in findings:
        print(f"[{finding['risk_level']} / confidence: {finding['confidence']}] ({finding['pillar']}) {finding['finding']}")


if __name__ == "__main__":
    main()
