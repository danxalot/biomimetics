#!/usr/bin/env python3
"""
Google Drive to MuninnDB Ingestion Pipeline (Cloud-to-Cloud)
Reads Obsidian vault from Google Drive and pushes to GCP MuninnDB.

Strict Invariants:
- GCP Auth File: /Users/danexall/biomimetics/secrets/gcp-service-agent.json
- GCP Gateway: https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator
- Target Vault: Obsidian-life
"""

import os

# Force Google Auth to use our invariant physical key for OIDC generation
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/danexall/biomimetics/secrets/gcp-service-agent.json"

import sys
import json
import base64
import urllib.request
import urllib.error
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Google API imports
try:
    from google.oauth2 import service_account, id_token
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from google.auth.transport import requests as google_requests
except ImportError as e:
    print(f"❌ Missing Google API dependencies: {e}")
    print("   Install with: pip3 install google-api-python-client google-auth")
    sys.exit(1)

# =============================================================================
# Strict Invariants (DO NOT MODIFY)
# =============================================================================

GCP_SERVICE_ACCOUNT_PATH = "/Users/danexall/biomimetics/secrets/gcp-service-agent.json"
GCP_GATEWAY_URL = "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
TARGET_VAULT_NAME = "Obsidian-life"

# Google Drive API Scope
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

# =============================================================================
# Configuration
# =============================================================================

# Target folders within the vault
TARGET_FOLDERS = [
    "Medical",
    "Personal",
    "Disability",
    "Health",
    "Context",
    "Memory",
    "Bio",
    "Complaints",
    "Legal",
    "Evidence_Pack",
    "Living",
    "People",
    "Projects",
    "Resources",
]

# File extensions to process
SUPPORTED_EXTENSIONS = [".md", ".markdown"]

# Maximum file size to process (1MB)
MAX_FILE_SIZE = 1024 * 1024

# =============================================================================
# Google Drive Authentication
# =============================================================================


def authenticate_drive_api() -> Optional[object]:
    """
    Authenticate with Google Drive API using service account.
    
    Returns:
        Drive API service object or None if authentication fails
    """
    auth_path = Path(GCP_SERVICE_ACCOUNT_PATH)
    
    if not auth_path.exists():
        print(f"❌ Service account file not found: {GCP_SERVICE_ACCOUNT_PATH}")
        return None
    
    try:
        # Load service account credentials
        credentials = service_account.Credentials.from_service_account_file(
            str(auth_path),
            scopes=[DRIVE_READONLY_SCOPE]
        )
        
        # Build Drive API service
        service = build('drive', 'v3', credentials=credentials)
        
        print(f"✅ Authenticated with Google Drive API")
        print(f"   Service Account: {credentials.service_account_email}")
        
        return service
        
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return None


def find_vault_folder(service: object) -> Optional[str]:
    """
    Find the Obsidian-life folder in Google Drive.
    
    Args:
        service: Drive API service object
    
    Returns:
        Folder ID or None if not found
    """
    try:
        # Query for folder named Obsidian-life
        query = f"name='{TARGET_VAULT_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, parents)',
            pageSize=10
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            print(f"⚠️  Folder '{TARGET_VAULT_NAME}' not found in Google Drive")
            return None
        
        if len(files) > 1:
            print(f"⚠️  Multiple folders named '{TARGET_VAULT_NAME}' found, using first")
        
        folder_id = files[0]['id']
        print(f"✅ Found vault folder: {TARGET_VAULT_NAME} (ID: {folder_id})")
        
        return folder_id
        
    except HttpError as e:
        print(f"❌ Drive API error: {e}")
        return None
    except Exception as e:
        print(f"❌ Error finding vault folder: {e}")
        return None


