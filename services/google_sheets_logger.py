import logging
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
from config import Config
import streamlit as st


class GoogleSheetsLogger:
    """
    Enhanced service to log session data to Google Sheets with debugging.
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
        
        logging.info(f"Enhanced GoogleSheetsLogger initialized for sheet: {self.sheet_name}")
    
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
            
            # Get or create worksheet
            try:
                self.worksheet = self.spreadsheet.worksheet(self.worksheet_name)
                logging.info(f"Using existing worksheet: {self.worksheet_name}")
            except gspread.WorksheetNotFound:
                self.worksheet = self.spreadsheet.add_worksheet(title=self.worksheet_name, rows=1000, cols=3)
                logging.info(f"Created new worksheet: {self.worksheet_name}")
                self._setup_headers()
            
            self.initialized = True
            logging.info("Enhanced Google Sheets connection initialized successfully")
            
        except Exception as e:
            logging.error(f"Failed to initialize Google Sheets connection: {str(e)}")
            self.initialized = False
    
    def _setup_headers(self):
        """Set up headers for the worksheet."""
        headers = [
            'Timestamp',
            'Session_ID', 
            'Complete_Log_Content'
        ]
        
        try:
            self.worksheet.append_row(headers)
            logging.info("Headers added to Google Sheet")
        except Exception as e:
            logging.error(f"Failed to add headers: {str(e)}")
    
    def log_session_data(self, log_file_path, metrics_data=None):
        """
        Log session data to Google Sheets with enhanced debugging.
        
        Args:
            log_file_path (str): Path to the session log file
            metrics_data (dict): Optional metrics data (ignored in simple version)
        """
        if not self.initialized:
            logging.warning("Google Sheets logger not initialized, skipping log upload")
            return
        
        try:
            # Debug: Check if log file exists
            logging.info(f"Attempting to log session data from: {log_file_path}")
            
            if not os.path.exists(log_file_path):
                logging.error(f"Log file not found at path: {log_file_path}")
                logging.info(f"Current working directory: {os.getcwd()}")
                logging.info(f"Directory contents: {os.listdir('.')}")
                if os.path.exists('./logs'):
                    logging.info(f"Logs directory contents: {os.listdir('./logs')}")
                return
            
            # Debug: Check file size and readability
            file_size = os.path.getsize(log_file_path)
            logging.info(f"Log file size: {file_size} bytes")
            
            if file_size == 0:
                logging.warning(f"Log file is empty: {log_file_path}")
                complete_log_content = "Log file was empty at time of upload"
            else:
                # Read the complete log file with error handling
                try:
                    with open(log_file_path, 'r', encoding='utf-8') as f:
                        complete_log_content = f.read()
                    
                    logging.info(f"Successfully read log file. Content length: {len(complete_log_content)} characters")
                    
                    # Debug: Log first 200 characters to verify content
                    preview = complete_log_content[:200].replace('\n', '\\n')
                    logging.info(f"Log content preview: {preview}...")
                    
                    if len(complete_log_content.strip()) == 0:
                        logging.warning("Log file content is empty or whitespace only")
                        complete_log_content = "Log file contained only whitespace"
                
                except UnicodeDecodeError as e:
                    logging.error(f"Unicode decode error reading log file: {str(e)}")
                    # Try with different encoding
                    with open(log_file_path, 'r', encoding='latin-1') as f:
                        complete_log_content = f.read()
                    logging.info("Successfully read log file with latin-1 encoding")
                
                except Exception as e:
                    logging.error(f"Error reading log file: {str(e)}")
                    complete_log_content = f"Error reading log file: {str(e)}"
            
            # Extract session ID from filename
            session_id = os.path.basename(log_file_path).replace('.log', '')
            logging.info(f"Extracted session ID: {session_id}")
            
            # Create row data with length validation
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Google Sheets has a cell limit of ~50,000 characters
            # Truncate if necessary
            max_cell_length = 49000
            if len(complete_log_content) > max_cell_length:
                logging.warning(f"Log content too long ({len(complete_log_content)} chars), truncating to {max_cell_length}")
                complete_log_content = complete_log_content[:max_cell_length] + "\n\n[LOG TRUNCATED DUE TO LENGTH]"
            
            row_data = [
                timestamp,           # Timestamp
                session_id,         # Session_ID  
                complete_log_content # Complete_Log_Content
            ]
            
            logging.info(f"Preparing to append row with {len(row_data)} columns")
            logging.info(f"Row data sizes: timestamp={len(timestamp)}, session_id={len(session_id)}, log_content={len(complete_log_content)} chars")
            
            # Append to Google Sheets with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.worksheet.append_row(row_data)
                    logging.info(f"Successfully logged session data to Google Sheets: {session_id} (attempt {attempt + 1})")
                    break
                except Exception as append_error:
                    logging.error(f"Failed to append row (attempt {attempt + 1}): {str(append_error)}")
                    if attempt == max_retries - 1:
                        raise append_error
                    import time
                    time.sleep(1)  # Wait before retry
            
        except Exception as e:
            logging.error(f"Failed to log session data to Google Sheets: {str(e)}")
            logging.error(f"Error type: {type(e).__name__}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
    
    def test_connection(self):
        """Test the Google Sheets connection with enhanced debugging."""
        if not self.initialized:
            logging.error("Google Sheets logger not initialized for connection test")
            return False
        
        try:
            # Test basic connection
            cell_value = self.worksheet.cell(1, 1).value
            logging.info(f"Google Sheets connection test successful. First cell value: '{cell_value}'")
            
            # Test write capability with a small test
            test_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            test_row = [test_timestamp, "CONNECTION_TEST", "This is a connection test"]
            
            # Find next empty row
            all_values = self.worksheet.get_all_values()
            next_row = len(all_values) + 1
            
            # Write test row
            self.worksheet.append_row(test_row)
            logging.info(f"Successfully wrote test row to Google Sheets at row {next_row}")
            
            return True
            
        except Exception as e:
            logging.error(f"Google Sheets connection test failed: {str(e)}")
            logging.error(f"Error type: {type(e).__name__}")
            return False
    
    def get_worksheet_info(self):
        """Get information about the current worksheet for debugging."""
        if not self.initialized:
            return {"error": "Not initialized"}
        
        try:
            info = {
                "worksheet_title": self.worksheet.title,
                "row_count": self.worksheet.row_count,
                "col_count": self.worksheet.col_count,
                "all_records_count": len(self.worksheet.get_all_records()),
                "first_row_values": self.worksheet.row_values(1) if self.worksheet.row_count > 0 else []
            }
            logging.info(f"Worksheet info: {info}")
            return info
        except Exception as e:
            error_info = {"error": str(e)}
            logging.error(f"Failed to get worksheet info: {error_info}")
            return error_info