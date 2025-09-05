
import logging
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
from config import Config
import streamlit as st


class GoogleSheetsLogger:
    """
    Simple service to log session data to Google Sheets in just two columns.
    """
    
    def __init__(self):
        """Initialize the Google Sheets logger with service account credentials."""
        # Use credentials directly from Streamlit secrets
        self.credentials_dict = dict(st.secrets.google_credentials)
        self.sheet_name = Config.GOOGLE_SHEET_NAME
        self.worksheet_name = Config.GOOGLE_WORKSHEET_NAME
        
        self.gc = None
        self.worksheet = None
        self.initialized = False
        
        # Initialize connection
        self._initialize_connection()
        
        logging.info(f"Simple GoogleSheetsLogger initialized for sheet: {self.sheet_name}")
    
    def _initialize_connection(self):
        """Initialize connection to Google Sheets."""
        try:
            # Define the scope
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            # Authenticate using service account info from secrets
            creds = Credentials.from_service_account_info(self.credentials_dict, scopes=scope)
            self.gc = gspread.authorize(creds)
            
            # Open the spreadsheet
            try:
                self.spreadsheet = self.gc.open(self.sheet_name)
                logging.info(f"Successfully opened spreadsheet: {self.sheet_name}")
            except gspread.SpreadsheetNotFound:
                logging.error(f"Spreadsheet '{self.sheet_name}' not found. Make sure it exists and is shared with logger@dreamkg.iam.gserviceaccount.com")
                return
            
            # Get or create simple worksheet
            try:
                self.worksheet = self.spreadsheet.worksheet(self.worksheet_name)
                logging.info(f"Using existing worksheet: {self.worksheet_name}")
            except gspread.WorksheetNotFound:
                self.worksheet = self.spreadsheet.add_worksheet(title=self.worksheet_name, rows=1000, cols=3)
                logging.info(f"Created new worksheet: {self.worksheet_name}")
                self._setup_simple_headers()
            
            self.initialized = True
            logging.info("Simple Google Sheets connection initialized successfully")
            
        except Exception as e:
            logging.error(f"Failed to initialize Google Sheets connection: {str(e)}")
            self.initialized = False
    
    def _setup_simple_headers(self):
        """Set up simple two-column headers."""
        headers = [
            'Timestamp',
            'Session_ID', 
            'Complete_Log_Content'
        ]
        
        try:
            self.worksheet.append_row(headers)
            logging.info("Simple headers added to Google Sheet")
        except Exception as e:
            logging.error(f"Failed to add simple headers: {str(e)}")
    
    def log_session_data(self, log_file_path, metrics_data=None):
        """
        Log session data to Google Sheets - just Session ID and complete log content.
        
        Args:
            log_file_path (str): Path to the session log file
            metrics_data (dict): Optional metrics data (ignored in simple version)
        """
        if not self.initialized:
            logging.warning("Google Sheets logger not initialized, skipping log upload")
            return
        
        try:
            # Read the complete log file
            if not os.path.exists(log_file_path):
                logging.warning(f"Log file not found: {log_file_path}")
                return
            
            with open(log_file_path, 'r', encoding='utf-8') as f:
                complete_log_content = f.read()
            
            # Extract session ID from filename
            session_id = os.path.basename(log_file_path).replace('.log', '')
            
            # Create simple row with just timestamp, session ID and complete log content
            row_data = [
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # Timestamp
                session_id,                                     # Session_ID
                complete_log_content                            # Complete_Log_Content
            ]
            
            # Append to Google Sheets
            self.worksheet.append_row(row_data)
            logging.info(f"Successfully logged simple session data to Google Sheets: {session_id}")
            
        except Exception as e:
            logging.error(f"Failed to log simple session data to Google Sheets: {str(e)}")
    
    def test_connection(self):
        """Test the Google Sheets connection."""
        if not self.initialized:
            return False
        
        try:
            cell_value = self.worksheet.cell(1, 1).value
            logging.info(f"Google Sheets connection test successful. First cell value: {cell_value}")
            return True
        except Exception as e:
            logging.error(f"Google Sheets connection test failed: {str(e)}")
            return False