def find_md_files_in_folder(service: object, folder_id: str, folder_name: str = "") -> List[Dict]:
    """
    Find all markdown files in a folder and its subfolders.
    
    Args:
        service: Drive API service object
        folder_id: ID of the folder to search
        folder_name: Name of the folder (for namespace)
    
    Returns:
        List of file metadata dicts
    """
    md_files = []
    
    try:
        # Query for files in this folder (including subfolders)
        query = f"'{folder_id}' in parents and trashed=false"
        
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, mimeType, size, modifiedTime, createdTime, parents)',
            pageSize=100
        ).execute()
        
        files = results.get('files', [])
        
        for file in files:
            # Check if it's a folder (recurse)
            if file.get('mimeType') == 'application/vnd.google-apps.folder':
                # Recurse into subfolder
                subfolder_files = find_md_files_in_folder(
                    service, 
                    file['id'], 
                    folder_name + "/" + file['name'] if folder_name else file['name']
                )
                md_files.extend(subfolder_files)
            
            # Check if it's a markdown file
            elif file.get('name', '').lower().endswith(tuple(SUPPORTED_EXTENSIONS)):
                # Check file size
                size = int(file.get('size', 0))
                if size > MAX_FILE_SIZE:
                    print(f"⚠️  Skipping large file: {file['name']} ({size} bytes)")
                    continue
                
                # Determine namespace from path
                namespace = determine_namespace_from_path(folder_name + "/" + file['name'] if folder_name else file['name'])
                
                md_files.append({
                    'id': file['id'],
                    'name': file['name'],
                    'path': folder_name + "/" + file['name'] if folder_name else file['name'],
                    'size': size,
                    'modified': file.get('modifiedTime'),
                    'created': file.get('createdTime'),
                    'namespace': namespace,
                })
        
    except HttpError as e:
        print(f"⚠️  Drive API error searching folder: {e}")
    except Exception as e:
        print(f"⚠️  Error searching folder: {e}")
    
    return md_files


def determine_namespace_from_path(file_path: str) -> str:
    """
    Determine namespace from file path.
    
    Args:
        file_path: Path within vault (e.g., "Medical/Conditions.md")
    
    Returns:
        Namespace string (e.g., "medical")
    """
    path_lower = file_path.lower()
    
    for folder in TARGET_FOLDERS:
        if folder.lower() in path_lower:
            return folder.lower()
    
    return "personal"


def download_file_content(service: object, file_id: str) -> Optional[str]:
    """
    Download text content of a file from Google Drive.
    
    Args:
        service: Drive API service object
        file_id: File ID
    
    Returns:
        File content as string or None
    """
    try:
        # Request file content
        request = service.files().get_media(fileId=file_id)
        
        # Execute and decode
        content = request.execute()
        
        # Handle bytes vs string
        if isinstance(content, bytes):
            return content.decode('utf-8')
        return content
        
    except HttpError as e:
        print(f"⚠️  Error downloading file {file_id}: {e}")
        return None
    except Exception as e:
        print(f"⚠️  Error downloading file {file_id}: {e}")
        return None


# =============================================================================
# Content Parsing
# =============================================================================


def parse_markdown_content(content: str, file_name: str) -> Dict:
    """
    Parse markdown content, extracting structure.
    
    Args:
        content: Markdown text
        file_name: Name of the file
    
    Returns:
        Dict with parsed content and metadata
    """
    # Extract headers
    headers = []
    for line in content.split('\n'):
        if line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            title = line.strip('#').strip()
            headers.append({"level": level, "title": title})
    
    # Generate content hash
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    # Extract frontmatter if present
    frontmatter = ""
    body_content = content
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
            body_content = parts[2].strip()
    
    return {
        "title": Path(file_name).stem,
        "content": content,
        "headers": headers,
        "word_count": len(content.split()),
        "content_hash": content_hash,
        "frontmatter": frontmatter,
    }


# =============================================================================
# GCP MuninnDB Integration
# =============================================================================


