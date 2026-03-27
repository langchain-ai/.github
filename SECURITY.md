# Overview

LangChain values the work of the security community and welcomes submissions of potential security vulnerabilities. Responsible disclosure helps us keep our products, infrastructure, and users safe.

We encourage good-faith security research and ask that you follow the guidelines below when reporting issues.

# Scope

This policy applies to submissions of potential security vulnerabilities related to LangChain-owned or operated digital assets.

## What’s In Scope

- **LangSmith** — [https://smith.langchain.com](https://smith.langchain.com/)
- High-usage LangChain-maintained open-source repositories (approximately **50,000+ downloads per day**), **excluding** non-production repositories like **`langchain-experimental`**. We **accept submissions** for **`langchain-community`**, but **do not offer bounties** due to its community-maintained nature.
- LangChain-owned applications, services, APIs, and infrastructure
- Public-facing LangChain branded websites (i.e. langchain.com, [https://academy.langchain.com](https://academy.langchain.com/), etc.)

Assets not explicitly listed are considered out of scope unless approved by LangChain. If you're unsure whether a repository is in scope, contact security@langchain.dev before extensive testing.

## What’s Out of Scope

### Always out of scope

- Social engineering or phishing
- Physical attacks or data-center access
- Attacks against third-party services
- Issues that only impact LangChain users without a LangChain-controlled vulnerability

### Usually out of scope

*(No bounty or acceptance unless additional, concrete security impact is demonstrated)*

- Automated scanning or indiscriminate fuzzing
- Rate limiting issues
- Password policy or complexity issues
- Error pages, banners, stack traces, or version disclosure
- Common public files (e.g. `robots.txt`, `.well-known`)
- Missing security headers or TLS/SSL best practices without exploitation
- Self-XSS, spam, or tabnabbing
- Open redirects without additional impact
- Issues requiring MITM or access to a user’s device
- Known vulnerable libraries without a working proof of concept
- CSV injection without demonstrated exploitability
- Prompt injection without demonstrated exploitability
- Issues affecting outdated or unsupported browsers
- Unauthorized access to higher-tier paid features

Third-party vulnerabilities are out of scope unless LangChain-specific mitigations are required.

> If you are unsure whether an issue is in scope, please contact Security@langchain.dev before performing extensive testing.
> 

# **How to Report a Vulnerability**

If you believe you’ve found a security issue affecting LangChain, please submit it using the appropriate channel below.

**Public open-source repositories**

For vulnerabilities in LangChain public GitHub repositories, follow the security reporting instructions provided in the relevant repository (for example, via `SECURITY.md` or GitHub Security Advisories and reach out to Security@langchain.dev).

**All other systems**

For vulnerabilities affecting LangChain applications, services, infrastructure, or any non-public systems, email [**security@langchain.dev**](mailto:security@langchain.dev).

## **Reporting Guidelines**

To help us validate and fix issues quickly, please follow these guidelines when submitting a vulnerability report.

We encourage reporters to bundle similar vulnerabilities of the same class (pay out the highest per the class/grouping).   

### **What to include**

Reports should include enough detail for us to **reproduce and assess the issue**. At a minimum, please provide:

- A clear description of the vulnerability
- The affected system, application, or repository
- Steps to reproduce the issue, or a working proof of concept
- An explanation of the security impact.
- Any relevant screenshots, logs, or code snippets (if applicable)

Reports that lack sufficient detail to reproduce the issue may not be accepted or eligible for a bounty.

<aside>
👉🏻

**Accurately assessed severity reports are prioritized for faster triage and response.**

</aside>

### **Proof of Impact**

We prioritize reports that clearly demonstrate **realistic security impact**.

Where possible, show:

- How the issue could be exploited in practice
- What an attacker could gain (e.g., access level, data exposure, privilege escalation)
- Any constraints or prerequisites required for exploitation

Theoretical issues or best-practice gaps without demonstrated impact are generally out of scope.

### Testing Expectations

Please conduct testing responsibly:

- Only test against assets listed as in scope
- Do not access, modify, or delete data that does not belong to you
- Do not intentionally degrade service availability
- Stop testing immediately if you believe your actions could impact other users or production systems

---

### Submission Rules

- Submit **one vulnerability per report**, unless chaining is required to demonstrate impact
- If multiple issues share a single root cause, they may be treated as one finding
- Duplicate submissions are awarded based on the **first reproducible report received**
- Vulnerabilities discovered through automated scanning must include **manual validation and demonstrated impact**
- LangChain **does not accept** AI-generated submissions or reports generated primarily by automated tools

---

### Disclosure Expectations

- **Do not publicly disclose vulnerabilities without LangChain’s explicit written permission**
- Allow reasonable time for us to investigate and remediate reported issues
- Coordinated disclosure may be permitted after remediation at LangChain’s discretion

---

## Response Targets

LangChain makes a best-effort attempt to meet the following timelines:

- Initial response: **within 4 business days**
- Initial triage: **within 15 business days**
- Resolution time: varies based on severity and complexity

Timelines are best-effort and may vary based on report quality, severity, and volume. 

---

## Safe Harbor

Security research conducted **in good faith and in accordance with this policy** is considered authorized.

LangChain will not initiate legal action against researchers who comply with this policy.

If a third party initiates legal action related to compliant research, LangChain will make reasonable efforts to clarify that the activity was authorized.

# Bug Bounty Rewards

Severity is based on what an attacker can realistically achieve, not theoretical or worst-case impact. We evaluate findings based on the level of access gained, data sensitivity, and likelihood of exploitation.

Reports should clearly demonstrate real-world impact. Theoretical issues or best-practice gaps without a demonstrated exploit are generally out of scope.

Final severity and bounty decisions are made by LangChain.

## LangSmith (or other commercial platforms) Reward Scale

| Severity | What This Means | Typical Impact | Example Findings | Reward |
| --- | --- | --- | --- | --- |
| **Low** | Minimal security impact with little attacker value | No customer data access. No production or privileged system access. Limited to individual accounts or non-sensitive assets. | Leaked LangSmith API key scoped to a LangChain employee’s personal org only | **$200** |
| **Moderate** | Real security weakness with constrained scope or impact | No customer data access. Limited internal access or functionality. Impact constrained by permissions or additional requirements. | Access to internal endpoints or metadata without privilege escalation Subdomain takeover in *.langchain.com | **$500** |
| **High** | Meaningful compromise of LangChain systems or infrastructure | Access to production systems or internal services. No confirmed customer data exposure. Clear exploitability. | RCE or environment access exposing only low-sensitivity secrets (e.g. `ANTHROPIC_API_KEY`) | **$1,000+** |
| **Severe / Critical** | Significant compromise of infrastructure, privileged systems, or customer trust | Customer data access, cross-tenant impact, or highly privileged system access | Read/write access to internal repositories or sensitive customer data | **$5,000–$10,000+** |

## Open Source Reward Scale

Severity for open-source vulnerabilities is based on **realistic impact in common deployments**, not theoretical worst-case scenarios.

| Severity | What This Means | Typical Impact | Example Findings | Reward |
| --- | --- | --- | --- | --- |
| **Low / Medium** | Limited or unlikely real-world impact | Requires uncommon configuration or provides minimal attacker value | Best-practice gaps without demonstrated exploitation | **No bounty** |
| **High** | Clear exploit path in typical deployments | Likely to impact real users or expose non-trivial secrets | Exploitable flaw likely leading to RCE or sensitive data exposure | **$500–$2,000** |
| **Severe / Critical** | High likelihood of widespread or serious impact | Reliable path to RCE or sensitive data access across many deployments | Vulnerabilities exposing environment secrets or enabling RCE | **$2,000–$4,000** |

## LangChain Branded Websites

| Severity | What This Means | Typical Impact | Example Findings | Reward |
| --- | --- | --- | --- | --- |
| **Low / Medium** | Limited or unlikely real-world impact | No sensitive data exposure. No meaningful impact to users, systems, or brand trust. | Missing security headers, CSP best-practice gaps, clickjacking on non-interactive pages, generic error messages, open redirects without chaining | **No bounty** |
| **High** | Clear exploit path with real user or brand impact | User-facing exploitation or brand-trust abuse, limited to the website | Reflected or stored XSS on public or authenticated pages, unauthorized access to CMS or content-management functionality, persistent content injection | $150–$300 |
| **Severe / Critical** | Serious compromise of users or brand trust | Widespread user impact or exposure of sensitive non-customer secrets originating from the website | XSS enabling large-scale session hijacking or phishing, exposure of real secrets embedded in frontend assets, website compromise enabling persistent malicious content | Up to $300 |

## Payment Options

Bounties are awarded at LangChain’s discretion based on validated impact and severity. Reward amounts may vary depending on exploitability, report quality, and overall risk.

### Payment Methods

LangChain currently supports the following payment options:

- **Wire transfer** (via Accounts Payable)
- **Goody** (https://www.ongoody.com/plus)

Payment method availability may vary by country. Additional information may be required to comply with legal, tax, or payment regulations.

### Other Security Concerns

For any other security concerns, please contact us at `security@langchain.dev`.
