# Privacy Policy for Nym Discord Application

**Effective Date:** October 31, 2026

Nym ("the Application", "the Bot") respects the privacy of its users and discord server communities. This Privacy Policy outlines what information is collected, how it is used, and how it is protected.

---

## 1. Information We Collect

Nym collects only minimal, non-sensitive operational data strictly required to provide its features:

- **Guild & Channel Identifiers:** Discord Guild IDs and Channel IDs are stored to persist custom server settings (e.g., custom command prefixes, channel sticky messages, and channel autodelete duration timers).
- **Command Configurations:** Custom prefix strings, sticky message text, and autodelete duration settings chosen by server administrators.
- **Temporary In-Memory Data:** Message IDs and timestamps are processed transiently in memory to execute automated message cleanup (AutoDelete) and sticky message positioning.

**We DO NOT collect or store:**
- User chat logs or message content history.
- Personal identifying information (real names, email addresses, phone numbers).
- Financial or payment details.
- User presence or activity tracking data.

---

## 2. How Information is Used

All collected data is used exclusively to operate and deliver Nym's core functionality:
- Resolving custom server command prefixes (`!`, `,`, or custom prefixes).
- Maintaining persistent sticky notices at the bottom of designated channels.
- Automating message deletion according to administrator-configured timers.
- Verifying administrative permissions for command execution.

We **never** sell, trade, rent, share, or disclose any collected data to third parties or advertising networks.

---

## 3. Data Retention and Storage

- Operational configuration data is stored securely in a private database and encrypted cache.
- If Nym is removed or kicked from a Discord server, server configuration data can be deleted upon request or routine database cleanup.

---

## 4. Message Content & Data Security

- Message contents are inspected strictly **in-memory at the exact time of message receipt** to check for command prefix triggers or autodelete filter rules.
- Message content data is **never** saved to disk or used for training machine learning or AI models.

---

## 5. Contact & Support

If you have questions regarding this Privacy Policy or wish to request data removal, please contact the bot developer via GitHub or Discord support.
