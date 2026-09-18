# EY Token Due Diligence Framework -> shoBITCOIN Risk Rules

**Source:** EY, "Token due diligence: a structured approach to evaluate
digital asset risk" (February 2024). Six risk pillars: Reputational &
Strategic, Technical, Financial, Legal & Compliance, Cybersecurity,
Auditability.

**Important distinction:** EY's paper is principle-based - it explains
*why* each risk matters using real incidents (Compound's COMP over-mint,
the Wormhole bridge exploit, Terra/Luna, Beanstalk's flash-loan attack)
but does not publish machine-readable thresholds or scoring logic.
Every rule below is therefore labeled **"Proposed project rule"** - our
own translation of EY's reasoning into something a script can evaluate -
never presented as EY's own rule. This matches the project's standing
requirement to separate External framework / Project interpretation /
Project rule / Observed blockchain evidence.

Each item is tagged with feasibility:

- **Automatable now** - from data we can already pull via Etherscan
- **Automatable with another free source** - needs an additional free API
  (DefiLlama, CoinGecko, The Graph, Snapshot/Tally)
- **Manual / qualitative** - not derivable from blockchain data at all

---

## 1. Reputational & Strategic - People & Entity Risk

**Question:** Are the core team/founders publicly known and accountable,
or anonymous?

**Evidence:** Public team bios, GitHub commit identity, media coverage,
LinkedIn presence.

**Feasibility:** Manual. Nothing about team identity exists on-chain.

**Proposed project rule:** Not automatable as a Risk Level. Log as a
qualitative research field with a manual checklist ("team identity
known: yes/no/partial") rather than a scored rule. EY itself notes this
correlates with, but doesn't determine, project outcomes - treat as
context, not a hard signal.

---

## 2. Technical

### 2.1 Network Design - Decentralization & Governance

**Question:** How concentrated is control over the protocol/network?

**Evidence:** Governance token holder concentration, validator/staking
distribution, multisig signer count for admin functions.

**Feasibility:** Partial. Governance token holder concentration is
queryable (Etherscan token holder data); full validator-level
decentralization metrics (e.g. Nakamoto Coefficient) are a bigger lift -
defer.

**Proposed project rule:** High concentration of governance-token voting
power in few addresses -> elevated governance risk.

### 2.2 Smart Contract Risk - the core of the current scanner

**Question:** Does the contract have privileged functions that could
harm users (mint, pause, freeze, blacklist, upgrade)?

**Evidence:** Verified source code + ABI (Etherscan `getsourcecode`),
specific function signatures present, whether the contract is a proxy,
who controls the admin/owner role.

**Feasibility:** Fully automatable today - this is exactly the data
`getsourcecode` returns.

**Proposed project rules:**

| Evidence observed | Finding | Risk | Confidence |
| --- | --- | --- | --- |
| Contract source is unverified | Logic cannot be reviewed | High | Low |
| Pause/freeze function exists, controlled by a single EOA | One address can halt transfers unilaterally | Medium-High | High |
| Mint function exists, unrestricted or single-EOA controlled | Supply can be inflated by one party | High | High |
| Contract is an upgradeable proxy, upgrade authority = single EOA | Logic can be changed unilaterally, no warning | High | High |
| Contract is an upgradeable proxy, upgrade authority = timelocked multisig/DAO | Some control exists but isn't eliminated | Medium | Medium |

### 2.3 Maintenance & Upgrades - Governance Transparency

**Question:** Who can upgrade/maintain the code, and how transparent is
that process?

**Evidence:** Timelock contract presence (on-chain, checkable), admin
role ownership (on-chain), governance proposal history (off-chain -
Snapshot/Tally free APIs).

**Proposed project rule:** Upgrade authority behind a timelock -> lower
risk than an upgrade authority with no delay. A time-locked cooling-off
period gives the community a chance to react before a change takes effect.

---

## 3. Financial

### 3.1 Tokenomics

**Question:** How is token supply changing (inflation, burns, unlocks)?

**Evidence:** Mint events (transfers *from* `0x000...000`) and burn
events (transfers *to* `0x000...000`) are observable in the existing
`token_transfers` table. Circulating/max supply can come from CoinGecko's
free tier.

**Proposed project rule:** Net mint volume over a period, as a percentage
of circulating supply, quantifies realized inflation - track as a trend,
not a single pass/fail threshold.

### 3.2 Financial Metrics & Ratios

**Question:** What is TVL, protocol revenue, and does value actually flow
to token holders, liquidity providers, or the treasury?

**Evidence:** DefiLlama free API (TVL, revenue by protocol), CoinGecko
(market cap, FDV).

**Feasibility:** Needs a new integration - not yet in the pipeline.

**Proposed project rule:** EY frames FDV/TVL and MC/R as benchmarking
ratios, not hard thresholds - meaningful only compared against peers,
not evaluated in isolation.

---

## 4. Legal & Compliance - Securities Analysis

**Question:** Does marketing language imply an expectation of profit from
the effort of others (Howey Test)?

**Evidence:** Public statements, marketing materials, sale terms.

**Feasibility:** Manual/qualitative - this is text and legal judgment,
not on-chain state. Application to crypto remains unsettled and
fact-specific.

**Proposed project rule:** Not automatable as a Risk Level. Any future AI
text-summarization output must remain a flagged item for human review,
never an auto-generated legal conclusion. AI explains findings; it never
invents them.

---

## 5. Cybersecurity - Governance & Operational Security

**Question:** What administrative/privileged control exists, and how is
it secured?

**Evidence:** Is the owner/admin address an EOA or a contract such as a
Gnosis Safe multisig? Multisig threshold and timelock presence are
additional checks.

**Feasibility:** Fully automatable - admin address type is checkable via
Etherscan; multisig threshold is readable from the Safe contract's state.

**Proposed project rules:**

| Evidence observed | Finding | Risk |
| --- | --- | --- |
| Admin/owner is an EOA | Single point of failure controls privileged functions | High |
| Admin is a multisig, threshold < 3 signers | Low signer diversity, still concentrated | Medium-High |
| Admin is a multisig, threshold >= 3-of-5 or higher | Broader distributed control | Medium/Low, never zero |
| Privileged actions pass through a timelock | Community gets advance warning before execution | Risk reduced one level versus no-timelock equivalent |

Decentralization and speed of response are a real tradeoff, not a case
where more decentralized is simply less risky in every dimension.

---

## 6. Auditability - Auditability & Ownership

**Question:** Can the contract's logic and data be independently verified?

**Evidence:** Source verification status, presence of issuer powers such as
clawback/blacklist, and existence of a published third-party audit report.

**Feasibility:** Verification status and clawback/blacklist function
presence are automatable now. Audit report existence is manual.

**Proposed project rules:**

| Evidence observed | Finding | Confidence in other findings |
| --- | --- | --- |
| Source unverified | Cannot assess logic at all | Low, flagged explicitly |
| Verified, no audit report found | Some transparency, no third-party validation | Medium |
| Verified, at least one audit from a recognized firm | Higher baseline assurance | Medium-High, never High and never a full guarantee |

---

## What this means for the next build

The pillars that can be turned into real Question -> Evidence -> Rule ->
Finding -> Risk -> Confidence records right now using only Etherscan are:

1. Technical -> Smart Contract Risk (2.2)
2. Cybersecurity -> Governance & Operational Security (5)
3. Auditability -> verification status (6, partial)

Everything else either needs another free API (DefiLlama, CoinGecko,
Snapshot/Tally) or is inherently manual/qualitative and should be logged
as such, not forced into a score.

The `contract_risk_scan.py` script takes any contract address, calls
Etherscan's `getsourcecode`, and produces verification status, proxy
detection, privileged-function flags, admin address type, and a multisig
threshold where available. It then applies the proposed project rules to
produce Finding, Risk Level, and Confidence records.
