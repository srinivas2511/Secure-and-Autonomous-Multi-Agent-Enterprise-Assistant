---
allowed_roles: [employee, hr, admin]
---
# Data Classification Policy

**Purpose**: Establish consistent standards for handling company and customer data based on its sensitivity, ensuring appropriate protection throughout its lifecycle.

**Classification tiers**:

**Public** — Information approved for external distribution. No restrictions on sharing. Examples: marketing materials, published job postings, press releases.

**Internal** — General business information not intended for public disclosure. Share only with employees and authorized contractors. Examples: internal announcements, project documentation, meeting notes.

**Confidential** — Sensitive business data whose unauthorized disclosure could harm the company or individuals. Requires encryption at rest and in transit. Share only on a need-to-know basis with documented authorization. Examples: employee personal data, customer records, financial forecasts, source code, contracts.

**Restricted** — Highest sensitivity. Access limited to named individuals. Must be encrypted end-to-end. Printing requires manager approval. Examples: M&A information, board materials, security vulnerability details, litigation strategy, executive compensation details.

**Handling requirements by tier**:
| Requirement | Internal | Confidential | Restricted |
|---|---|---|---|
| Encryption in transit | Recommended | Required | Required |
| Encryption at rest | Recommended | Required | Required |
| Access logging | No | Yes | Yes |
| Printing | Allowed | Discouraged | Requires approval |
| External sharing | Internal only | With NDA | Named individuals only |

**Labeling**: Confidential and Restricted documents must be labeled in the header or footer. Templates are available in the document management system.

**Data retention**: Data must not be retained beyond its defined retention period. Retention schedules are maintained by the Legal team and available in the compliance portal.

**Disposal**: Physical documents classified Confidential or Restricted must be shredded. Digital data must be securely deleted using approved tools; simply deleting a file is not sufficient for Restricted data.
