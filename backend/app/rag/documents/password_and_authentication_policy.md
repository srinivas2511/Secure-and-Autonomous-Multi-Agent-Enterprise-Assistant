---
allowed_roles: [employee, hr, admin]
---
# Password and Authentication Policy

**Password requirements**: All passwords for company systems must be at least 14 characters and contain a mix of uppercase letters, lowercase letters, numbers, and symbols. Common words, keyboard patterns (qwerty, 123456), and personal information (name, birthday) are not permitted.

**Multi-factor authentication (MFA)**: MFA is mandatory for all company accounts including email, VPN, cloud services, and the HR portal. Authenticator apps (TOTP) are the preferred second factor. SMS-based MFA is accepted only where authenticator apps are unsupported. Hardware security keys are required for admin-level and privileged accounts.

**Password managers**: The company provides a licensed password manager (details in the IT portal) to all employees. Use of the company password manager is strongly encouraged. Storing passwords in browser auto-fill for work accounts is discouraged on shared or unmanaged devices.

**Password reuse and rotation**: Passwords must not be reused across company systems or between personal and work accounts. Passwords do not expire on a fixed schedule but must be changed immediately upon suspicion of compromise.

**Credential sharing**: Sharing passwords or MFA codes is never permitted, including with IT staff. The IT helpdesk will never ask for a password via email, chat, or phone.

**Service accounts**: Shared or service account credentials must be stored in the company secrets manager, not in code, config files, or chat tools. Access to service accounts requires manager approval and is logged.

**Phishing awareness**: Employees must not enter credentials on any page reached via an email link unless they independently verified the URL. Suspected phishing emails should be forwarded to security@company.com using the "Report Phishing" button in email, not deleted.

**Breached credentials**: If an employee's work credentials are found in a breach (notified by IT or detected via monitoring), the password must be changed within 4 hours and IT must be informed.
