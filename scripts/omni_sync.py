#!/usr/bin/env python3
"""
ARCA Omni-Sync: Master Integration Script
Phase 6.5 Final Activation

Handles:
- Notion database creation and synchronization
- Google Drive file watching (PDFs, Markdown)
- Proton Mail 5-account loop (localhost:1143)
- Gmail integration
- MyCloud storage monitoring
"""

import os
import sys
import json
import time
import logging
import hashlib
import imaplib
import email
import ssl
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
import uuid

# Third-party imports (with graceful handling)
try:
    import requests
except ImportError:
    requests = None

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

# Configuration
CONFIG_PATH = Path.home() / "omni_sync_config.json"
LOG_PATH = Path.home() / ".arca" / "omni_sync.log"
STATE_DIR = Path.home() / ".arca" / "omni_sync"
DB_STATE_FILE = STATE_DIR / "db_state.json"  # Persistence for database IDs

# Circuit Breaker Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB hard limit
IGNORE_KEYWORDS = ['z-lib', 'libgen', 'epub', 'pdf', 'torrent', 'crack', 'warez']
MAX_CONTENT_LENGTH = 100000  # Max characters to extract (prevents token exhaustion)


def setup_logging(dry_run: bool = False):
    """Configure logging to file and console."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_PATH),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration from JSON file."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")

    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)

    # Expand ~ paths
    for key in ['GOOGLE_CREDENTIALS_PATH', 'STATE_DIR', 'LOG_FILE']:
        if key in config and config[key]:
            config[key] = os.path.expanduser(config[key])

    return config


def load_db_state() -> Dict[str, str]:
    """Load existing database IDs from state file (persistence fix)."""
    if not DB_STATE_FILE.exists():
        return {}
    try:
        with open(DB_STATE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_db_state(db_ids: Dict[str, str]) -> bool:
    """Save database IDs to state file for persistence."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(DB_STATE_FILE, 'w') as f:
            json.dump(db_ids, f, indent=2)
        return True
    except IOError as e:
        print(f"Warning: Could not save db_state.json: {e}")
        return False


