import os
import logging
from datetime import datetime
import streamlit as st
import uuid

# ==============================================================================
# Environment Variables
# ==============================================================================

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
    LLM_MODEL = "openai/gpt-oss-120b"
    LLM_TEMPERATURE = 2

    # Google Sheets Configuration
    GOOGLE_CREDENTIALS = dict(st.secrets["google_credentials"])
    GOOGLE_SHEET_NAME = "DreamKGLogs"
    GOOGLE_WORKSHEET_NAME = "Session_Logs" 
    
    # Memory Configuration
    MAX_CONVERSATION_HISTORY = 5
    
    # Spatial Intelligence Configuration
    GEOCODING_TIMEOUT = 10
    DEFAULT_DISTANCE_THRESHOLD =  0.8 # miles
    EXPANDED_DISTANCE_THRESHOLD = 1.1  # miles
    
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
    def setup_logging_with_session_id(cls, session_id):
        """Setup logging with guaranteed unique filename per session WITHOUT affecting global config."""
        
        # Create directory if it doesn't exist
        os.makedirs(cls.LOG_DIRECTORY, exist_ok=True)
        
        # Use session ID + timestamp + random component for absolute uniqueness
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")[:-3]
        random_component = str(uuid.uuid4())[:8]
        log_filename = f"{cls.LOG_DIRECTORY}{timestamp}_{session_id[:8]}_{random_component}_app.log"
        
        # Create a dedicated logger for this session instead of reconfiguring basicConfig
        logger = logging.getLogger(f"session_{session_id}")
        logger.setLevel(cls.LOG_LEVEL)
        
        # Remove any existing handlers to avoid duplicates
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Create file handler for this session only
        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(cls.LOG_LEVEL)
        
        # Create formatter and add it to the handler
        formatter = logging.Formatter(cls.LOG_FORMAT)
        file_handler.setFormatter(formatter)
        
        # Add the handler to the logger
        logger.addHandler(file_handler)
        
        # Prevent propagation to root logger to avoid duplicate logging
        logger.propagate = False
        
        return log_filename, logger


    # Category order for multi-category queries
    CATEGORY_ORDER = [
        "Food Bank",
        "Library", 
        "Social Security Office",
        "Mental Health",
        "Temporary Shelter"
    ]
    
    # Service to Category mapping for short answers
    CATEGORY_SERVICES = {
        "Food Bank": [
            "12-step",
            "addiction & recovery",
            "advocacy & legal aid",
            "after school care",
            "anger management",
            "baby supplies",
            "bereavement",
            "breakfast",
            "case management",
            "clothing",
            "community support services",
            "computer or internet access",
            "counseling",
            "day camp",
            "detox",
            "dining",
            "dinner",
            "disaster response",
            "drug testing",
            "emergency food",
            "family counseling",
            "financial education",
            "food",
            "food delivery",
            "food pantry",
            "group therapy",
            "health education",
            "help find housing",
            "help find work",
            "home goods",
            "housing advice",
            "individual counseling",
            "lunch",
            "meal",
            "meals",
            "medical care",
            "mental health care",
            "mental health evaluation",
            "navigating the system",
            "nutrition",
            "nutrition education",
            "one-on-one support",
            "outpatient treatment",
            "parenting education",
            "peer support",
            "personal care items",
            "personal hygiene",
            "recreation",
            "residential housing",
            "residential treatment",
            "safe housing",
            "short-term housing",
            "skills & training",
            "sober living",
            "spiritual support",
            "substance abuse counseling",
            "support network",
            "toys & gifts",
            "understand mental health",
            "virtual support"
        ],
        
        "Library": [
            "accessibility",
            "adult basic literacy",
            "adult education",
            "after school",
            "after school care",
            "after-school",
            "after-school programs",
            "archives",
            "arts",
            "audio",
            "audio/braille/large print books",
            "audiobooks",
            "author events",
            "author events & talks",
            "author talks",
            "basic literacy",
            "bathroom",
            "board games",
            "book",
            "book drop",
            "books",
            "braille",
            "chess",
            "chess club",
            "children",
            "children's library & department",
            "chinese",
            "chinese-language collection",
            "citizenship",
            "citizenship class",
            "class",
            "classes",
            "coding",
            "collection",
            "community programs",
            "community support",
            "computer",
            "computer access",
            "computer class",
            "computer labs",
            "computer or internet access",
            "computer/sketch/health classes",
            "computers",
            "conference",
            "cooking",
            "cooking classes",
            "copies",
            "copier",
            "copy",
            "copying",
            "culinary",
            "day camp",
            "delivery",
            "disease screening",
            "drop box",
            "drop off",
            "education",
            "employment",
            "engineering",
            "english conversation groups",
            "esl",
            "event",
            "events",
            "exhibitions",
            "facilities",
            "film",
            "foreign",
            "foreign film",
            "foreign film/language collections",
            "game",
            "games",
            "gaming",
            "gaming events",
            "ged",
            "ged & literacy classes",
            "guided tours",
            "health",
            "health classes",
            "health education",
            "help find work",
            "homework",
            "homework help",
            "internet",
            "job",
            "job & workforce development support",
            "job assistance",
            "job readiness",
            "job search",
            "kids programs",
            "language collection",
            "large collection",
            "large print",
            "learning",
            "literacy",
            "mail",
            "math",
            "medical care",
            "meeting",
            "meeting room",
            "meeting rooms",
            "meeting rooms & spaces",
            "meeting space",
            "movies",
            "multilingual",
            "museum access",
            "music",
            "music classes",
            "music/coding classes",
            "new americans",
            "one-on-one assistance",
            "parenting education",
            "playback equipment",
            "postage",
            "postage-free mail delivery",
            "print",
            "printer",
            "printing",
            "programming",
            "programs",
            "public computers",
            "public computers & lab access",
            "public restrooms",
            "quiet space",
            "reading courses",
            "research",
            "research library",
            "resume development",
            "restroom",
            "restrooms",
            "return",
            "scan",
            "scanner",
            "scanners",
            "scanning",
            "scanning & scanners",
            "science",
            "services for new americans",
            "sex education",
            "shipping",
            "social services",
            "social services support",
            "social support",
            "spanish",
            "special",
            "special collections",
            "stem",
            "stem classes & workshops",
            "story",
            "story time",
            "story times",
            "storytime",
            "study",
            "study room",
            "study rooms",
            "summer",
            "summer learning",
            "summer learning programs",
            "summer programs",
            "technology",
            "tour",
            "tours",
            "tutoring",
            "video",
            "wellness",
            "wi-fi",
            "wifi",
            "wireless",
            "workforce development",
            "workshop",
            "workshops",
            "youth programs"
        ],
        
        "Mental Health": [
            "12-step",
            "addiction",
            "addiction & recovery",
            "anger management",
            "bereavement",
            "case management",
            "checkup & test",
            "community support services",
            "counseling",
            "daily life skills",
            "detox",
            "disease screening",
            "drug testing",
            "family counseling",
            "government benefits",
            "group therapy",
            "health education",
            "help hotlines",
            "individual counseling",
            "long-term housing",
            "medical care",
            "medication management",
            "medications for addiction",
            "medications for mental health",
            "mental health",
            "mental health care",
            "mental health evaluation",
            "navigating the system",
            "one-on-one support",
            "outpatient treatment",
            "parenting education",
            "peer recovery coaching",
            "peer support",
            "prescription assistance",
            "prevent & treat",
            "psychiatric",
            "psychiatric emergency services",
            "recovery",
            "residential care",
            "residential housing",
            "residential treatment",
            "safe housing",
            "short-term housing",
            "sober living",
            "specialized therapy",
            "spiritual support",
            "substance abuse",
            "substance abuse counseling",
            "support groups",
            "support network",
            "therapy",
            "understand mental health",
            "virtual support"
        ],
        
        "Social Security Office": [
            "1099",
            "address",
            "appeal",
            "appeal a decision",
            "appealing",
            "appeals",
            "application",
            "applications",
            "apply",
            "apply for",
            "apply for benefits",
            "applying",
            "atm",
            "atm withdrawals",
            "benefit",
            "benefits",
            "calculation",
            "calculator",
            "calculating",
            "card replacement",
            "cash",
            "challenge",
            "challenging",
            "change",
            "change address",
            "change direct deposit",
            "changing",
            "decision",
            "deposit",
            "direct deposit",
            "direct deposit information",
            "disability",
            "dispute",
            "disputing",
            "earnings",
            "estimate",
            "estimates",
            "filing",
            "funds transfer",
            "get benefit estimates",
            "get replacement 1099",
            "history",
            "international",
            "international transactions",
            "medicare",
            "modify",
            "money transfer",
            "overnight card delivery",
            "overseas",
            "paper statements",
            "print proof",
            "print proof of benefits",
            "proof",
            "replacement 1099",
            "request replacement social security card",
            "requesting",
            "retirement",
            "review earnings",
            "review earnings history",
            "social security",
            "ssi",
            "statement",
            "statements",
            "transfer",
            "update",
            "update address",
            "updating",
            "withdrawal"
        ],
        
        "Temporary Shelter": [
            "stay",
            "addiction & recovery",
            "advocacy & legal aid",
            "case management",
            "clothes",
            "clothing",
            "community support services",
            "computer class",
            "computer or internet access",
            "counseling",
            "daily life skills",
            "disaster response",
            "disease screening",
            "emergency food",
            "emergency payments",
            "exercise & fitness",
            "financial assistance",
            "financial education",
            "food pantry",
            "government benefits",
            "health education",
            "help find healthcare",
            "help find housing",
            "help find school",
            "help find work",
            "help pay for housing",
            "help pay for utilities",
            "home goods",
            "housing",
            "hygiene",
            "meals",
            "medical care",
            "mental health care",
            "more education",
            "navigating the system",
            "one-on-one support",
            "parenting education",
            "personal care",
            "personal hygiene",
            "physical safety",
            "prevent & treat",
            "recreation",
            "residential housing",
            "restroom",
            "resume development",
            "safe housing",
            "screening & exams",
            "sex education",
            "shelter",
            "short-term housing",
            "skilled nursing",
            "skills & training",
            "spiritual support",
            "substance abuse counseling",
            "support network",
            "temporary shelter",
            "weather relief"
        ]
    }

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