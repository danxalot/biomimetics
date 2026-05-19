#!/usr/bin/env python3
"""
Email utility tool for searching and retrieving emails.
"""

import argparse
from pathlib import Path
from datetime import datetime
from email_utils import search_emails

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retrieve a specific email from a ProtonMail account via Proton Bridge.")
    parser.add_argument("--email-address", type=str, default="dan.exall@pm.me", help="Email address to search in.")
    parser.add_argument("--folder", type=str, default="INBOX", help="Email folder to search in.")
    parser.add_argument("--from-date", type=lambda s: datetime.strptime(s, '%Y-%m-%d'), help="Search for emails from this date (YYYY-MM-DD).")
    parser.add_argument("--to-date", type=lambda s: datetime.strptime(s, '%Y-%m-%d'), help="Search for emails up to this date (YYYY-MM-DD).")
    parser.add_argument("--subject", type=str, help="Subject of the email to search for.")
    parser.add_argument("--sender", type=str, help="Sender of the email to search for.")
    parser.add_argument("--content", type=str, help="Text content to search for in the email body.")
    parser.add_argument("--output-dir", type=Path, default=Path("/Users/danexall/biomimetics/review/security_incident_202603"), help="Directory to save the email(s).")
    
    args = parser.parse_args()

    search_emails(
        email_address=args.email_address,
        folder=args.folder,
        from_date=args.from_date,
        to_date=args.to_date,
        subject=args.subject,
        sender=args.sender,
        content=args.content,
        output_dir=args.output_dir
    )