class NotionClient:
    """Notion API client with graceful 403 error handling."""
    
    def __init__(self, api_key: str, logger: logging.Logger):
        self.api_key = api_key
        self.logger = logger
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
    
    def _handle_response(self, response: requests.Response) -> Optional[Dict]:
        """Handle API response with graceful 403 error handling."""
        if response.status_code == 403:
            self.logger.warning("Notion API returned 403 Forbidden - insufficient permissions")
            return None
        elif response.status_code == 401:
            self.logger.error("Notion API returned 401 Unauthorized - invalid API key")
            return None
        elif response.status_code == 404:
            self.logger.warning("Notion API returned 404 - resource not found")
            return None
        elif response.status_code >= 400:
            self.logger.error(f"Notion API error: {response.status_code} - {response.text}")
            return None
        
        try:
            return response.json()
        except json.JSONDecodeError:
            self.logger.error(f"Failed to parse Notion response: {response.text}")
            return None
    
    def create_database(self, parent_page_id: str, title: str, properties: Dict) -> Optional[str]:
        """Create a new database in Notion. Returns database ID or None on failure."""
        if requests is None:
            self.logger.error("requests library not available")
            return None
        
        url = f"{self.base_url}/databases"
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            result = self._handle_response(response)
            
            if result:
                self.logger.info(f"Created database '{title}' with ID: {result.get('id')}")
                return result.get('id')
            return None
            
        except requests.RequestException as e:
            self.logger.error(f"Notion API request failed: {e}")
            return None
    
    def create_life_os_triage_db(self, parent_page_id: str) -> Optional[str]:
        """Create 'Life OS Triage' database."""
        properties = {
            "Name": {"title": {}},
            "Source": {"rich_text": {}},
            "Summary": {"rich_text": {}},
            "Memory_UUID": {"rich_text": {}},
            "Timestamp": {"date": {}}
        }
        return self.create_database(parent_page_id, "Life OS Triage", properties)
    
    def create_tool_guard_db(self, parent_page_id: str) -> Optional[str]:
        """Create 'Tool Guard' database."""
        properties = {
            "Action": {"title": {}},
            "Target": {"rich_text": {}},
            "Params": {"rich_text": {}},
            "Status": {"select": {"options": [
                {"name": "Pending", "color": "yellow"},
                {"name": "Approved", "color": "green"},
                {"name": "Rejected", "color": "red"},
                {"name": "Executing", "color": "blue"}
            ]}},
            "Approval_Link": {"url": {}}
        }
        return self.create_database(parent_page_id, "Tool Guard", properties)
    
    def append_to_database(self, database_id: str, properties: Dict) -> bool:
        """Append a row to a Notion database."""
        if requests is None:
            return False
        
        url = f"{self.base_url}/pages"
        payload = {
            "parent": {"database_id": database_id},
            "properties": properties
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            result = self._handle_response(response)
            return result is not None
        except requests.RequestException as e:
            self.logger.error(f"Failed to append to database: {e}")
            return False


class GmailClient:
    """Gmail IMAP client for email monitoring."""
    
    def __init__(self, config: Dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.host = config.get('GMAIL_IMAP_HOST', 'imap.gmail.com')
        self.port = config.get('GMAIL_IMAP_PORT', 993)
        self.user = config.get('GMAIL_USER')
        self.password = config.get('GMAIL_APP_PASSWORD')
    
    def connect(self) -> Optional[imaplib.IMAP4_SSL]:
        """Connect to Gmail IMAP server."""
        try:
            mail = imaplib.IMAP4_SSL(self.host, self.port)
            mail.login(self.user, self.password)
            self.logger.info(f"Connected to Gmail: {self.user}")
            return mail
        except imaplib.IMAP4.error as e:
            self.logger.error(f"Gmail connection failed: {e}")
            return None
    
    def fetch_unread(self, mail: imaplib.IMAP4_SSL, limit: int = 10) -> List[Dict]:
        """Fetch unread emails."""
        emails = []
        try:
            mail.select('INBOX')
            status, messages = mail.search(None, 'UNSEEN')
            
            if status != 'OK':
                return emails
            
            msg_ids = messages[0].split()[-limit:]
            
            for msg_id in msg_ids:
                status, msg_data = mail.fetch(msg_id, '(RFC822)')
                if status == 'OK':
                    email_msg = email.message_from_bytes(msg_data[0][1])
                    emails.append({
                        'subject': email_msg.get('Subject', ''),
                        'from': email_msg.get('From', ''),
                        'date': email_msg.get('Date', ''),
                        'body': self._get_email_body(email_msg)
                    })
            
        except imaplib.IMAP4.error as e:
            self.logger.error(f"Failed to fetch emails: {e}")
        
        return emails
    
    def _get_email_body(self, msg: email.message.Message) -> str:
        """Extract email body."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    try:
                        return part.get_payload(decode=True).decode()
                    except:
                        pass
        else:
            try:
                return msg.get_payload(decode=True).decode()
            except:
                pass
        return ""


class ProtonMailClient:
    """Proton Mail client supporting 5-account loop via Bridge (localhost:1143)."""
    
    def __init__(self, config: Dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.host = config.get('PROTONMAIL_IMAP_HOST', '127.0.0.1')
        self.port = config.get('PROTONMAIL_IMAP_PORT', 1143)
        self.accounts = config.get('PROTONMAIL_ACCOUNTS', [])
    
    def loop_through_accounts(self) -> List[Dict]:
        """Loop through all 5 Proton accounts and fetch unread emails."""
        all_emails = []
        
        for account in self.accounts:
            email_addr = account.get('email')
            password = account.get('password')
            
            self.logger.info(f"Checking Proton account: {email_addr}")
            
            try:
                mail = imaplib.IMAP4_SSL(self.host, self.port)
                mail.login(email_addr, password)
                mail.select('INBOX')
                
                status, messages = mail.search(None, 'UNSEEN')
                if status == 'OK':
                    msg_ids = messages[0].split()[-10:]  # Last 10 unread
                    
                    for msg_id in msg_ids:
                        status, msg_data = mail.fetch(msg_id, '(RFC822)')
                        if status == 'OK':
                            email_msg = email.message_from_bytes(msg_data[0][1])
                            all_emails.append({
                                'account': email_addr,
                                'subject': email_msg.get('Subject', ''),
                                'from': email_msg.get('From', ''),
                                'body': self._get_email_body(email_msg)
                            })
                
                mail.logout()
                
            except (imaplib.IMAP4.error, ConnectionRefusedError, OSError, ssl.SSLError) as e:
                self.logger.warning(f"Proton account {email_addr} unavailable (Bridge may not be running): {e}")
            except Exception as e:
                self.logger.error(f"Proton account {email_addr} unexpected error: {e}")
        
        self.logger.info(f"Total emails collected from 5 accounts: {len(all_emails)}")
        return all_emails
    
    def _get_email_body(self, msg: email.message.Message) -> str:
        """Extract email body."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    try:
                        return part.get_payload(decode=True).decode()
                    except:
                        pass
        else:
            try:
                return msg.get_payload(decode=True).decode()
            except:
                pass
        return ""


class GoogleDriveClient:
    """Google Drive client for file watching with circuit breakers."""

    def __init__(self, config: Dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.service_account_path = config.get('GOOGLE_SERVICE_ACCOUNT_PATH')
        self.client_secrets_path = config.get('GOOGLE_CLIENT_SECRETS_PATH')
        self.watch_folder = config.get('GOOGLE_DRIVE_WATCH_FOLDER', 'root')
        self.auth_type = config.get('GOOGLE_AUTH_TYPE', 'service_account')
        self.service = None
        self.gcp_gateway_url = config.get('GCP_GATEWAY_URL')

        if GOOGLE_AVAILABLE:
            self._authenticate()
        else:
            self.logger.warning("Google API libraries not available")

    def _authenticate(self):
        """Authenticate with Google Drive API using service account or OAuth."""
        try:
            if self.auth_type == 'service_account' and self.service_account_path:
                self._authenticate_service_account()
            else:
                self._authenticate_oauth()
        except Exception as e:
            self.logger.warning(f"Google Drive authentication failed: {e}")
            self.logger.warning("Continuing without Google Drive sync")

    def _authenticate_service_account(self):
        """Authenticate using service account credentials."""
        try:
            from google.oauth2 import service_account

            if not os.path.exists(self.service_account_path):
                self.logger.error(f"Service account file not found: {self.service_account_path}")
                return

            # Use the user-interaction-agent service account
            creds = service_account.Credentials.from_service_account_file(
                self.service_account_path,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )

            self.service = build('drive', 'v3', credentials=creds)
            self.logger.info(f"Authenticated with Google Drive (Service Account: {creds.service_account_email})")

        except Exception as e:
            self.logger.warning(f"Service account auth failed: {e}")
            # Fallback to OAuth
            self._authenticate_oauth()

    def _authenticate_oauth(self):
        """Authenticate using OAuth credentials."""
        try:
            if not os.path.exists(self.client_secrets_path):
                self.logger.error(f"OAuth credentials file not found: {self.client_secrets_path}")
                return

            with open(self.client_secrets_path, 'r') as f:
                cred_data = json.load(f)

            # Handle both 'installed' and 'web' app formats
            if 'installed' in cred_data:
                cred_info = cred_data['installed']
            elif 'web' in cred_data:
                cred_info = cred_data['web']
            else:
                cred_info = cred_data

            # Try to use refresh token from existing credentials file
            creds = None
            gdrive_creds_path = os.path.join(os.path.dirname(self.client_secrets_path), 'gdrive_credentials.json')
            if os.path.exists(gdrive_creds_path):
                with open(gdrive_creds_path, 'r') as f:
                    gdrive_data = json.load(f)
                    if gdrive_data.get('refresh_token'):
                        creds = Credentials(
                            token=gdrive_data.get('access_token'),
                            refresh_token=gdrive_data.get('refresh_token'),
                            token_uri=cred_info.get('token_uri', 'https://oauth2.googleapis.com/token'),
                            client_id=cred_info.get('client_id'),
                            client_secret=cred_info.get('client_secret'),
                            scopes=['https://www.googleapis.com/auth/drive.readonly']
                        )

            if creds:
                self.service = build('drive', 'v3', credentials=creds)
                self.logger.info("Authenticated with Google Drive (OAuth with refresh token)")
            else:
                self.logger.warning("OAuth credentials found but no refresh token available")

        except Exception as e:
            self.logger.warning(f"OAuth auth failed: {e}")

    def _should_skip_file(self, file_meta: Dict) -> tuple:
        """
        Circuit breaker: Check if file should be skipped or metadata-only.
        Returns: (should_skip, reason, is_metadata_only)
        """
        file_name = file_meta.get('name', '').lower()
        file_size = file_meta.get('size', 0)
        mime_type = file_meta.get('mimeType', '')

        # Convert size to int (Google API returns size as string)
        try:
            file_size = int(file_size) if file_size else 0
        except (ValueError, TypeError):
            file_size = 0

        # Check 1: Size limit (10MB hard cap)
        if file_size > MAX_FILE_SIZE:
            return (False, f"Size {file_size} exceeds {MAX_FILE_SIZE}", True)

        # Check 2: Keyword blacklist
        for keyword in IGNORE_KEYWORDS:
            if keyword.lower() in file_name:
                self.logger.info(f"CIRCUIT BREAKER: Keyword '{keyword}' found in '{file_meta.get('name')}'")
                return (False, f"Keyword blacklist: {keyword}", True)

        # Check 3: Native Google Docs - always process with export
        if mime_type in [
            'application/vnd.google-apps.document',
            'application/vnd.google-apps.spreadsheet',
            'application/vnd.google-apps.presentation'
        ]:
            return (False, "Native Google Doc - will export", False)

        return (False, "OK", False)

    def _export_google_doc(self, file_id: str, mime_type: str) -> Optional[str]:
        """Export Google Docs/Sheets/Slides as plain text."""
        if not self.service:
            return None

        try:
            # Map Google MIME types to export formats
            export_map = {
                'application/vnd.google-apps.document': 'text/plain',
                'application/vnd.google-apps.spreadsheet': 'text/csv',
                'application/vnd.google-apps.presentation': 'text/plain'
            }

            export_mime = export_map.get(mime_type, 'text/plain')

            request = self.service.files().export_media(
                fileId=file_id,
                mimeType=export_mime
            )

            content = request.execute()
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='ignore')

            # Truncate if too large
            if len(content) > MAX_CONTENT_LENGTH:
                self.logger.warning(f"Content truncated from {len(content)} to {MAX_CONTENT_LENGTH} chars")
                content = content[:MAX_CONTENT_LENGTH] + "\n\n[TRUNCATED - Content exceeded token limit]"

            return content

        except HttpError as e:
            if e.resp.status == 403:
                self.logger.error(f"Google Docs export 403 - permission denied for file {file_id}")
            else:
                self.logger.error(f"Google Docs export error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error exporting Google Doc: {e}")
            return None

    def _download_file_content(self, file_meta: Dict) -> Optional[str]:
        """Download file content with size checks."""
        if not self.service:
            return None

        file_id = file_meta.get('id')
        file_name = file_meta.get('name', 'unknown')
        mime_type = file_meta.get('mimeType', '')

        # Handle Google Docs via export
        if mime_type.startswith('application/vnd.google-apps'):
            return self._export_google_doc(file_id, mime_type)

        try:
            # Get file with size info
            file_info = self.service.files().get(
                fileId=file_id,
                fields='id,name,mimeType,size,webViewLink'
            ).execute()

            file_size = file_info.get('size', 0)

            # Convert size to int (Google API returns size as string)
            try:
                file_size = int(file_size) if file_size else 0
            except (ValueError, TypeError):
                file_size = 0

            # Double-check size before download
            if file_size > MAX_FILE_SIZE:
                self.logger.warning(f"Skipping download of {file_name}: size {file_size} exceeds limit")
                return None

            # Download file using execute_media()
            import io
            from googleapiclient.http import MediaIoBaseDownload

            request = self.service.files().get_media(fileId=file_id)
            file_buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(file_buffer, request)

            done = False
            while done is False:
                status, done = downloader.next_chunk()

            content = file_buffer.getvalue()

            # Try to decode as text
            try:
                text_content = content.decode('utf-8', errors='ignore')
            except:
                text_content = content.decode('latin-1', errors='ignore')

            # Truncate if too large
            if len(text_content) > MAX_CONTENT_LENGTH:
                self.logger.warning(f"Content truncated from {len(text_content)} to {MAX_CONTENT_LENGTH} chars")
                text_content = text_content[:MAX_CONTENT_LENGTH] + "\n\n[TRUNCATED - Content exceeded token limit]"

            return text_content

        except HttpError as e:
            if e.resp.status == 403:
                self.logger.error(f"Download 403 - permission denied for {file_name}")
            else:
                self.logger.error(f"Download error for {file_name}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error downloading {file_name}: {e}")
            return None

    def _send_metadata_to_gateway(self, file_meta: Dict, reason: str) -> bool:
        """Send metadata-only record to GCP Gateway."""
        if not self.gcp_gateway_url:
            self.logger.info(f"Metadata-only (no gateway): {file_meta.get('name')} - {reason}")
            return True

        try:
            payload = {
                'type': 'metadata_only',
                'reason': reason,
                'file': {
                    'id': file_meta.get('id'),
                    'name': file_meta.get('name'),
                    'mimeType': file_meta.get('mimeType'),
                    'size': file_meta.get('size'),
                    'webViewLink': file_meta.get('webViewLink'),
                    'createdTime': file_meta.get('createdTime'),
                },
                'identity': self.config.get('IDENTITY', {}),
                'timestamp': datetime.now().isoformat()
            }

            if requests is None:
                self.logger.warning("requests not available - cannot send to gateway")
                return False

            response = requests.post(
                self.gcp_gateway_url,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                self.logger.info(f"Metadata sent to gateway: {file_meta.get('name')}")
                return True
            else:
                self.logger.warning(f"Gateway rejected metadata: {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to send metadata to gateway: {e}")
            return False

    def watch_for_files(self, file_types: List[str] = ['.pdf', '.md']) -> List[Dict]:
        """
        Watch for files with circuit breaker protection.
        Returns list of processed file records.
        """
        if not self.service:
            return []

        processed_files = []

        try:
            # Build query: PDFs by mimeType, Markdown by extension
            query_parts = []
            for ext in file_types:
                if ext == '.pdf':
                    query_parts.append("mimeType='application/pdf'")
                elif ext == '.md':
                    query_parts.append("name contains '.md'")
                else:
                    query_parts.append(f"name contains '{ext}'")

            # Also include Google Docs
            query_parts.append("mimeType='application/vnd.google-apps.document'")
            query_parts.append("mimeType='application/vnd.google-apps.spreadsheet'")

            query = " or ".join(query_parts)

            results = self.service.files().list(
                q=query,
                pageSize=50,
                fields="files(id, name, mimeType, size, createdTime, webViewLink)"
            ).execute()

            files = results.get('files', [])
            self.logger.info(f"Found {len(files)} matching files in Google Drive")

            for file_meta in files:
                file_name = file_meta.get('name', 'unknown')

                # CIRCUIT BREAKER: Evaluate file before processing
                should_skip, reason, is_metadata_only = self._should_skip_file(file_meta)

                if should_skip:
                    self.logger.info(f"SKIPPED: {file_name} - {reason}")
                    continue

                if is_metadata_only:
                    # Send metadata only to gateway (no content extraction)
                    self._send_metadata_to_gateway(file_meta, reason)
                    processed_files.append({
                        'id': file_meta.get('id'),
                        'name': file_name,
                        'mimeType': file_meta.get('mimeType'),
                        'size': file_meta.get('size'),
                        'webViewLink': file_meta.get('webViewLink'),
                        'status': 'metadata_only',
                        'skip_reason': reason
                    })
                    self.logger.info(f"METADATA-ONLY: {file_name} - {reason}")
                    continue

                # Full processing: download and extract content
                self.logger.info(f"PROCESSING: {file_name}")
                content = self._download_file_content(file_meta)

                if content:
                    processed_files.append({
                        'id': file_meta.get('id'),
                        'name': file_name,
                        'mimeType': file_meta.get('mimeType'),
                        'size': file_meta.get('size'),
                        'webViewLink': file_meta.get('webViewLink'),
                        'status': 'full_content',
                        'content': content,
                        'content_length': len(content)
                    })
                    self.logger.info(f"EXTRACTED: {file_name} ({len(content)} chars)")
                else:
                    processed_files.append({
                        'id': file_meta.get('id'),
                        'name': file_name,
                        'mimeType': file_meta.get('mimeType'),
                        'status': 'download_failed'
                    })

        except HttpError as e:
            if e.resp.status == 403:
                self.logger.error("Google Drive API 403 - quota exceeded or permission denied")
            else:
                self.logger.error(f"Google Drive API error: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error watching Drive files: {e}")

        return processed_files


class OmniSync:
    """Main OmniSync orchestrator."""

    def __init__(self, config: Dict, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.logger = setup_logging(dry_run)

        self.notion = NotionClient(
            config.get('NOTION_API_KEY', ''),
            self.logger
        )

        self.gmail = GmailClient(config, self.logger) if config.get('GMAIL_ENABLED') else None
        self.proton = ProtonMailClient(config, self.logger) if config.get('PROTONMAIL_ENABLED') else None
        self.gdrive = GoogleDriveClient(config, self.logger) if config.get('GOOGLE_DRIVE_ENABLED') else None

        self.identity = config.get('IDENTITY', {})

        self.logger.info(f"OmniSync initialized (Dry Run: {dry_run})")
        self.logger.info(f"Identity: {self.identity.get('IDENTITY_NAME')} <{self.identity.get('PRIMARY_EMAIL')}>")
        self.logger.info(f"Circuit Breakers: MAX_FILE_SIZE={MAX_FILE_SIZE}, IGNORE_KEYWORDS={IGNORE_KEYWORDS}")
    
    def create_notion_databases(self) -> Dict[str, Optional[str]]:
        """Create Life OS Triage and Tool Guard databases with persistence fix."""
        parent_page_id = self.config.get('NOTION_PAGE_ID')

        if not parent_page_id:
            self.logger.error("NOTION_PAGE_ID not configured")
            return {}

        self.logger.info(f"Creating databases in Notion page: {parent_page_id}")

        # PERSISTENCE FIX: Check for existing database IDs first
        existing_state = load_db_state()
        if existing_state:
            self.logger.info(f"Found existing database IDs in {DB_STATE_FILE}")
            self.logger.info(f"  Life OS Triage: {existing_state.get('life_os_triage', 'N/A')}")
            self.logger.info(f"  Tool Guard: {existing_state.get('tool_guard', 'N/A')}")
            return existing_state

        if self.dry_run:
            self.logger.info("[DRY RUN] Would create 'Life OS Triage' database")
            self.logger.info("[DRY RUN] Would create 'Tool Guard' database")
            return {
                'life_os_triage': 'dry-run-id-1',
                'tool_guard': 'dry-run-id-2'
            }

        # Create new databases
        life_os_id = self.notion.create_life_os_triage_db(parent_page_id)
        tool_guard_id = self.notion.create_tool_guard_db(parent_page_id)

        db_ids = {
            'life_os_triage': life_os_id,
            'tool_guard': tool_guard_id
        }

        # PERSISTENCE FIX: Save database IDs for future runs
        if life_os_id or tool_guard_id:
            if save_db_state(db_ids):
                self.logger.info(f"Saved database IDs to {DB_STATE_FILE}")
            else:
                self.logger.warning("Failed to save database IDs (will retry on next run)")

        return db_ids
    
    def sync_emails(self) -> List[Dict]:
        """Sync emails from Proton (5 accounts) and Gmail."""
        all_emails = []
        
        # Proton Mail 5-account loop
        if self.proton:
            self.logger.info("Starting Proton Mail 5-account loop...")
            proton_emails = self.proton.loop_through_accounts()
            all_emails.extend(proton_emails)
        
        # Gmail
        if self.gmail:
            self.logger.info("Checking Gmail...")
            mail = self.gmail.connect()
            if mail:
                gmail_emails = self.gmail.fetch_unread(mail)
                all_emails.extend(gmail_emails)
                mail.logout()
        
        self.logger.info(f"Total emails synced: {len(all_emails)}")
        return all_emails
    
    def sync_drive_files(self) -> List[Dict]:
        """Sync files from Google Drive with circuit breaker protection."""
        if not self.gdrive:
            return []

        self.logger.info("Watching Google Drive for PDFs and Markdown files (with circuit breakers)...")
        files = self.gdrive.watch_for_files(['.pdf', '.md'])

        # Summary statistics
        full_content_count = sum(1 for f in files if f.get('status') == 'full_content')
        metadata_only_count = sum(1 for f in files if f.get('status') == 'metadata_only')
        failed_count = sum(1 for f in files if f.get('status') == 'download_failed')

        self.logger.info(f"Drive sync complete: {full_content_count} full, {metadata_only_count} metadata-only, {failed_count} failed")

        return files

    def process_local_file(self, file_path: str) -> Optional[Dict]:
        """
        Process a local file with circuit breaker protection.
        Returns file record or None if skipped.
        """
        path = Path(file_path)

        if not path.exists():
            self.logger.error(f"Local file not found: {file_path}")
            return None

        # Get file metadata
        file_size = path.stat().st_size
        file_name = path.name

        # CIRCUIT BREAKER: Check size
        if file_size > MAX_FILE_SIZE:
            self.logger.warning(f"CIRCUIT BREAKER: Local file {file_name} exceeds size limit ({file_size} > {MAX_FILE_SIZE})")
            return {
                'id': str(uuid.uuid4()),
                'name': file_name,
                'path': str(path.absolute()),
                'size': file_size,
                'status': 'metadata_only',
                'skip_reason': f"Size exceeds {MAX_FILE_SIZE} bytes"
            }

        # CIRCUIT BREAKER: Check keywords
        for keyword in IGNORE_KEYWORDS:
            if keyword.lower() in file_name.lower():
                self.logger.warning(f"CIRCUIT BREAKER: Local file {file_name} matches keyword '{keyword}'")
                return {
                    'id': str(uuid.uuid4()),
                    'name': file_name,
                    'path': str(path.absolute()),
                    'size': file_size,
                    'status': 'metadata_only',
                    'skip_reason': f"Keyword blacklist: {keyword}"
                }

        # Full processing based on file type
        try:
            if path.suffix.lower() == '.md':
                # Markdown - read directly
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Truncate if too large
                if len(content) > MAX_CONTENT_LENGTH:
                    self.logger.warning(f"Content truncated: {file_name}")
                    content = content[:MAX_CONTENT_LENGTH] + "\n\n[TRUNCATED]"

                return {
                    'id': str(uuid.uuid4()),
                    'name': file_name,
                    'path': str(path.absolute()),
                    'size': file_size,
                    'status': 'full_content',
                    'content': content,
                    'content_length': len(content),
                    'type': 'markdown'
                }

            elif path.suffix.lower() == '.pdf':
                # PDF - metadata only (requires pdfplumber or PyPDF2 for text extraction)
                self.logger.info(f"PDF detected: {file_name} - metadata only (install pdfplumber for text extraction)")
                return {
                    'id': str(uuid.uuid4()),
                    'name': file_name,
                    'path': str(path.absolute()),
                    'size': file_size,
                    'status': 'metadata_only',
                    'skip_reason': 'PDF text extraction requires pdfplumber',
                    'type': 'pdf'
                }

            else:
                self.logger.warning(f"Unknown file type: {path.suffix}")
                return {
                    'id': str(uuid.uuid4()),
                    'name': file_name,
                    'path': str(path.absolute()),
                    'size': file_size,
                    'status': 'metadata_only',
                    'skip_reason': f'Unknown file type: {path.suffix}'
                }

        except Exception as e:
            self.logger.error(f"Error processing local file {file_name}: {e}")
            return {
                'id': str(uuid.uuid4()),
                'name': file_name,
                'path': str(path.absolute()),
                'size': file_size,
                'status': 'error',
                'error': str(e)
            }
    
    def run(self):
        """Main execution loop."""
        self.logger.info("=" * 60)
        self.logger.info("ARCA Omni-Sync - Phase 6.5 Final Activation")
        self.logger.info("=" * 60)
        
        # 1. Create Notion databases
        db_ids = self.create_notion_databases()
        
        # 2. Sync emails (5-account Proton loop + Gmail)
        emails = self.sync_emails()
        
        # 3. Sync Google Drive files
        drive_files = self.sync_drive_files()
        
        # Summary
        self.logger.info("=" * 60)
        self.logger.info("Sync Summary:")
        self.logger.info(f"  - Notion Databases: {len(db_ids)} created")
        self.logger.info(f"  - Emails Synced: {len(emails)}")
        self.logger.info(f"  - Drive Files Found: {len(drive_files)}")
        self.logger.info("=" * 60)
        
        if self.dry_run:
            self.logger.info("DRY RUN COMPLETE - No changes were made")
        
        return {
            'databases': db_ids,
            'emails': emails,
            'drive_files': drive_files
        }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='ARCA Omni-Sync')
    parser.add_argument('--config', type=str, default=str(CONFIG_PATH),
                        help='Path to config file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run without making changes')
    parser.add_argument('--create-databases', action='store_true',
                        help='Create Notion databases only')
    
    args = parser.parse_args()
    
    try:
        config = load_config()
        sync = OmniSync(config, dry_run=args.dry_run)
        
        if args.create_databases:
            result = sync.create_notion_databases()
            print(json.dumps(result, indent=2))
        else:
            result = sync.run()
            
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