def get_oidc_token() -> Optional[str]:
    """
    Generate OIDC token from service account for GCP Gateway authentication.
    
    Returns:
        OIDC token string or None
    """
    auth_path = Path(GCP_SERVICE_ACCOUNT_PATH)
    
    if not auth_path.exists():
        print(f"⚠️  Service account file not found: {GCP_SERVICE_ACCOUNT_PATH}")
        return None
    
    try:
        # Load service account credentials
        credentials = service_account.Credentials.from_service_account_file(
            str(auth_path)
        )
        
        # Generate OIDC token for the target audience
        token = id_token.fetch_id_token(
            google_requests.Request(),
            GCP_GATEWAY_URL
        )
        
        return token
        
    except Exception as e:
        print(f"⚠️  Failed to generate OIDC token: {e}")
        return None


def build_payload(file_data: Dict, namespace: str, action: str = "store") -> Dict:
    """
    Build payload for GCP Memory Orchestrator.
    
    Args:
        file_data: Parsed file data
        namespace: Category namespace
        action: Action type
    
    Returns:
        Dict formatted for memory-orchestrator
    """
    return {
        "action": action,
        "namespace": namespace,
        "source": "gdrive_vault",
        "vault_name": TARGET_VAULT_NAME,
        "content": {
            "title": file_data["title"],
            "path": file_data.get("path", ""),
            "content": file_data["content"],
            "headers": file_data.get("headers", []),
            "word_count": file_data.get("word_count", 0),
            "content_hash": file_data.get("content_hash", ""),
        },
        "metadata": {
            "modified": file_data.get("modified"),
            "created": file_data.get("created"),
            "frontmatter": file_data.get("frontmatter", ""),
        },
        "context": {
            "disability_context": namespace in ["medical", "disability", "health"],
            "medical_context": namespace in ["medical", "health"],
            "personal_context": namespace in ["personal", "bio"],
        },
    }


def send_to_gcp(payload: Dict, oidc_token: Optional[str], dry_run: bool = True) -> Tuple[bool, str]:
    """
    Send payload to GCP Memory Orchestrator.

    Args:
        payload: Formatted payload dict
        oidc_token: OIDC token for authentication
        dry_run: If True, don't actually send

    Returns:
        Tuple of (success: bool, message: str)
    """
    if dry_run:
        return True, "Dry run - not sent"

    if not oidc_token:
        return False, "No OIDC token available"

    try:
        # Prepare request with OIDC authentication
        data = json.dumps(payload).encode('utf-8')

        req = urllib.request.Request(
            GCP_GATEWAY_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {oidc_token}",
            }
        )

        # Create SSL context that bypasses certificate verification (for local dev)
        import ssl
        ssl_context = ssl._create_unverified_context()

        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
            result = json.loads(response.read().decode('utf-8'))
            return True, f"Success: {result}"
            
    except urllib.error.HTTPError as e:
        return False, f"HTTP Error {e.code}: {e.read().decode()}"
    except Exception as e:
        return False, f"Error: {e}"


# =============================================================================
# Main Ingestion Pipeline
# =============================================================================


