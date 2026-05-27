# Key Rotation Runbook: Column-Level Encryption

## Overview

All sensitive AI data columns are encrypted at rest using AES-256-GCM.
Each column has an independent data key. Data keys are protected by a
master key, which is encrypted with `age` on disk.

**Key hierarchy:**
```
age identity (private key, ~/.hermes/crypto/identity.txt)
  └── master key (32 bytes, ~/.hermes/crypto/master.key.age)
        ├── copilot_conversations.messages  (data key v1)
        ├── weekly_reports.narrative_text   (data key v1)
        └── user_twin_profiles.embedding_vector (data key v1)
```

**Key material location:** `~/.hermes/crypto/`
- `identity.txt` — age private key (mode 600)
- `master.key.age` — master key encrypted with age
- `data_keys.json` — per-column data keys, encrypted with master key

## Prerequisites

```bash
# Install age CLI
# Ubuntu/Debian:
curl -1sLf 'https://dl.cloudsmith.io/public/flynt/age/setup.deb.sh' | sudo -E bash
sudo apt install age

# macOS:
brew install FiloSottile/age/age

# Verify:
age --version
age-keygen --version
```

## Initial Setup (first deploy)

```bash
# 1. Set the AGE_PASSWORD environment variable (or use identity file)
export AGE_PASSWORD="strong-passphrase-here"

# 2. Generate age identity and master key (done automatically on app startup)
#    Or manually:
cd ~/.hermes/crypto
age-keygen -o identity.txt
# Note the public key from the comment line

# 3. Generate master key
python3 -c "
import os, base64
from data_infrastructure.crypto.keys import MasterKeyManager
mgr = MasterKeyManager()
mgr.ensure_initialized()
print('Master key size:', len(mgr._master_key), 'bytes')
print('Data keys:', list(mgr._data_keys.keys()))
"

# 4. Verify file permissions
ls -la ~/.hermes/crypto/
# identity.txt should be mode 600
# master.key.age should be mode 600
```

## Rotate a Single Column's Data Key

Use this when a specific column's data key may be compromised, or as routine rotation.

**Impact:** Requires re-encrypting all rows in that column with the new key. The old key is discarded.

```bash
# 1. Set environment
export AGE_PASSWORD="strong-passphrase-here"
export CRYPTO_KEYRING_DIR="$HOME/.hermes/crypto"

# 2. Run re-encryption script (see scripts/rotate_column_key.py)
python3 scripts/rotate_column_key.py \
  --column copilot_conversations.messages \
  --db-url postgresql+asyncpg://trading:trading@localhost:5432/trading_db

# 3. Verify:
#    - Check data_keys.json for incremented version
#    - Sample decrypt a few rows
python3 -c "
from data_infrastructure.crypto.keys import MasterKeyManager
mgr = MasterKeyManager()
mgr.ensure_initialized()
for col, info in mgr._data_keys.items():
    print(f'{col}: v{info[\"version\"]} (created {info[\"created_at\"]})')
"
```

## Rotate Master Key

Use this when the master key itself may be compromised, or as annual rotation.

**Impact:** All data keys are re-encrypted with the new master key. Column data keys themselves do NOT change — only their encryption wrapper.

```bash
# 1. Set new password
export AGE_PASSWORD="new-stronger-passphrase"

# 2. Run master rotation
python3 -c "
from data_infrastructure.crypto.keys import MasterKeyManager
mgr = MasterKeyManager()
mgr.ensure_initialized()
mgr.rotate_master_key(new_age_password='new-stronger-passphrase')
print('Master key rotated successfully')
print('Data keys re-encrypted:', len(mgr._data_keys))
"

# 3. Verify decryption works:
python3 -c "
from data_infrastructure.crypto.keys import MasterKeyManager
mgr = MasterKeyManager()
mgr.ensure_initialized()
key = mgr.get_data_key('copilot_conversations.messages')
print('Retrieved data key:', len(key), 'bytes')
"
```

## Recover from Lost Identity

If the age identity file (`identity.txt`) is lost:

1. The master key CANNOT be recovered without the identity
2. All data keys CANNOT be decrypted without the master key
3. All encrypted data is permanently lost

**Mitigation:**
- Store a copy of `identity.txt` in a hardware security module or sealed envelope
- Include `identity.txt` in the same backup process as the database
- Test recovery quarterly

```bash
# Test recovery:
cp ~/.hermes/crypto/identity.txt /tmp/identity_backup.txt
# Simulate loss:
rm ~/.hermes/crypto/identity.txt
# Restore:
cp /tmp/identity_backup.txt ~/.hermes/crypto/identity.txt
# Verify:
python3 -c "
from data_infrastructure.crypto.keys import MasterKeyManager
mgr = MasterKeyManager()
mgr.ensure_initialized()
key = mgr.get_data_key('copilot_conversations.messages')
print('Recovery OK, key length:', len(key))
"
```

## Scheduled Rotation Policy

| Rotation Type | Frequency | Responsible | SLA |
|---|---|---|---|
| Data key (per column) | Every 90 days | On-call engineer | Complete during maintenance window |
| Master key | Every 12 months | Security team | Complete with 2-person sign-off |
| Identity backup | Quarterly | Security team | Verify restore works |

## Emergency Procedures

### Suspected Key Compromise

1. **Identify scope:** Which key is compromised? (data key vs master key)
2. **Rotate immediately:**
   - Data key compromise: `rotate_column_key.py --column <name>`
   - Master key compromise: rotate master + rotate all data keys
3. **Re-encrypt affected data:** Run the re-encryption script for each column
4. **Audit:** Check access logs for the compromised period
5. **Document:** Create an incident report with timeline

### Application Startup Failure (Key Missing)

```bash
# Check if keys exist:
ls -la ~/.hermes/crypto/

# If identity.txt is missing but backed up:
cp /path/to/backup/identity.txt ~/.hermes/crypto/identity.txt
chmod 600 ~/.hermes/crypto/identity.txt

# If master.key.age is missing:
# Generate new master key (data keys will be regenerated for new data)
python3 -c "
from data_infrastructure.crypto.keys import MasterKeyManager
mgr = MasterKeyManager()
mgr.ensure_initialized()
print('Keys initialized')
"
```

## Column Encryption Summary

| Table | Encrypted Column | Storage Type | Max Size | Key ID |
|---|---|---|---|---|
| copilot_conversations | messages → messages_encrypted | TEXT (base64) | ~2x original | copilot_conversations.messages |
| weekly_reports | narrative_text → narrative_text_encrypted | TEXT (base64) | ~2x original | weekly_reports.narrative_text |
| user_twin_profiles | embedding_vector → embedding_vector_encrypted | TEXT (base64) | ~2x original | user_twin_profiles.embedding_vector |

**Note:** Base64 encoding adds ~33% overhead. AES-GCM adds 12 bytes (nonce) + 16 bytes (tag) per encryption operation.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGE_PASSWORD` | Yes | - | Passphrase for age-encrypted master key |
| `CRYPTO_KEYRING_DIR` | No | `~/.hermes/crypto` | Path to key material directory |
