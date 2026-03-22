# Phase 6: Unified Inbox & File Pipeline

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  ProtonMail     │     │                     │     │  GCP Memory      │
│  (IMAP Bridge)  │────▶│                     │────▶│  Gateway         │
└─────────────────┘     │                     │     └──────────────────┘
                        │                     │                │
┌─────────────────┐     │   omni_sync.py      │                │
│  Gmail          │     │   (Python Daemon)   │                ▼
│  (IMAP)         │────▶│                     │     ┌──────────────────┐
└─────────────────┘     │                     │     │  Notion API      │
                        │   - Email fetch     │     │  (Inbox Track)   │
┌─────────────────┐     │   - File extract    │     └──────────────────┘
│  Google Drive   │     │   - Memory store    │
│  (API)          │────▶│   - Notion update   │
└─────────────────┘     │                     │
                        │                     │
┌─────────────────┐     │                     │
│  MyCloud Home   │     │                     │
│  (SMB Mount)    │────▶│                     │
└─────────────────┘     └─────────────────────┘
```

---

## Configuration

### omni_sync_config.json

```json
{
  "GCP_GATEWAY_URL": "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator",
  
  "NOTION_API_KEY": "secret_xxx",
  "NOTION_INBOX_DB_ID": "your-database-id",
  
  "PROTONMAIL_ENABLED": true,
  "PROTONMAIL_IMAP_HOST": "127.0.0.1",
  "PROTONMAIL_IMAP_PORT": 1143,
  "PROTONMAIL_USER": "your-email@proton.me",
  "PROTONMAIL_PASS": "your-bridge-password",
  
  "GMAIL_ENABLED": true,
  "GMAIL_IMAP_HOST": "imap.gmail.com",
  "GMAIL_IMAP_PORT": 993,
  "GMAIL_USER": "your-email@gmail.com",
  "GMAIL_APP_PASSWORD": "your-app-password",
  
  "GOOGLE_DRIVE_ENABLED": true,
  "GOOGLE_CREDENTIALS_PATH": "~/.gcp/google_drive_credentials.json",
  "GOOGLE_DRIVE_WATCH_FOLDER": "root",
  
  "MYCLOUD_ENABLED": true,
  "MYCLOUD_MOUNT_PATH": "/Volumes/MyCloud Home",
  "MYCLOUD_WATCH_FOLDERS": ["Documents", "Downloads", "Obsidian"],
  
  "EMAIL_POLL_INTERVAL": 60,
  "DRIVE_POLL_INTERVAL": 300,
  "MYCLOUD_POLL_INTERVAL": 300
}
```

---

## Setup Instructions

### 1. ProtonMail Bridge Setup

```bash
# Install ProtonMail Bridge
# Download from https://proton.me/download/bridge

# Start Bridge and login
# Bridge will create IMAP server at localhost:1143

# Get Bridge credentials
# Settings → Bridge → Copy username and password
```

### 2. Gmail App Password

```bash
# Enable 2FA on Google Account
# Go to https://myaccount.google.com/apppasswords
# Create app password for "Mail"
# Use this password in config (not your regular password)
```

### 3. Google Drive API Credentials

```bash
# Go to https://console.cloud.google.com/
# Create new project or select existing
# Enable Drive API
# Create service account
# Download JSON credentials
# Save to ~/.gcp/google_drive_credentials.json
```

### 4. Notion Database Setup

```bash
# Create new database in Notion
# Add properties:
#   - Name (title)
#   - Type (select: Email, File)
#   - Source (rich text)
#   - Summary (rich text)
#   - Processed (date)
#   - Sender (rich text)
#   - Filepath (rich text)

# Get database ID from URL
# Get API token from https://www.notion.so/my-integrations
```

---

## Usage

### Run Once (Test)

```bash
python3 /Users/danexall/omni_sync.py \
  --config /Users/danexall/omni_sync_config.json \
  --once
```

### Run as Daemon

```bash
# Load launchd service
launchctl load ~/Library/LaunchAgents/com.arca.omni-sync.plist

# Check status
launchctl list | grep omni-sync

# Unload
launchctl unload ~/Library/LaunchAgents/com.arca.omni-sync.plist
```

### Monitor Logs

```bash
# Main log
tail -f ~/.arca/omni_sync.log