def run_ingestion(dry_run: bool = True, verbose: bool = True):
    """
    Run the Google Drive to MuninnDB ingestion pipeline.
    
    Args:
        dry_run: If True, print discovered files instead of sending
        verbose: If True, print detailed output
    """
    print("=" * 70)
    print("  Google Drive to MuninnDB Ingestion Pipeline (Cloud-to-Cloud)")
    print("=" * 70)
    print()
    
    # Configuration summary
    print(f"🔐 Service Account: {GCP_SERVICE_ACCOUNT_PATH}")
    print(f"🌐 GCP Gateway: {GCP_GATEWAY_URL}")
    print(f"📁 Target Vault: {TARGET_VAULT_NAME}")
    print(f"📂 Target Folders: {', '.join(TARGET_FOLDERS)}")
    print(f"🧪 Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()
    
    # Step 1: Authenticate with Google Drive API
    print("📊 Stage 1: Google Drive Read")
    print("-" * 70)
    print()
    
    print("🔑 Authenticating with Google Drive API...")
    service = authenticate_drive_api()
    
    if not service:
        print("❌ Failed to authenticate with Google Drive API")
        print("   Ensure service account file exists and has Drive API access")
        return False
    
    print()
    
    # Step 2: Find vault folder
    print(f"🔍 Searching for vault folder: {TARGET_VAULT_NAME}...")
    vault_folder_id = find_vault_folder(service)
    
    if not vault_folder_id:
        print("❌ Vault folder not found in Google Drive")
        return False
    
    print()
    
    # Step 3: Find markdown files
    print(f"🔍 Scanning vault for markdown files...")
    md_files = find_md_files_in_folder(service, vault_folder_id)
    
    print(f"   📄 Found {len(md_files)} markdown files")
    print()
    
    if not md_files:
        print("ℹ️  No markdown files found in vault")
        return True
    
    # List discovered files
    if verbose or dry_run:
        print("📋 Discovered Files:")
        print("-" * 70)
        for i, file in enumerate(md_files, 1):
            print(f"   [{i}] {file['path']}")
            print(f"       Namespace: {file['namespace']}, Size: {file['size']} bytes")
        print()
    
    if dry_run:
        print("✅ DRY RUN COMPLETE")
        print("   Files discovered but not sent to MuninnDB")
        print("   Run with --live to send data")
        return True
    
    # Step 4: Process and send files
    print("📊 Stage 2: MuninnDB Push")
    print("-" * 70)
    print()
    
    # Get OIDC token
    print("🔑 Generating OIDC token for GCP Gateway...")
    oidc_token = get_oidc_token()
    
    if oidc_token:
        print(f"   ✅ OIDC token generated")
    else:
        print(f"   ⚠️  OIDC token not available (will skip live send)")
    print()
    
    # Process files
    stats = {
        "processed": 0,
        "downloaded": 0,
        "sent": 0,
        "errors": 0,
    }
    
    for file in md_files:
        stats["processed"] += 1
        
        print(f"📄 [{stats['processed']}] {file['name']}")
        
        # Download file content
        content = download_file_content(service, file['id'])
        
        if not content:
            print(f"   ⚠️  Failed to download content")
            stats["errors"] += 1
            continue
        
        stats["downloaded"] += 1
        
        # Parse content
        parsed = parse_markdown_content(content, file['name'])
        parsed['path'] = file['path']
        parsed['modified'] = file['modified']
        parsed['created'] = file['created']
        
        # Build payload
        payload = build_payload(parsed, file['namespace'])
        
        if verbose:
            print(f"   Path: {file['path']}")
            print(f"   Namespace: {file['namespace']}")
            print(f"   Words: {parsed['word_count']}")
            print(f"   Headers: {len(parsed['headers'])}")
        
        # Send to GCP
        success, message = send_to_gcp(payload, oidc_token, dry_run=False)
        
        if success:
            print(f"   ✅ Sent to MuninnDB")
            stats["sent"] += 1
        else:
            print(f"   ❌ Failed: {message}")
            stats["errors"] += 1
        
        print()
    
    # Summary
    print("=" * 70)
    print("  Ingestion Summary")
    print("=" * 70)
    print()
    print(f"   Files Processed: {stats['processed']}")
    print(f"   Files Downloaded: {stats['downloaded']}")
    print(f"   Files Sent: {stats['sent']}")
    print(f"   Errors: {stats['errors']}")
    print()
    print("✅ Cloud-to-Cloud ingestion complete")
    print()
    
    return True


# =============================================================================
# CLI Entry Point
# =============================================================================


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Google Drive to MuninnDB Ingestion Pipeline"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Send data to GCP (default: dry run)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce output verbosity"
    )
    
    args = parser.parse_args()
    
    # Run ingestion
    success = run_ingestion(
        dry_run=not args.live,
        verbose=not args.quiet
    )
    
    sys.exit(0 if success else 1)
