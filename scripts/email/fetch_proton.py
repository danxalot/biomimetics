import imaplib
import email
from email.header import decode_header
from datetime import datetime, timezone, timedelta
import ssl

# Your provided configuration
IMAP_HOST = '127.0.0.1'
IMAP_PORT = 1143
USERNAME = 'dan.exall@pm.me'
PASSWORD = 'ayaOq50DHJRuB1CsH2OoIA'

def get_recent_emails():
    try:
        # Connect to the local Proton Bridge
        mail = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
        
        # Proton Bridge uses self-signed certs locally; we must ignore the verification
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Upgrade to STARTTLS
        mail.starttls(ssl_context=context)
        
        # Authenticate
        mail.login(USERNAME, PASSWORD)
        mail.select('INBOX')
        
        # Calculate the exact time 2 hours ago (UTC)
        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
        
        # IMAP only searches by date. Grab everything from yesterday to now.
        date_since = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{date_since}")')
        
        if status != 'OK' or not messages[0]:
            print("No recent emails found in the inbox.")
            return

        email_ids = messages[0].split()
        found_any = False
        
        print(f"Scanning for emails received since {two_hours_ago.strftime('%Y-%m-%d %H:%M:%S %Z')}...\n")
        
        for e_id in email_ids:
            # Fetch the raw email data
            status, msg_data = mail.fetch(e_id, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Parse the Date header to check the exact time
                    date_tuple = email.utils.parsedate_tz(msg['Date'])
                    if date_tuple:
                        local_date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple), timezone.utc)
                        
                        # Filter out anything older than 2 hours
                        if local_date >= two_hours_ago:
                            found_any = True
                            
                            # Decode the Subject safely
                            subject, encoding = decode_header(msg['Subject'])[0]
                            if isinstance(subject, bytes):
                                subject = subject.decode(encoding if encoding else 'utf-8', errors='ignore')
                            
                            sender = msg.get('From')
                            print("-" * 60)
                            print(f"Time:    {local_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                            print(f"From:    {sender}")
                            print(f"Subject: {subject}")
                            
                            # Extract the plain text body
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body = part.get_payload(decode=True).decode(errors='ignore')
                                        print(f"\n{body.strip()[:500]}...\n") # Limiting to 500 chars for readability
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode(errors='ignore')
                                print(f"\n{body.strip()[:500]}...\n")

        if not found_any:
            print("No emails found within the exact 2-hour window.")
            
        mail.logout()
        
    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    get_recent_emails()