# Error log
tail -f ~/.arca/omni_sync.err
```

---

## Email Processing

### Supported Formats

| Format | Processing |
|--------|------------|
| Plain text | Direct extraction |
| HTML | Stripped to text |
| Attachments | Skipped (not processed) |

### Memory Format

```markdown
# Email: {subject}

**From:** {sender}
**Date:** {date}
**Source:** {source}

---

{body}
```

### Metadata Stored

```json
{
  "source": "email",
  "email_source": "ProtonMail",
  "sender": "user@example.com",
  "subject": "Email subject",
  "message_id": "<msg-id>",
  "received_at": "2026-03-15T10:00:00Z",
  "processed_at": "2026-03-15T10:05:00Z"
}
```

---

## File Processing

### Supported File Types

| Type | Library | Processing |
|------|---------|------------|
| PDF | PyPDF2 | Text extraction |
| DOCX | python-docx | Text extraction |
| TXT | Built-in | Direct read |
| MD | Built-in | Direct read |

### Memory Format

```markdown
# File: {filename}

**Path:** {filepath}
**Source:** {source}
**Type:** {file_type}

---

{content}
```

### Metadata Stored

```json
{
  "source": "file",
  "file_source": "Google Drive",
  "filename": "document.pdf",
  "filepath": "/path/to/file.pdf",
  "file_type": ".pdf",
  "file_hash": "md5hash",
  "file_size": 12345,
  "processed_at": "2026-03-15T10:05:00Z"
}
```

---

## Notion Integration

### Inbox Entry Format

| Property | Value |
|----------|-------|
| Name | Email subject or filename |
| Type | Email or File |
| Source | ProtonMail, Gmail, Google Drive, MyCloud |
| Summary | Brief description |
| Processed | Timestamp |
| Sender | Email sender (for emails) |
| Filepath | File path (for files) |

---

## State Management

### Processed Items Tracking

State is stored in `~/.arca/omni_sync/`:

- `processed_emails.json` - List of processed email IDs (last 10000)
- `processed_files.json` - Map of filepath → MD5 hash

### Duplicate Prevention

- Emails: Tracked by IMAP message ID
- Files: Tracked by filepath + MD5 hash

---

## Troubleshooting

### ProtonMail Bridge Not Connecting

```bash
# Check if Bridge is running
ps aux | grep ProtonMail

# Restart Bridge
# Open ProtonMail Bridge app
# Settings → Restart Bridge

# Test connection
telnet 127.0.0.1 1143
```

### Gmail IMAP Failing

```bash
# Verify App Password
# Go to https://myaccount.google.com/apppasswords
# Regenerate if needed

# Check IMAP enabled
# Gmail Settings → Forwarding and POP/IMAP → Enable IMAP
```

### Google Drive API Errors

```bash
# Check credentials
ls -la ~/.gcp/google_drive_credentials.json

# Test API
python3 -c "
from google.oauth2 import service_account
creds = service_account.Credentials.from_service_account_file(
    '~/.gcp/google_drive_credentials.json',
    scopes=['https://www.googleapis.com/auth/drive.readonly']
)
print('Credentials valid:', creds.valid)
"
```

### MyCloud Mount Missing

```bash
# Check mount
ls -la /Volumes/MyCloud\ Home

# Mount manually (if needed)
mount_smbfs //user@mycloud-ip/Obsidian /Volumes/MyCloud\ Home
```

---

## Files Created

| File | Purpose |
|------|---------|
| `omni_sync.py` | Main daemon script |
| `omni_sync_requirements.txt` | Python dependencies |
| `omni_sync_config.example.json` | Sample config |
| `com.arca.omni-sync.plist` | launchd service |
| `phase6-setup.sh` | Setup script |

---

## Performance Tuning

### Adjust Poll Intervals

```json
{
  "EMAIL_POLL_INTERVAL": 60,    // Seconds between email checks
  "DRIVE_POLL_INTERVAL": 300,   // Seconds between Drive checks
  "MYCLOUD_POLL_INTERVAL": 300  // Seconds between MyCloud checks
}
```

### Memory Limits

The daemon is designed to be lightweight:
- Memory: ~50MB typical
- CPU: <1% when idle
- Network: Only on sync cycles

---

## Security Notes

- Store credentials in config file (chmod 600)
- Use App Passwords, not main passwords
- State files contain processed IDs (not sensitive)
- Logs may contain email subjects (review before sharing)
