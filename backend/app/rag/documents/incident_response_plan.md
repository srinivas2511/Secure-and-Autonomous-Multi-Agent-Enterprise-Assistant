---
allowed_roles: [hr, admin]
---
# Incident Response Plan

**Purpose**: Define roles, procedures, and communication protocols for responding to information security incidents to minimize impact and restore operations quickly.

**Incident classification**:
- **P1 — Critical**: Active data breach, ransomware, complete service outage, or confirmed unauthorized access to sensitive systems. Response target: 15 minutes.
- **P2 — High**: Suspected breach under investigation, partial service degradation, or malware detected but contained. Response target: 1 hour.
- **P3 — Medium**: Policy violation, phishing attempt (no payload executed), unauthorized software found. Response target: 4 hours.
- **P4 — Low**: Suspicious but unconfirmed activity, minor policy deviation. Response target: next business day.

**Incident Response Team (IRT)**:
- **Incident Commander** — Senior IT or Security lead who owns the response end-to-end
- **Technical Lead** — Engineer responsible for containment, eradication, and recovery
- **Communications Lead** — Coordinates internal and external communications
- **Legal/Compliance** — Engaged immediately for P1/P2; consulted for P3
- **HR** — Engaged when an insider threat is suspected

**Response phases**:
1. **Detect & Report** — Any employee suspecting a security incident must report immediately via security@company.com or the IT helpdesk. Do not attempt to investigate or remediate independently.
2. **Triage** — IRT assesses severity and classifies the incident within the response target window.
3. **Contain** — Isolate affected systems, revoke compromised credentials, block malicious traffic. Preserve evidence before remediation.
4. **Eradicate** — Remove malware, patch exploited vulnerabilities, close unauthorized access paths.
5. **Recover** — Restore from clean backups, verify system integrity, resume operations in a controlled manner.
6. **Post-Incident Review** — Mandatory within 5 business days for P1/P2. Document root cause, timeline, impact, and lessons learned.

**Notification obligations**: Legal must be consulted within 2 hours of confirming a P1 breach involving personal data. Regulatory notification timelines vary by jurisdiction (GDPR: 72 hours; CCPA: expedient notice).

**Evidence preservation**: Do not power off compromised systems without Technical Lead authorization. Disk images and logs must be captured before any remediation step.
