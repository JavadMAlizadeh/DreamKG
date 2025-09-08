# ==============================================================================
# UPDATED config.py - Add Google Maps API Key
# ==============================================================================

import os
import logging
from datetime import datetime
import streamlit as st

# Load from Streamlit secrets
os.environ["NEO4J_URI"] = st.secrets["NEO4J_URI"]
os.environ["NEO4J_USERNAME"] = st.secrets["NEO4J_USERNAME"]
os.environ["NEO4J_PASSWORD"] = st.secrets["NEO4J_PASSWORD"]
os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]

class Config:
    """Configuration class containing all application settings."""

    NEO4J_URI = os.getenv("NEO4J_URI")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
    
    # LLM Configuration
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    LLM_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"
    LLM_TEMPERATURE = 2

    # Google Maps Configuration - ADD THIS
    GOOGLE_MAPS_API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY", None)

    # Google Sheets Configuration
    GOOGLE_SHEET_NAME = "DreamKGLogs"
    GOOGLE_WORKSHEET_NAME = "Session_Logs" 
    
    # Memory Configuration
    MAX_CONVERSATION_HISTORY = 5
    
    # Spatial Intelligence Configuration
    GEOCODING_TIMEOUT = 10
    DEFAULT_DISTANCE_THRESHOLD = 0.8 # miles
    EXPANDED_DISTANCE_THRESHOLD = 1.25  # miles
    
    # Proximity thresholds in miles
    PROXIMITY_THRESHOLDS = {
        'nearby': 0.8,
        'close': 0.8,
        'walking distance': 0.8,
        'driving distance': 3.0,
        'blocks': 1,
        'vicinity': 1,
        'area': 2.0
    }
    
    # Philadelphia-specific landmarks and neighborhoods
    PHILLY_LANDMARKS = {
        'city hall': '39.952335, -75.163789',
        'liberty bell': '39.9496, -75.1503',
        'independence hall': '39.9487, -75.1503',
        'temple university': '39.9812, -75.1556',
        'university of pennsylvania': '39.9522, -75.1932',
        'drexel university': '39.9566, -75.1899',
        'center city': '39.9526, -75.1652',
        'south philly': '39.9184, -75.1718',
        'north philly': '40.0059, -75.1380',
        'west philly': '39.9612, -75.2397',
        'rittenhouse square': '39.9486, -75.1723',
        'fishtown': '39.9759, -75.1370',
        'northern liberties': '39.9670, -75.1410'
    }
    
    # Spatial keywords that trigger geocoding
    SPATIAL_KEYWORDS = [
        'near', 'close', 'nearby', 'around', 'within', 'distance', 
        'closest', 'nearest', 'walking', 'driving', 'miles', 'km',
        'blocks', 'vicinity', 'area', 'location', 'from', 'to'
    ]
    
    # Logging Configuration
    LOG_DIRECTORY = "./logs/"
    LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    LOG_LEVEL = logging.INFO
    
    @classmethod
    def setup_logging(cls):
        import os
        import uuid
        os.makedirs(cls.LOG_DIRECTORY, exist_ok=True)
        
        # Use UUID + timestamp for guaranteed uniqueness
        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]  # Include microseconds
        log_filename = f"{cls.LOG_DIRECTORY}{timestamp}_{unique_id}_app.log"
        
        logging.basicConfig(
            level=cls.LOG_LEVEL,
            format=cls.LOG_FORMAT,
            handlers=[
                logging.FileHandler(log_filename)
            ]
        )
        
        return log_filename
    
    @classmethod
    def validate_config(cls):
        """Validate that all required configuration is present."""
        required_vars = [
            ('NEO4J_PASSWORD', cls.NEO4J_PASSWORD),
            ('GROQ_API_KEY', cls.GROQ_API_KEY),
        ]
        
        missing_vars = []
        for var_name, var_value in required_vars:
            if not var_value:
                missing_vars.append(var_name)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return True