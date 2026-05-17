import sys
import imaplib
import email
from email.header import decode_header
import ssl

# Your provided configuration
IMAP_HOST = '127.0.0.1'
IMAP_PORT = 1143
USERNAME = 'dan.exall@pm.me'
PASSWORD = 'ayaOq50DHJRuB1CsH2OoIA'

def fetch_by_subject(target_subjects):
    try:
        # Connect to the local Proton Bridge
        mail = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
        
        # Bypass self-signed cert verification for local Bridge
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Upgrade to STARTTLS and Authenticate
        mail.starttls(ssl_context=context)
        mail.login(USERNAME, PASSWORD)
        mail.select('INBOX')
        
        found_any = False
        
        for subject_query in target_subjects:
            print(f"Searching for subject: '{subject_query}'...")
            
            # Use native IMAP search for the specific subject
            status, messages = mail.search(None, f'SUBJECT "{subject_query}"')
            
            if status == 'OK' and messages[0]:
                email_ids = messages[0].split()
                
                for e_id in email_ids:
                    # Fetch the full raw email data
                    status, msg_data = mail.fetch(e_id, '(RFC822)')
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            
                            # Decode the Subject safely
                            subject, encoding = decode_header(msg['Subject'])[0]
                            if isinstance(subject, bytes):
                                subject = subject.decode(encoding if encoding else 'utf-8', errors='ignore')
                            
                            sender = msg.get('From')
                            date = msg.get('Date')
                            
                            print("\n" + "=" * 80)
                            print(f"Date:    {date}")
                            print(f"From:    {sender}")
                            print(f"Subject: {subject}")
                            print("=" * 80 + "\n")
                            
                            # Extract the FULL plain text body
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body = part.get_payload(decode=True).decode(errors='ignore')
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode(errors='ignore')
                            
                            # Print the entire untruncated body
                            print(body.strip())
                            print("\n" + "=" * 80 + "\n")
                            found_any = True
            else:
                print(f" -> No matches found for '{subject_query}'.")

        if not found_any:
            print("\nExtraction complete. No emails matched the provided subjects.")
            
        mail.logout()
        
    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    # Ensure the user passed at least one subject argument
    if len(sys.argv) < 2:
        print("Usage error. Please provide subject lines.")
        print('Example: python3 fetch_subject.py "Invoice 2024" "Project Update"')
        sys.exit(1)
    
    # Grab all arguments passed after the script name as target subjects
    targets = sys.argv[1:]
    fetch_by_subject(targets)
