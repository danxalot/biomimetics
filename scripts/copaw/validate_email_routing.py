import sys
import unittest
from unittest.mock import MagicMock, patch

# path to the script relative to workspace root
sys.path.append("/Users/danexall/biomimetics/scripts/copaw")
import mcp_email_server

class TestEmailRouting(unittest.TestCase):
    @patch("mcp_email_server.imaplib.IMAP4_SSL")
    @patch("mcp_email_server.imaplib.IMAP4")
    @patch("mcp_email_server.ssl._create_unverified_context")
    def test_imap_routing_gmail(self, mock_ssl_context, mock_imap, mock_imap_ssl):
        # Setup
        account = "dan.exall@gmail.com"
        password = "fake_password"
        account_type = "gmail"
        
        # Action
        mcp_email_server.connect_imap(account, password, account_type)
        
        # Verify Gmail uses IMAP4_SSL on port 993
        mock_imap_ssl.assert_called_once_with("imap.gmail.com", 993, ssl_context=mcp_email_server.GMAIL_SSL_CONTEXT)
        mock_imap.assert_not_called()

    @patch("mcp_email_server.imaplib.IMAP4_SSL")
    @patch("mcp_email_server.imaplib.IMAP4")
    @patch("mcp_email_server.ssl._create_unverified_context")
    def test_imap_routing_proton(self, mock_ssl_context, mock_imap, mock_imap_ssl):
        # Setup
        account = "dan.exall@pm.me"
        password = "fake_password"
        account_type = "proton"
        
        # Action
        mcp_email_server.connect_imap(account, password, account_type)
        
        # Verify Proton uses IMAP4 on localhost port 1143 with starttls
        mock_imap.assert_called_once_with("127.0.0.1", 1143)
        mock_imap.return_value.starttls.assert_called_once()
        mock_imap_ssl.assert_not_called()

    @patch("mcp_email_server.smtplib.SMTP")
    def test_smtp_routing_gmail(self, mock_smtp):
        # Setup
        account = "dan.exall@gmail.com"
        password = "fake_password"
        account_type = "gmail"
        
        # Action
        mcp_email_server.connect_smtp(account, password, account_type)
        
        # Verify Gmail uses SMTP on port 587
        mock_smtp.assert_called_once_with("smtp.gmail.com", 587)
        mock_smtp.return_value.starttls.assert_called_once()

    @patch("mcp_email_server.smtplib.SMTP")
    def test_smtp_routing_proton(self, mock_smtp):
        # Setup
        account = "dan.exall@pm.me"
        password = "fake_password"
        account_type = "proton"
        
        # Action
        mcp_email_server.connect_smtp(account, password, account_type)
        
        # Verify Proton uses SMTP on localhost port 1125
        mock_smtp.assert_called_once_with("127.0.0.1", 1125)
        mock_smtp.return_value.starttls.assert_called_once()

if __name__ == "__main__":
    unittest.main()
