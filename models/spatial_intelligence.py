

import re
import logging
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from config import Config


class SpatialIntelligence:
    """
    Handles all spatial intelligence operations including:
    - Spatial query detection
    - Location extraction from natural language
    - Geocoding locations to coordinates
    - Distance threshold determination
    """
    
    def __init__(self):
        """Initialize spatial intelligence with geocoder and configuration."""
        self.geolocator = Nominatim(
            user_agent="organization_finder_app", 
            timeout=Config.GEOCODING_TIMEOUT
        )
        self.geocoding_cache = {}
        self.spatial_keywords = Config.SPATIAL_KEYWORDS
        self.proximity_thresholds = Config.PROXIMITY_THRESHOLDS
        self.philly_landmarks = Config.PHILLY_LANDMARKS
        
        logging.info("SpatialIntelligence initialized with geocoding cache and Philadelphia landmarks")

    def detect_spatial_query(self, query):
        """
        Detect if a query contains spatial/location-based keywords with context awareness.
        
        Args:
            query (str): User query to analyze
            
        Returns:
            bool: True if query contains spatial indicators, False otherwise
        """
        query_lower = query.lower()
        
        # First, check for explicit spatial indicators (most reliable)
        explicit_spatial_patterns = [
            r'\bnear\s+[a-zA-Z]',           # "near City Hall" (not "near 8pm")
            r'\bclose\s+to\s+[a-zA-Z]',     # "close to Temple"
            r'\bwithin\s+\d+.*(?:mile|km|block)', # "within 2 miles"
            r'\b\d+\s*(?:mile|km|block)s?\s+(?:of|from)', # "2 miles from"
            r'\b(?:walking|driving)\s+distance', # "walking distance"
        ]
        
        for pattern in explicit_spatial_patterns:
            if re.search(pattern, query_lower):
                logging.info(f"Explicit spatial pattern detected: {pattern}")
                return True
        
        # Check for Philadelphia landmarks
        has_landmarks = any(landmark in query_lower for landmark in self.philly_landmarks.keys())
        if has_landmarks:
            logging.info("Philadelphia landmark detected in query")
            return True
        
        # IMPROVED: Check for address patterns (both numbered and street names)
        address_patterns = [
            # Numbered addresses: "123 Main Street"
            r'\d+\s+\w+\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard)',
            # Street names without numbers: "North Broad Street", "Market Street", etc.
            r'(?:north|south|east|west)\s+\w+\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard)',
            r'\w+\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard)(?:\s|$|,|\.)',
            # Zip codes
            r'\b19\d{3}\b'
        ]
        
        for pattern in address_patterns:
            if re.search(pattern, query_lower):
                logging.info(f"Address pattern detected: {pattern}")
                return True
        
        # FIXED: Check for location prepositions but exclude time-related contexts
        # Define time-related words that should NOT trigger spatial detection
        time_words = [
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
            'weekday', 'weekend', 'morning', 'afternoon', 'evening', 'night',
            'today', 'tomorrow', 'yesterday', 'weekdays', 'weekends',
            'am', 'pm', 'oclock', "o'clock"
        ]
        
        # Create a pattern that excludes time words
        time_word_pattern = r'\b(?:' + '|'.join(time_words) + r')\b'
        
        location_patterns = [
            (r'\bin\s+(?!the\s+)(?!a\s+)(?!\d)([a-zA-Z]+(?:\s+[a-zA-Z]+)*)', 'in'),    # "in Philadelphia" but not "in the morning"
            (r'\bat\s+(?!\d)([a-zA-Z]+(?:\s+[a-zA-Z]+)*)', 'at'),                      # "at Temple" but not "at 8pm"
            (r'\bon\s+(?!a\s+)(?!the\s+)(?!\d)([a-zA-Z]+(?:\s+[a-zA-Z]+)*)', 'on'),    # "on North Broad Street" - FIXED VERSION
        ]
        
        for pattern, preposition in location_patterns:
            matches = re.finditer(pattern, query_lower)
            for match in matches:
                location_candidate = match.group(1).strip()
                
                # Check if the location candidate is actually a time word
                if not re.search(time_word_pattern, location_candidate):
                    logging.info(f"Location preposition pattern detected: {preposition} {location_candidate}")
                    return True
                else:
                    logging.info(f"Excluded time context: {preposition} {location_candidate}")
        
        # Check for time-related contexts where "around" shouldn't trigger spatial mode
        # Only check "around" in time context after we've checked explicit spatial patterns
        around_time_contexts = [
            r'around\s+\d+\s*(am|pm|:\d+)',  # "around 8pm", "around 8:30am"
            r'around\s+\d+\s*(o\'?clock)',   # "around 8 o'clock"
        ]
        
        # Check if "around" is used in time context AND there are no spatial indicators
        has_around_time = any(re.search(pattern, query_lower) for pattern in around_time_contexts)
        
        # Additional "around" pattern for location (now that we've checked time contexts)
        around_location_pattern = r'\baround\s+(?!the\s+)(?!\d)([a-zA-Z]+(?:\s+[a-zA-Z]+)*)'  # "around Temple" but not "around 8pm"
        around_matches = re.finditer(around_location_pattern, query_lower)
        
        for match in around_matches:
            location_candidate = match.group(1).strip()
            # Check if it's not a time word
            if not re.search(time_word_pattern, location_candidate):
                logging.info(f"Around location pattern detected: around {location_candidate}")
                return True
        
        # If "around" is only used for time and no spatial indicators found, return False
        if has_around_time:
            # Double-check: make sure there are truly no spatial indicators
            other_time_contexts = [
                r'open\s+around',                # "open around"
                r'close\s+around',               # "close around"
                r'hours.*around',                # "hours around"
            ]
            
            # If query matches other time contexts, it's not spatial
            for time_pattern in other_time_contexts:
                if re.search(time_pattern, query_lower):
                    logging.info("Time context detected - not spatial")
                    return False
        
        # Final check: remaining spatial keywords (but only if not purely time context)
        remaining_spatial_keywords = ['closest', 'nearest', 'vicinity', 'area', 'location']
        has_remaining_spatial = any(keyword in query_lower for keyword in remaining_spatial_keywords)
        
        if has_remaining_spatial:
            logging.info("Remaining spatial keywords detected")
        
        return has_remaining_spatial

    def geocode_location(self, location_text):
        """
        Geocode a location string to coordinates with caching.
        
        Args:
            location_text (str): Location description to geocode
            
        Returns:
            tuple: (latitude, longitude) or None if geocoding fails
        """
        # Check cache first
        if location_text in self.geocoding_cache:
            logging.info(f"Using cached coordinates for: {location_text}")
            return self.geocoding_cache[location_text]
        
        # Check if it's a known Philadelphia landmark
        location_lower = location_text.lower()
        for landmark, coords in self.philly_landmarks.items():
            if landmark in location_lower:
                lat, lon = map(float, coords.split(', '))
                self.geocoding_cache[location_text] = (lat, lon)
                logging.info(f"Found landmark {landmark} at coordinates: {lat}, {lon}")
                return (lat, lon)
        
        # Try geocoding with Nominatim
        try:
            # Add Philadelphia context for better results
            search_query = f"{location_text}, Philadelphia, PA"
            location = self.geolocator.geocode(search_query)
            
            if location:
                coords = (location.latitude, location.longitude)
                self.geocoding_cache[location_text] = coords
                logging.info(f"Geocoded '{location_text}' to coordinates: {coords}")
                return coords
            else:
                logging.warning(f"Could not geocode location: {location_text}")
                return None
                
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logging.error(f"Geocoding service error for '{location_text}': {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Unexpected geocoding error for '{location_text}': {str(e)}")
            return None

    def extract_location_from_query(self, query):
        """
        Extract location information from the user query with improved context awareness.
        FIXED VERSION to handle multi-word landmarks and complex locations.
        """
        query_lower = query.lower()

        # --- PRIORITY 1: Check for known Philadelphia landmarks first ---
        for landmark in self.philly_landmarks.keys():
            if landmark in query_lower:
                logging.info(f"Extracted landmark from query: '{landmark}'")
                return landmark

        # --- PRIORITY 2: Check for zip codes early (they're very specific) ---
        zip_match = re.search(r'\b(19\d{3})\b', query_lower)
        if zip_match:
            zip_code = zip_match.group(1)
            logging.info(f"Extracted zip code from query: '{zip_code}'")
            return zip_code

        # Helper function for word boundary validation - IMPROVED
        def contains_excluded_words(text, excluded_words):
            """Check if text contains any excluded words using word boundaries."""
            text_lower = text.lower()
            for word in excluded_words:
                # Use word boundaries to match whole words only
                if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
                    logging.info(f"Found excluded word '{word}' in '{text}'")
                    return True
            return False

        def extract_clean_location(text, stop_words=None):
            """Extract clean location by removing stop words at the end."""
            if not stop_words:
                stop_words = ['has', 'have', 'with', 'on', 'at', 'in', 'is', 'are', 'handles', 'handle']
            
            words = text.strip().split()
            # Remove stop words from the end
            while words and words[-1].lower() in stop_words:
                words.pop()
            
            return ' '.join(words) if words else text

        # --- PRIORITY 3: IMPROVED Multi-word landmark patterns ---
        # Handle "the [Landmark Name]" patterns specifically
        landmark_patterns = [
            # Pattern for "near the [Multi-word Landmark]"
            r'near\s+the\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){1,4})(?:\s+(?:has|have|with|on|at|in|is|are|handles|handle)\b|\s*$)',
            r'close\s+to\s+the\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){1,4})(?:\s+(?:has|have|with|on|at|in|is|are|handles|handle)\b|\s*$)',
            r'at\s+the\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){1,4})(?:\s+(?:has|have|with|on|at|in|is|are|handles|handle)\b|\s*$)',
            r'around\s+the\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){1,4})(?:\s+(?:has|have|with|on|at|in|is|are|handles|handle)\b|\s*$)',
            
            # Pattern for "near [Multi-word Landmark without 'the']"
            r'near\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){1,3})(?:\s+(?:has|have|with|on|at|in|is|are|handles|handle)\b|\s*$)',
            r'close\s+to\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){1,3})(?:\s+(?:has|have|with|on|at|in|is|are|handles|handle)\b|\s*$)',
        ]

        for pattern in landmark_patterns:
            match = re.search(pattern, query_lower)
            if match:
                location_text = match.group(1).strip()
                # Clean up by removing trailing context words
                clean_location = extract_clean_location(location_text)
                
                # Validate it's not a service or excluded term
                service_words = ['story', 'time', 'toddler', 'program', 'class', 'service', 'form', 'tax', 'application']
                if not contains_excluded_words(clean_location, service_words) and len(clean_location.split()) >= 1:
                    logging.info(f"Extracted multi-word landmark: '{clean_location}'")
                    return clean_location

        # --- PRIORITY 4: IMPROVED Numbered and directional street patterns ---
        
        # Pattern 1: Numbered addresses with directional prefixes - FIXED
        numbered_directional_pattern = r'\b((?:north|south|east|west)\s+\d+(?:st|nd|rd|th)?\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard))\b'
        numbered_directional_match = re.search(numbered_directional_pattern, query_lower)
        if numbered_directional_match:
            address = numbered_directional_match.group(1).strip()
            logging.info(f"Extracted numbered directional street: '{address}'")
            return address
        
        # Pattern 2: Regular numbered addresses
        numbered_address_match = re.search(r'\b(\d{1,5}\s+[a-zA-Z]+(?:\s+[a-zA-Z]+){0,2}\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard))\b', query_lower)
        if numbered_address_match:
            address = numbered_address_match.group(1).strip()
            form_related_words = ['form', 'tax', 'w2', 'w-2', '1099', 'statement', 'document']
            if not contains_excluded_words(address, form_related_words):
                logging.info(f"Extracted numbered address from query: '{address}'")
                return address
        
        # Pattern 3: Directional streets with named streets - IMPROVED
        directional_patterns = [
            r'\b((?:north|south|east|west)\s+[a-zA-Z]+\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard))\b',
            r'\b((?:north|south|east|west)\s+[a-zA-Z]+\s+[a-zA-Z]+\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard))\b'
        ]
        
        for pattern in directional_patterns:
            directional_match = re.search(pattern, query_lower)
            if directional_match:
                street = directional_match.group(1).strip()
                # Make sure it's not capturing service-related terms
                excluded_words = ['story', 'time', 'toddler', 'has', 'have', 'with', 'program', 'class', 'service']
                if not contains_excluded_words(street, excluded_words):
                    logging.info(f"Extracted directional street from query: '{street}'")
                    return street

        # --- PRIORITY 5: Street patterns with prepositions - IMPROVED ---
        preposition_patterns = [
            # More specific patterns that stop at context words
            r'near\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2}\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard))(?:\s|$)',
            r'close\s+to\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2}\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard))(?:\s|$)',
            r'on\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2}\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard))(?:\s+(?:on|at|in)\b|\s*$)',
            r'at\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2}\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard))(?:\s|$)',
            r'in\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2}\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard))(?:\s|$)',
            r'around\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2}\s+(?:street|st|avenue|ave|road|rd|blvd|boulevard))(?:\s|$)',
        ]
        
        # Skip "around" pattern if it's followed by time indicators
        if re.search(r'around\s+\d+\s*(am|pm|:\d+|o\'?clock)', query_lower):
            preposition_patterns = [p for p in preposition_patterns if 'around' not in p]

        for pattern in preposition_patterns:
            match = re.search(pattern, query_lower)
            if match:
                location_text = match.group(1).strip()
                logging.info(f"Found potential street with preposition pattern: '{location_text}'")
                
                # Enhanced validation for preposition patterns
                non_location_words = [
                    'form', 'tax', 'w2', 'w-2', '1099', 'statement', 'document', 'paper',
                    'apply', 'retirement', 'benefits', 'where', 'can',
                    'story', 'time', 'toddler', 'program', 'class', 'service'
                ]
                
                if not contains_excluded_words(location_text, non_location_words):
                    logging.info(f"Extracted street from preposition pattern: '{location_text}'")
                    return location_text
                else:
                    logging.info(f"Rejected street '{location_text}' due to non-location words")

        # --- PRIORITY 6: IMPROVED Simple location extraction ---
        simple_location_patterns = [
            # Patterns that handle multi-word locations better and stop at context words
            r'near\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})(?:\s+(?:has|have|with|on|at|in|is|are|handles|handle)\b|\s*$)',
            r'close\s+to\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})(?:\s+(?:has|have|with|on|at|in|is|are|handles|handle)\b|\s*$)',
            r'at\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})(?:\s+(?:has|have|with|on|at|in|is|are|handles|handle)\b|\s*$)',
            r'in\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})(?:\s+(?:has|have|with|on|at|in|is|are|handles|handle)\b|\s*$)',
            r'around\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,3})(?:\s+(?:has|have|with|on|at|in|is|are|handles|handle)\b|\s*$)',
        ]
        
        # Skip "around" pattern if it's followed by time indicators
        if re.search(r'around\s+\d+\s*(am|pm|:\d+|o\'?clock)', query_lower):
            simple_location_patterns = [p for p in simple_location_patterns if 'around' not in p]
        
        for pattern in simple_location_patterns:
            match = re.search(pattern, query_lower)
            if match:
                location_text = match.group(1).strip()
                # Clean up by removing trailing context words
                clean_location = extract_clean_location(location_text)
                
                # UPDATED: More lenient exclusion list - removed "the" as it's common in landmarks
                non_location_words = [
                    'form', 'tax', 'w2', 'w-2', '1099', 'statement', 'document', 'paper',
                    'apply', 'retirement', 'benefits', 'where', 'can',
                    'wednesday', 'monday', 'tuesday', 'thursday', 'friday', 'saturday', 'sunday',
                    'story', 'time', 'toddler', 'program', 'class', 'service'
                    # NOTE: Removed 'the' from excluded words to allow "Philadelphia Museum" etc.
                ]
                
                if not contains_excluded_words(clean_location, non_location_words) and len(clean_location.split()) >= 1:
                    # Additional validation: must contain at least one letter
                    if re.search(r'[a-zA-Z]', clean_location):
                        logging.info(f"Extracted simple location from query: '{clean_location}'")
                        return clean_location

        # --- PRIORITY 7: Distance-based patterns - IMPROVED ---
        distance_patterns = [
            r'within\s+\d+(?:\.\d+)?\s+(?:miles?|mi|km|blocks?)\s+of\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,4})(?:\s+(?:has|have|with|on|at|in)\b|\s*$)',
            r'\d+\s*(?:miles?|mi|km|blocks?)\s+(?:of|from)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,4})(?:\s+(?:has|have|with|on|at|in)\b|\s*$)',
        ]
        
        for pattern in distance_patterns:
            match = re.search(pattern, query_lower)
            if match:
                location_text = match.group(1).strip()
                clean_location = extract_clean_location(location_text)
                
                non_location_words = [
                    'form', 'tax', 'w2', 'w-2', '1099', 'statement', 'document', 'paper',
                    'apply', 'retirement', 'benefits', 'where', 'can',
                    'story', 'time', 'toddler', 'program', 'class', 'service'
                ]
                if not contains_excluded_words(clean_location, non_location_words):
                    logging.info(f"Extracted location from distance pattern: '{clean_location}'")
                    return clean_location
        
        logging.info("No location extracted from query")
        return None
    
    def get_distance_threshold(self, query):
        """
        Determine distance threshold based on query context.
        
        Args:
            query (str): User query to analyze for distance context
            
        Returns:
            float: Distance threshold in miles
        """
        query_lower = query.lower()
        
        # Extract explicit distance mentions
        distance_match = re.search(r'(\d+(?:\.\d+)?)\s*(miles?|mi|km|blocks?)', query_lower)
        if distance_match:
            value = float(distance_match.group(1))
            unit = distance_match.group(2)
            if 'km' in unit:
                return value * 0.621371  # Convert km to miles
            elif 'block' in unit:
                return value * 0.1  # Assume 10 blocks per mile
            else:
                return value
        
        # Use semantic thresholds
        for term, threshold in self.proximity_thresholds.items():
            if term in query_lower:
                return threshold
        
        # Default threshold
        return Config.DEFAULT_DISTANCE_THRESHOLD

    def create_spatial_context(self, user_coordinates, distance_threshold, location_text):
        """
        Create spatial context string for Cypher query generation.
        
        Args:
            user_coordinates (tuple): (latitude, longitude)
            distance_threshold (float): Distance threshold in miles
            location_text (str): Original location text from query
            
        Returns:
            str: Formatted spatial context for prompts
        """
        return f"""
USER LOCATION: {user_coordinates[0]}, {user_coordinates[1]} (geocoded from: {location_text})
DISTANCE THRESHOLD: {distance_threshold} miles
USER COORDINATES: user_latitude = {user_coordinates[0]}, user_longitude = {user_coordinates[1]}
DISTANCE THRESHOLD: distance_threshold = {distance_threshold}

SPATIAL QUERY INSTRUCTIONS:
- Include distance calculations in your Cypher query using the provided coordinates
- Filter results ONLY by the distance threshold (distance_miles <= {distance_threshold})
- DO NOT add location-based filters (street, city, zipcode, state) - distance filtering handles location
- Sort results by distance (closest first)
- Include distance_miles in the result set
- The location "{location_text}" has been geocoded to coordinates - use distance, not text matching
"""

    def create_spatial_info(self, location_text, user_coordinates, distance_threshold):
        """
        Create spatial information dictionary for memory storage.
        
        Args:
            location_text (str): Original location text
            user_coordinates (tuple): (latitude, longitude)
            distance_threshold (float): Distance threshold in miles
            
        Returns:
            dict: Spatial information dictionary
        """
        return {
            'location_text': location_text,
            'coordinates': user_coordinates,
            'distance_threshold': distance_threshold
        }