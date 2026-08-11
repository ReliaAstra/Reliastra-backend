# ADR-004: Application-layer dependency-header encryption

**Status:** Accepted

Dependency headers can contain vendor credentials. Services encrypt the entire header object with Fernet before repository persistence. A SHA-256 derivation of the runtime secret supplies the MVP key. This limits database-dump exposure. Production key rotation should move to an envelope-encryption KMS adapter without changing repositories or models.
