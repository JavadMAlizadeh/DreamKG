# Give a strict style to the response

import streamlit as st
import streamlit.components.v1 as components
import logging
import base64
from pathlib import Path
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time
import os
import re
from config import Config
from models.spatial_intelligence import SpatialIntelligence
from models.conversation_memory import ConversationMemory
from metrics import MetricsCollector  # Import the enhanced metrics collector
from database.neo4j_client import Neo4jClient
from services.query_service import QueryService  # Will use the enhanced version
from services.response_service import ResponseService
from services.google_sheets_logger import GoogleSheetsLogger

class OrganizationInfoApp:
    """
    Main application class with enhanced metrics tracking for all operations.
    Provides detailed insights into token usage, latency breakdowns, and processing times.
    """
    
    def __init__(self):
        """Initialize the application with enhanced metrics tracking."""
        # Setup logging and validate configuration
        self.log_filename = Config.setup_logging()
        Config.validate_config()
        
        # Initialize enhanced metrics collector first
        self.metrics = MetricsCollector()

        # Initialize Google Sheets logger
        try:
            self.sheets_logger = GoogleSheetsLogger()
            logging.info("Google Sheets logger initialized successfully")
        except Exception as e:
            logging.warning(f"Failed to initialize Google Sheets logger: {str(e)}")
            self.sheets_logger = None
        
        # Initialize core components
        self.spatial_intel = SpatialIntelligence()
        self.memory = ConversationMemory()
        self.neo4j_client = Neo4jClient()
        
        # Initialize services with enhanced metrics integration
        self.query_service = QueryService(
            self.neo4j_client, 
            self.spatial_intel, 
            self.memory,
            self.metrics  # Pass enhanced metrics collector to query service
        )
        self.response_service = ResponseService()
        
        logging.info("OrganizationInfoApp initialized with enhanced metrics tracking and Google Sheets logging")
    
    def log_session_to_sheets(self):
        """Log the current session data to Google Sheets."""
        if self.sheets_logger and self.sheets_logger.initialized:
            try:
                # Get current metrics data
                metrics_data = self.metrics.get_statistics()
                
                # Log to Google Sheets
                self.sheets_logger.log_session_data(self.log_filename, metrics_data)
                logging.info("Session data logged to Google Sheets successfully")
                
            except Exception as e:
                logging.error(f"Failed to log session to Google Sheets: {str(e)}")
        else:
            logging.warning("Google Sheets logger not available, skipping session log")

    def get_log_filename(self):
        """Get the current log filename."""
        return self.log_filename

    def read_log_file(self):
        """Read the current log file content."""
        try:
            import os
            if os.path.exists(self.log_filename):
                with open(self.log_filename, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                return "Log file not found."
        except Exception as e:
            return f"Error reading log file: {str(e)}"
    
    def _is_personal_location_query(self, user_query):
        """
        Check if query uses personal location references like 'near me', 'around me', 'close to me'.
        
        Args:
            user_query (str): User's question
            
        Returns:
            bool: True if query uses personal location references
        """
        query_lower = user_query.lower()
        
        personal_location_patterns = [
            r'\bnear\s+me\b',
            r'\baround\s+me\b', 
            r'\bclose\s+to\s+me\b',
            r'\bnearby\s+me\b',
            r'\bwithin.*of\s+me\b',
            r'\bmy\s+location\b',
            r'\bhere\b',
            r'\bwhere\s+I\s+am\b',
            r'\bmy\s+area\b',
            r'\bin\s+my\s+vicinity\b'
        ]
        
        for pattern in personal_location_patterns:
            if re.search(pattern, query_lower):
                logging.info(f"Personal location pattern detected: {pattern}")
                return True
        
        return False
    
    def process_user_request_for_streamlit(self, user_query, user_location=None):
        """
        Process user request and return both formatted response and raw data for mapping.
        
        Args:
            user_query (str): User's question
            user_location (tuple): User's coordinates (lat, lon) if available
            
        Returns:
            tuple: (formatted_response, raw_data)
        """
        # Log user location information
        if user_location:
            logging.info(f"User location received: Latitude: {user_location[0]}, Longitude: {user_location[1]}")
        else:
            logging.info("No user location available or permission denied")
        
        # Determine spatial processing approach based on scenarios
        should_call_spatial_intel = True
        final_coordinates = None
        
        # Check if this is a personal location query FIRST (before any other processing)
        is_personal_location = self._is_personal_location_query(user_query)
        
        if is_personal_location:
            # Personal location queries ("near me", "around me", etc.) should NEVER call spatial intelligence
            if user_location:
                # Scenario 3: Use user's location, don't call spatial intelligence
                logging.info("Scenario 3: User allowed location + personal reference - using user location directly")
                should_call_spatial_intel = False
                final_coordinates = user_location
            else:
                # Scenario 1 variant: No permission but personal reference - use City Hall as default
                logging.info("Scenario 1 variant: No location permission + personal reference - using City Hall as default")
                should_call_spatial_intel = False
                final_coordinates = (39.952335, -75.163789)  # City Hall coordinates
        else:
            # Not a personal location query - check for specific locations
            if user_location:
                # Scenario 4: User allowed location but mentioned specific area - use spatial intelligence
                logging.info("Scenario 4: User allowed location + specific area mentioned - using spatial intelligence")
                should_call_spatial_intel = True
            else:
                # User denied location access or location not available
                has_specific_location = self.spatial_intel.extract_location_from_query(user_query)
                if has_specific_location:
                    # Scenario 2: No permission + specific location mentioned - use spatial intelligence
                    logging.info("Scenario 2: No location permission + specific area mentioned - using spatial intelligence")
                    should_call_spatial_intel = True
                else:
                    # Scenario 1: No permission + no specific location - use City Hall as default
                    logging.info("Scenario 1: No location permission + no specific area - using City Hall as default")
                    should_call_spatial_intel = False
                    final_coordinates = (39.952335, -75.163789)  # City Hall coordinates
        
        # Process the query based on determined approach
        if should_call_spatial_intel:
            # Use original spatial intelligence processing
            response_content = self._process_user_query_with_enhanced_metrics(user_query)
        else:
            # Process without spatial intelligence but with coordinates
            response_content = self._process_user_query_with_coordinates(user_query, final_coordinates)
        
        # Get raw data for mapping by accessing the last query results
        raw_data = []
        if hasattr(self.memory, 'current_context') and self.memory.current_context:
            raw_data = self.memory.current_context
        
        return response_content, raw_data
    
    def _process_user_query_with_coordinates(self, user_query, coordinates):
        """
        Process user query with predefined coordinates without using spatial intelligence.
        
        Args:
            user_query (str): User's question
            coordinates (tuple): (latitude, longitude) to use for spatial queries
            
        Returns:
            str: Response content to display
        """
        logging.info("="*30)
        logging.info(f"Processing query with predefined coordinates: {coordinates}")
        
        # Start comprehensive metrics tracking
        query_id = self.metrics.start_query(user_query)
        
        try:
            # Check for special commands
            if user_query.lower() in ['help', 'h']:
                help_response = self.response_service.generate_help_response()
                return help_response['response']
            
            if user_query.lower() in ['metrics', 'stats', 'statistics']:
                try:
                    report = self.metrics.format_statistics_report()
                    return f"**Current Session Metrics:**\n```\n{report}\n```"
                except Exception as e:
                    return f"Error generating metrics: {str(e)}"
            
            # Check if this is a simple follow-up that can use cached results
            if (self.query_service.is_simple_followup(user_query) and 
                self.memory.should_use_memory(user_query)):
                
                logging.info("Detected simple follow-up query - using cached results")
                return self._handle_cached_query_with_enhanced_metrics(user_query)
            
            # Process query directly with coordinates (bypass spatial intelligence)
            query_result = self.query_service.process_query_with_coordinates(user_query, coordinates)
            
            # Record memory usage with timing
            self.metrics.record_memory_usage(
                used_memory=query_result.get('used_memory', False),
                is_focused=self.query_service.is_focused_followup(user_query),
                duration=query_result.get('memory_duration')
            )
            
            # Record processing time breakdowns
            if query_result.get('neo4j_duration'):
                self.metrics.record_processing_time('neo4j', query_result['neo4j_duration'])
            
            if not query_result['success']:
                # Record failed query with enhanced error tracking
                self.metrics.record_query_result(
                    success=False,
                    error_message=query_result.get('error', 'Unknown error'),
                    neo4j_duration=query_result.get('neo4j_duration', 0.0)
                )
                return self._handle_query_error(query_result)
            
            # Record successful query result with comprehensive metrics
            results = query_result['results']
            self.metrics.record_query_result(
                success=True,
                result_count=len(results) if results else 0,
                expanded_search=query_result.get('expanded_radius', False),
                cypher_query=query_result.get('cypher_query'),
                neo4j_duration=query_result.get('neo4j_duration', 0.0)
            )
            
            # Generate response
            response_result = self._generate_response(user_query, query_result)
            
            if not response_result['success']:
                return self._handle_response_error(response_result)
            
            # Display results with enhanced performance information
            return self._format_results_with_performance_info(response_result, query_result)
            
        except Exception as e:
            # Record exception with enhanced error tracking
            self.metrics.record_query_result(
                success=False,
                error_message=str(e),
                neo4j_duration=0.0
            )
            logging.error(f"Query processing failed with exception: {str(e)}")
            return f"Sorry, there was an error processing your query: {str(e)}"
        
        finally:
            # Always end metrics tracking
            self.metrics.end_query()
            self._show_enhanced_metrics()
    
    def _show_enhanced_metrics(self):
        """Display comprehensive session metrics to the user."""
        try:
            # Log comprehensive metrics to file (same as original main.py)
            self.metrics.log_statistics_to_file()
            
        except Exception as e:
            logging.error(f"Error in enhanced metrics display: {str(e)}")
    
    def _process_user_query_with_enhanced_metrics(self, user_query):
        """
        Process a single user query through the complete pipeline with enhanced metrics tracking.
        
        Args:
            user_query (str): User's question
            
        Returns:
            str: Response content to display
        """
        logging.info("="*30)
        logging.info(f"Processing new user query: {user_query}")
        
        # Start comprehensive metrics tracking
        query_id = self.metrics.start_query(user_query)
        
        try:
            # Check for special commands
            if user_query.lower() in ['help', 'h']:
                help_response = self.response_service.generate_help_response()
                return help_response['response']
            
            if user_query.lower() in ['metrics', 'stats', 'statistics']:
                try:
                    report = self.metrics.format_statistics_report()
                    return f"**Current Session Metrics:**\n```\n{report}\n```"
                except Exception as e:
                    return f"Error generating metrics: {str(e)}"
            
            # Check if this is a simple follow-up that can use cached results
            if (self.query_service.is_simple_followup(user_query) and 
                self.memory.should_use_memory(user_query)):
                
                logging.info("Detected simple follow-up query - using cached results")
                return self._handle_cached_query_with_enhanced_metrics(user_query)
            
            # Process query through full pipeline with enhanced metrics
            query_result = self.query_service.process_query(user_query)
            
            # Record spatial detection with enhanced metrics
            if 'spatial_info' in query_result and query_result['spatial_info']:
                spatial_info = query_result['spatial_info']
                self.metrics.record_spatial_detection(
                    is_spatial=query_result.get('is_spatial', False),
                    location_text=spatial_info.get('location_text'),
                    distance_threshold=spatial_info.get('distance_threshold')
                )
            elif query_result.get('is_spatial', False):
                # Spatial query detected but geocoding might have failed
                self.metrics.record_spatial_detection(is_spatial=True)
            
            # Record memory usage with timing
            self.metrics.record_memory_usage(
                used_memory=query_result.get('used_memory', False),
                is_focused=self.query_service.is_focused_followup(user_query),
                duration=query_result.get('memory_duration')
            )
            
            # Record processing time breakdowns
            if query_result.get('neo4j_duration'):
                self.metrics.record_processing_time('neo4j', query_result['neo4j_duration'])
            
            if query_result.get('spatial_duration'):
                self.metrics.record_processing_time('spatial', query_result['spatial_duration'])
            
            if not query_result['success']:
                # Record failed query with enhanced error tracking
                self.metrics.record_query_result(
                    success=False,
                    error_message=query_result.get('error', 'Unknown error'),
                    neo4j_duration=query_result.get('neo4j_duration', 0.0)
                )
                return self._handle_query_error(query_result)
            
            # Record successful query result with comprehensive metrics
            results = query_result['results']
            self.metrics.record_query_result(
                success=True,
                result_count=len(results) if results else 0,
                expanded_search=query_result.get('expanded_radius', False),
                cypher_query=query_result.get('cypher_query'),
                neo4j_duration=query_result.get('neo4j_duration', 0.0)
            )
            
            # Generate response
            response_result = self._generate_response(user_query, query_result)
            
            if not response_result['success']:
                return self._handle_response_error(response_result)
            
            # Display results with enhanced performance information
            return self._format_results_with_performance_info(response_result, query_result)
            
        except Exception as e:
            # Record exception with enhanced error tracking
            self.metrics.record_query_result(
                success=False,
                error_message=str(e),
                neo4j_duration=0.0
            )
            logging.error(f"Query processing failed with exception: {str(e)}")
            return f"Sorry, there was an error processing your query: {str(e)}"
        
        finally:
            # Always end metrics tracking but DON'T show metrics after every query
            self.metrics.end_query()
            self._show_enhanced_metrics()  # This was causing the extra report
    
    def _handle_cached_query_with_enhanced_metrics(self, user_query):
        """
        Handle queries that use cached results from memory with enhanced metrics tracking.
        
        Args:
            user_query (str): User query
            
        Returns:
            str: Response content
        """
        cached_results = self.query_service.get_cached_results()
        
        # Record memory usage with timing
        import time
        memory_start_time = time.time()
        is_focused = self.query_service.is_focused_followup(user_query)
        memory_duration = time.time() - memory_start_time
        
        self.metrics.record_memory_usage(
            used_memory=True,
            is_focused=is_focused,
            duration=memory_duration
        )
        
        if not cached_results:
            self.metrics.record_query_result(
                success=False,
                error_message="No cached results available",
                neo4j_duration=0.0
            )
            return "No previous results available. Please ask a new question."
        
        # Determine response type
        is_spatial = self.query_service.has_spatial_memory()
        
        response_result = self.response_service.generate_response(
            user_query, cached_results, is_spatial=is_spatial, is_focused=is_focused
        )
        
        if response_result['success']:
            self.metrics.record_query_result(
                success=True,
                result_count=len(cached_results),
                neo4j_duration=0.0  # No database query for cached results
            )
            return response_result['response']
        else:
            self.metrics.record_query_result(
                success=False,
                error_message="Failed to generate response for cached query",
                neo4j_duration=0.0
            )
            return "Sorry, I couldn't generate a response to your follow-up question."
    
    def _generate_response(self, user_query, query_result):
        """
        Generate response based on query results.
        
        Args:
            user_query (str): Original user query
            query_result (dict): Query processing result
            
        Returns:
            dict: Response generation result
        """
        results = query_result['results']
        is_spatial = query_result['is_spatial']
        used_memory = query_result['used_memory']
        
        # For follow-up queries using memory, check if focused response needed
        if used_memory:
            is_focused = self.query_service.is_focused_followup(user_query)
        else:
            is_focused = False
        
        return self.response_service.generate_response(
            user_query, results, is_spatial=is_spatial, is_focused=is_focused
        )
    
    def _handle_query_error(self, query_result):
        """Handle errors in query processing with enhanced error reporting."""
        error_message = query_result.get('error', 'Unknown error')
        
        if 'geocode' in error_message.lower():
            error_response = self.response_service.format_error_response(
                'geocoding', error_message
            )
        elif 'no results' in error_message.lower():
            error_response = self.response_service.format_error_response(
                'no_results', error_message
            )
        else:
            error_response = self.response_service.format_error_response(
                'query', error_message
            )
        
        return error_response['response']
    
    def _handle_response_error(self, response_result):
        """Handle errors in response generation."""
        error_message = response_result.get('error', 'Unknown error')
        logging.error(f"Response generation failed: {error_message}")
        return f"Sorry, there was an error generating the response: {error_message}"
    
    def _format_results_with_performance_info(self, response_result, query_result):
        """
        Format results with enhanced performance information for Streamlit.
        
        Args:
            response_result (dict): Response generation result
            query_result (dict): Query processing result
            
        Returns:
            str: Formatted response content
        """
        logging.info(f"Final Answer:\n\n{response_result['response']}")

        # Start with main response
        content = response_result['response']
        
        # Add helpful suggestions
        if query_result['results']:
            result_count = len(query_result['results'])
            suggestions = self.response_service.generate_suggestion_response(
                result_count=result_count,
                is_spatial=query_result['is_spatial'],
                used_memory=query_result['used_memory'],
                expanded_radius=query_result.get('expanded_radius', False),
                original_threshold=(query_result.get('spatial_info') or {}).get('distance_threshold'),
                expanded_threshold=query_result.get('expanded_threshold')
            )
            
            if suggestions:
                content += f"\n\n{suggestions}"
        
        return content
    
    def _cleanup(self):
        """Clean up resources and log final enhanced metrics."""
        try:
            # Log session to Google Sheets before cleanup - NEW
            self.log_session_to_sheets()
            
            if hasattr(self, 'neo4j_client'):
                self.neo4j_client.close()
                logging.info("Application cleanup completed with enhanced metrics and Google Sheets logging")
        except Exception as e:
            logging.error(f"Error during cleanup: {str(e)}")
    
    def get_stats(self):
        """
        Get comprehensive application statistics including enhanced metrics.
        
        Returns:
            dict: Application statistics with enhanced metrics
        """
        try:
            memory_stats = self.query_service.get_memory_stats()
            enhanced_metrics_stats = self.metrics.get_statistics()
            
            return {
                'memory': memory_stats,
                'database': {
                    'organizations': self.neo4j_client.get_node_count('Organization'),
                    'locations': self.neo4j_client.get_node_count('Location'),
                    'services': self.neo4j_client.get_node_count('Service'),
                    'connection_ok': self.neo4j_client.test_connection()
                },
                'enhanced_metrics': enhanced_metrics_stats
            }
        except Exception as e:
            logging.error(f"Error getting enhanced stats: {str(e)}")
            return {'error': str(e)}
        
# --- Page Configuration ---
st.set_page_config(
    page_title="DreamKG",
    page_icon="logo.png",
    layout="centered",
)

def display_structured_response(response_data):
    """
    Display structured response data in Streamlit with proper formatting.
    
    Args:
        response_data: Either a string (old format) or dict (new structured format)
    """
    # Handle old format (string responses)
    if isinstance(response_data, str):
        st.markdown(response_data)
        return
    
    # Handle new structured format
    if isinstance(response_data, dict) and response_data.get('type') == 'structured':
        # Display intro text
        if response_data.get('intro'):
            st.markdown(response_data['intro'])
            st.write("")  # Empty line
        
        # Display each organization
        for org in response_data.get('organizations', []):
            # Organization header - numbered with bold name
            st.markdown(f"**{org['number']}. {org['name']}**")
            
            # Combine all main details with black bullets (●) into one block for tighter spacing
            main_items_text = ""
            for item in org.get('main_items', []):
                main_items_text += f"● {item}<br>"
            
            # Hours section with black bullet and white sub-bullets (compressed)
            if org.get('hours'):
                main_items_text += "● Hours:<br>"
                for day, hours in org['hours'].items():
                    main_items_text += f"&nbsp;&nbsp;&nbsp;&nbsp;○ {day}: {hours}<br>"
            
            # Services section with black bullet and white sub-bullets (compressed)
            services = org.get('services', {})
            if services.get('free') or services.get('paid'):
                main_items_text += "● Services:<br>"
                
                # Free services
                for service in services.get('free', []):
                    main_items_text += f"&nbsp;&nbsp;&nbsp;&nbsp;○ Free: {service}<br>"
                
                # Paid services
                for service in services.get('paid', []):
                    main_items_text += f"&nbsp;&nbsp;&nbsp;&nbsp;○ Paid: {service}<br>"
            
            # Display all content for this organization in one markdown block
            if main_items_text:
                st.markdown(main_items_text.rstrip('<br>'), unsafe_allow_html=True)
            
            # Add spacing between organizations only
            st.write("")
    
    else:
        # Fallback - treat as string
        st.markdown(str(response_data))

# --- Geolocation Component ---
def get_user_location():
    """
    Get user's current location using browser geolocation API.
    Automatically requests permission without button - fresh request each time.
    """
    geolocation_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Location Request</title>
    </head>
    <body>
        <div id="location-status" style="display: none;">
            <div id="status-message"></div>
        </div>

        <script>
        function requestLocationAutomatically() {
            const statusMsg = document.getElementById('status-message');
            
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    function(position) {
                        const lat = position.coords.latitude.toFixed(6);
                        const lon = position.coords.longitude.toFixed(6);
                        
                        // Store fresh location data
                        localStorage.setItem('streamlit_user_lat', lat);
                        localStorage.setItem('streamlit_user_lon', lon);
                        localStorage.setItem('streamlit_location_granted', 'true');
                        localStorage.setItem('streamlit_location_time', new Date().toISOString());
                        
                        // Update parent page URL WITHOUT reloading
                        try {
                            const parentUrl = new URL(window.parent.location);
                            parentUrl.searchParams.set('lat', lat);
                            parentUrl.searchParams.set('lon', lon);
                            parentUrl.searchParams.set('location_granted', 'true');
                            window.parent.history.replaceState({}, '', parentUrl);
                            
                            console.log('Location stored successfully:', lat, lon);
                            
                        } catch(e) {
                            console.log('Could not update parent URL:', e);
                        }
                        
                        // Immediately hide the status message and component
                        statusMsg.innerHTML = '';
                        document.getElementById('location-status').style.display = 'none';
                    },
                    function(error) {
                        // Clear any location data on error
                        localStorage.removeItem('streamlit_user_lat');
                        localStorage.removeItem('streamlit_user_lon');
                        localStorage.removeItem('streamlit_location_granted');
                        localStorage.setItem('streamlit_location_error', error.message);
                        
                        console.error('Geolocation error:', error);
                        
                        // Immediately hide the status message and component on error too
                        statusMsg.innerHTML = '';
                        document.getElementById('location-status').style.display = 'none';
                    },
                    {
                        enableHighAccuracy: true,
                        timeout: 10000,
                        maximumAge: 0  // Always request fresh location, don't use cached
                    }
                );
            } else {
                console.log('Geolocation not supported');
                // Immediately hide if not supported
                statusMsg.innerHTML = '';
                document.getElementById('location-status').style.display = 'none';
            }
        }
        
        // Automatically request location when page loads
        window.onload = function() {
            // Clear any existing location data when app loads for fresh request
            localStorage.removeItem('streamlit_user_lat');
            localStorage.removeItem('streamlit_user_lon');
            localStorage.removeItem('streamlit_location_granted');
            localStorage.removeItem('streamlit_location_error');
            localStorage.removeItem('streamlit_location_time');
            
            // Automatically trigger location request
            requestLocationAutomatically();
        };
        </script>
    </body>
    </html>
    """
    
    # Always show location component for automatic request - but with zero height
    components.html(geolocation_html, height=0)

# --- Logo and Header ---
@st.cache_data
def get_img_as_base64(file):
    if not Path(file).is_file():
        return None
    with open(file, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

img = get_img_as_base64("logo.png")

if img:
    st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
            <img src="data:image/png;base64,{img}" width="50">
            <h1 style="margin: 0;">DreamKG</h1>
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    st.title("DreamKG")

st.markdown("---")

# Request user location on first visit - moved to after the welcome message
# This ensures no space appears between header and welcome text

st.markdown("""
Welcome! Ask a question about **Food Banks**, **Mental Health Centers**, **Shelters**, **Public Libraries**, and **Social Security offices** in Philadelphia.

**Examples:**
* Looking for a library on West Lehigh Avenue that has free wi-fi on a Tuesday.
* Where can I apply for retirement benefits on Aramingo Avenue on a Wednesday?
* Looking for a food bank near me.
* Looking for a mental health center in my area.
* Looking for a shelter on North Broad Street.

**Before You Continue:**
* Please enable location access to view results near you.<br>        
* Options are sorted by proximity to your target location.<br>
* Your session activity will be securely logged and transmitted to our servers to support monitoring and service improvements.
""", unsafe_allow_html=True)

# Request user location after the welcome message to avoid any spacing issues
get_user_location()

st.markdown("---")

# --- Application Initialization ---
@st.cache_resource
def init_app():
    """Initializes the OrganizationInfoApp and returns the instance."""
    try:
        app_instance = OrganizationInfoApp()
        return app_instance
    except Exception as e:
        st.error(f"Application failed to initialize. Please check your configurations. Error: {e}", icon="🚨")
        return None

app = init_app()

# --- Configuration for Directions ---
DIRECTIONS_HEIGHT = 500  # Height for directions iframe
PLACEHOLDER_HEIGHT = 350  # Height for placeholder when directions fail to load

# --- Embedded Directions Display ---
def get_user_location_for_directions():
    """
    Get user's current location for directions based on priority order.
    Priority: 1. Custom start location, 2. User's actual location, 3. Query location, 4. Default (City Hall)
    """
    # Priority 1: Check if user has set a custom starting point
    if 'custom_start_location' in st.session_state and st.session_state.custom_start_location:
        custom_lat, custom_lon = st.session_state.custom_start_location
        logging.info(f"Using custom start location for directions: {custom_lat}, {custom_lon}")
        return st.session_state.custom_start_location
    
    # Priority 2: Check if we have user's actual location (from geolocation)
    if 'user_location' in st.session_state and st.session_state.user_location:
        user_lat, user_lon = st.session_state.user_location
        logging.info(f"Using user's actual location for directions: {user_lat}, {user_lon}")
        return st.session_state.user_location
    
    # Priority 3: Check if there's a query-based location from the last search
    if 'query_location' in st.session_state and st.session_state.query_location:
        query_lat, query_lon = st.session_state.query_location
        logging.info(f"Using query-based location for directions: {query_lat}, {query_lon}")
        return st.session_state.query_location
    
    # Priority 4: Default to Philadelphia City Hall coordinates
    logging.info("Using default City Hall location for directions: 39.952335, -75.163789")
    return 39.952335, -75.163789  # City Hall coordinates

def extract_user_location_from_query(query, raw_data, app_instance=None):
    """
    Extract the user's mentioned location from their query using the existing SpatialIntelligence system.
    """
    # Use the app's spatial intelligence if available
    if app_instance and hasattr(app_instance, 'spatial_intel'):
        # Check if it's a spatial query first
        if app_instance.spatial_intel.detect_spatial_query(query):
            # Extract location using the existing spatial intelligence
            location_text = app_instance.spatial_intel.extract_location_from_query(query)
            if location_text:
                return location_text
    
    # Fallback: try to get from raw_data if spatial processing already happened
    if raw_data:
        for record in raw_data:
            # Check if this record has distance info (indicating spatial query)
            if 'distance_miles' in record:
                # Check session state for last spatial info
                if hasattr(st.session_state, 'last_spatial_location'):
                    return st.session_state.last_spatial_location
    
    return None

@st.cache_data
def geocode_start_location(address):
    """Geocode a starting address to coordinates."""
    try:
        geolocator = Nominatim(user_agent="dream_kg_directions_app", timeout=10)
        time.sleep(1)  # Rate limiting
        
        # Add Philadelphia context for better results
        search_query = f"{address}, Philadelphia, PA" if "Philadelphia" not in address else address
        location = geolocator.geocode(search_query)
        
        if location:
            return location.latitude, location.longitude, location.address
        else:
            return None, None, None
            
    except Exception as e:
        return None, None, None

def display_embedded_directions_for_all_organizations(raw_data, user_query="", app_instance=None, message_index=None):
    """
    Display embedded directions with dropdown to select from all found organizations.
    
    Args:
        raw_data (list): All organizations found in the search
        user_query (str): The original user query to extract location from
        app_instance: The main app instance to access spatial intelligence
        message_index (int): Index of the message to make keys unique
    """
    if not raw_data:
        return
    
    # Create unique key suffix based on message index or current time
    key_suffix = f"_{message_index}" if message_index is not None else f"_{int(time.time() * 1000)}"
    
    try:
        # Extract user's mentioned location using existing spatial intelligence
        query_location_text = extract_user_location_from_query(user_query, raw_data, app_instance)
        
        # If we found a location in the query and haven't set a custom location yet, use it as default
        if query_location_text and 'custom_start_location' not in st.session_state:
            # Use the app's spatial intelligence for geocoding if available
            if app_instance and hasattr(app_instance, 'spatial_intel'):
                query_coordinates = app_instance.spatial_intel.geocode_location(query_location_text)
                if query_coordinates:
                    st.session_state.query_location = query_coordinates
                    st.session_state.query_location_name = query_location_text
                    st.session_state.query_location_text = query_location_text
            else:
                # Fallback to our geocoding function
                query_lat, query_lon, query_full_address = geocode_start_location(query_location_text)
                if query_lat and query_lon:
                    st.session_state.query_location = (query_lat, query_lon)
                    st.session_state.query_location_name = query_full_address or query_location_text
                    st.session_state.query_location_text = query_location_text
        
        # Prepare organization data with geocoded addresses
        org_options = []
        org_data = {}
        
        for record in raw_data:
            # Get organization name from different possible formats
            org_name = (
                record.get('o.name') or 
                record.get('name') or 
                record.get('organizationName') or 
                (record.get('org', {}).get('name') if isinstance(record.get('org'), dict) else record.get('org')) or
                (record.get('o', {}).get('name') if isinstance(record.get('o'), dict) else record.get('o'))
            )
            
            if org_name:
                # Try to get address information
                address = (
                    record.get('l.street') or 
                    record.get('street') or 
                    record.get('streetAddress') or 
                    record.get('address')
                )
                
                city = (
                    record.get('l.city') or 
                    record.get('city') or
                    'Philadelphia'  # Default city
                )
                
                state = (
                    record.get('l.state') or 
                    record.get('state') or 
                    'PA'  # Default state
                )
                
                zipcode = (
                    record.get('l.zipcode') or 
                    record.get('zipcode') or 
                    record.get('zipCode') or 
                    ''
                )
                
                if address:
                    # Build full address
                    full_address = f"{address}"
                    if city:
                        full_address += f", {city}"
                    if state:
                        full_address += f", {state}"
                    if zipcode:
                        full_address += f" {zipcode}"
                    
                    full_address = full_address.strip()
                    
                    # Try to geocode this address
                    lat, lon = geocode_address(full_address, org_name)
                    if lat is not None and lon is not None:
                        org_options.append(org_name)
                        org_data[org_name] = {
                            'lat': lat,
                            'lon': lon,
                            'address': full_address,
                            'record': record
                        }
        
        if not org_options:
            st.warning("No organizations with valid addresses found for directions.")
            return
        
        # Create the main directions interface
        st.markdown("### Directions to")
        
        # Organization selector dropdown with unique key
        selected_org = st.selectbox(
            "Select destination:",
            options=org_options,
            index=0,
            key=f"destination_selector{key_suffix}",
            label_visibility="collapsed"
        )
        
        if selected_org and selected_org in org_data:
            org_info = org_data[selected_org]
            lat, lon = org_info['lat'], org_info['lon']
            
            # Determine what to show in the text input placeholder and value
            default_location_text = ""
            placeholder_text = "e.g., 1234 Market Street, Philadelphia"
            
            # Priority-based location text for input field
            if 'custom_start_location' in st.session_state and st.session_state.custom_start_location:
                # Custom location set by user
                custom_lat, custom_lon = st.session_state.custom_start_location
                default_location_text = st.session_state.get('custom_start_location_name', f"Custom ({custom_lat:.4f}, {custom_lon:.4f})")
                placeholder_text = f"Custom location: {default_location_text}"
            elif 'user_location' in st.session_state and st.session_state.user_location:
                # User's actual location is available
                user_lat, user_lon = st.session_state.user_location
                default_location_text = f"My Location ({user_lat:.4f}, {user_lon:.4f})"
                placeholder_text = f"Using your location: {user_lat:.4f}, {user_lon:.4f}"
            elif 'query_location_text' in st.session_state:
                # Query-based location
                default_location_text = st.session_state.query_location_text
                placeholder_text = f"From query: {st.session_state.query_location_text}"

            
            # Simple starting location input - full width
            col1, col2 = st.columns([4, 1])
            with col1:
                # Show different help text based on what location we're using
                help_text = "You can change this starting point if needed"
                if 'user_location' in st.session_state and st.session_state.user_location:
                    help_text = "Using your actual location. You can override this with a custom address."
                
                custom_address = st.text_input(
                    "Starting location:",
                    value=default_location_text,
                    placeholder=placeholder_text,
                    key=f"start_location_all_orgs{key_suffix}",
                    help=help_text,
                    label_visibility="visible"
                )
            with col2:
                st.markdown("<br>", unsafe_allow_html=True)
                # Change button text based on context
                button_text = "Update" if default_location_text else "Set Location"
                set_location = st.button(button_text, key=f"set_start_all_orgs{key_suffix}", use_container_width=True)
            
            # Handle location setting/updating
            if set_location and custom_address:
                # Don't geocode if user is trying to use the same location that's already set
                current_user_loc = st.session_state.get('user_location')
                if current_user_loc and custom_address.startswith("My Location"):
                    st.info("✅ Already using your current location for directions.")
                else:
                    with st.spinner("Finding location..."):
                        start_lat, start_lon, full_address = geocode_start_location(custom_address)
                        
                        if start_lat and start_lon:
                            st.session_state.custom_start_location = (start_lat, start_lon)
                            st.session_state.custom_start_location_name = full_address or custom_address
                            logging.info(f"Custom start location set: {full_address or custom_address} ({start_lat}, {start_lon})")
                            st.success(f"✅ Starting point updated to: {full_address or custom_address}")
                            st.rerun()
                        else:
                            st.error("⚠ Could not find that address. Please try a different format.")
            elif set_location and not custom_address:
                st.warning("Please enter an address first.")
            
            # Show clear indication of which location is being used for directions
            current_start_lat, current_start_lon = get_user_location_for_directions()
            location_source = "City Hall (default)"
            if 'custom_start_location' in st.session_state and st.session_state.custom_start_location == (current_start_lat, current_start_lon):
                location_source = "Custom location"
            elif 'user_location' in st.session_state and st.session_state.user_location == (current_start_lat, current_start_lon):
                location_source = "Your actual location"
            elif 'query_location' in st.session_state and st.session_state.query_location == (current_start_lat, current_start_lon):
                location_source = "Query location"
            
            # Get user location for directions
            user_lat, user_lon = get_user_location_for_directions()
            
            # Transportation mode selector (simplified) with unique keys
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                walking = st.button("🚶🏽 Walking", key=f"walking_all_orgs{key_suffix}", use_container_width=True)
            with col2:
                driving = st.button("🚗 Driving", key=f"driving_all_orgs{key_suffix}", use_container_width=True)
            with col3:
                cycling = st.button("🚴‍♀️ Cycling", key=f"cycling_all_orgs{key_suffix}", use_container_width=True)
            with col4:
                transit = st.button("🚌 Transit", key=f"transit_all_orgs{key_suffix}", use_container_width=True)

            # Determine transportation mode
            transport_mode = "walking"  # Default to walking
            
            if driving:
                transport_mode = "driving"
                st.session_state["global_transport_mode"] = "driving"
            elif cycling:
                transport_mode = "bicycling"
                st.session_state["global_transport_mode"] = "bicycling"
            elif transit:
                transport_mode = "transit"
                st.session_state["global_transport_mode"] = "transit"
            elif walking:
                transport_mode = "walking"
                st.session_state["global_transport_mode"] = "walking"
            else:
                # Check if we have a saved global mode
                saved_mode = st.session_state.get("global_transport_mode", "walking")
                transport_mode = saved_mode
            
            # Create directions embed URL with transportation mode
            google_api_key = getattr(Config, 'GOOGLE_MAPS_API_KEY', None)
            
            if google_api_key:
                # Use Google Maps Directions API embed (FREE)
                directions_url = f"https://www.google.com/maps/embed/v1/directions?key={google_api_key}&origin={user_lat},{user_lon}&destination={lat},{lon}&mode={transport_mode}"
            else:
                # Fallback directions embed with mode
                directions_url = f"https://maps.google.com/maps?saddr={user_lat},{user_lon}&daddr={lat},{lon}&dirflg={'w' if transport_mode == 'walking' else 'r' if transport_mode == 'transit' else 'b' if transport_mode == 'bicycling' else 'd'}&output=embed"
            
            try:
                # Display directions map
                st.markdown(f"""
                <div style="border: 2px solid #e0e0e0; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 15px;">
                    <iframe 
                        src="{directions_url}" 
                        width="100%" 
                        height="{DIRECTIONS_HEIGHT}" 
                        style="border:0;" 
                        allowfullscreen="" 
                        loading="lazy" 
                        referrerpolicy="no-referrer-when-downgrade">
                    </iframe>
                </div>
                """, unsafe_allow_html=True)
                
                # Embed Street View right after the map using your exact format
                street_view_embed_url = f"https://www.google.com/maps/embed?pb=!1m0!4v1723910100000!6m8!1m7!1sCAoSLEFGMVFpcE5fU3lzY1Z3b1hXZ2ZkR0hGd2VnU0Z1dHlJZ1F4b2Z0b2J3!2m2!1d{lat}!2d{lon}!3f75!4f0!5f0.78"
                
                st.components.v1.html(
                    f"""
                    <iframe
                      src="{street_view_embed_url}"
                      width="100%"
                      height="600"
                      style="border:0;"
                      allowfullscreen=""
                      loading="lazy"
                      referrerpolicy="no-referrer-when-downgrade">
                    </iframe>
                    """,
                    height=600,
                )
                
            except Exception as e:
                # Fallback directions display
                st.error("Directions embed failed. Here are alternative options:")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown(f"""
                    **🚗 Driving Directions:**
                        [Open in Google Maps](https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={lat},{lon}&travelmode={transport_mode})
                    """)
                
                with col2:
                    st.markdown(f"""
                    **🗺️ Street View:**
                    [View Location](https://www.google.com/maps/@{lat},{lon},3a,75y,0h,90t/data=!3m7!1e1!3m5!1s!2e0!6s!7i13312!8i6656)
                    """)
                
                # Show basic route information
                st.markdown(f"""
                <div style="padding: 15px; background-color: #f0f2f6; border-radius: 8px; margin-top: 10px;">
                    <h4>Route Summary</h4>
                    <p><strong>To:</strong> {selected_org}</p>
                </div>
                """, unsafe_allow_html=True)
            
    except Exception as e:
        st.error(f"Error displaying directions: {e}")
        
        # Emergency fallback
        st.markdown(f"""
        <div style="padding: 20px; background-color: #f0f2f6; border-radius: 8px; text-align: center;">
            <h4>Organizations Found</h4>
            <p>Unable to display directions. Please try refreshing.</p>
        </div>
        """, unsafe_allow_html=True)

# --- Geocoding Function with Caching ---
@st.cache_data
def geocode_address(address, org_name=None):
    """Converts an address string into latitude and longitude."""
    try:
        geolocator = Nominatim(user_agent="dream_kg_map_app_v2", timeout=10)
        time.sleep(1.5)  # Increased delay to avoid rate limiting
        
        # Try the full address first
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
        
        # If full address fails, try with just street and city
        if "Philadelphia" in address:
            simplified_address = address.split(",")[0] + ", Philadelphia, PA"
            location = geolocator.geocode(simplified_address)
            if location:
                return location.latitude, location.longitude
        
        # If that fails, try even more simplified
        if "Philadelphia" in address:
            very_simple = address.split(",")[0] + ", Philadelphia"
            location = geolocator.geocode(very_simple)
            if location:
                return location.latitude, location.longitude
        
        # If address fails completely, try the organization name + Philadelphia
        if org_name:
            org_location = geolocator.geocode(f"{org_name}, Philadelphia, PA")
            if org_location:
                return org_location.latitude, org_location.longitude
                
    except Exception as e:
        # Only show warning in debug, not to user
        pass
    return None, None

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Check for location data using simplified method - no auto-reload
def check_and_store_location():
    """Check for location data from JavaScript and store it in session state - no refresh loops."""
    location_found = False
    
    # Only check URL parameters - remove auto-reload scripts
    if st.query_params.get("location_granted") == "true":
        try:
            lat = float(st.query_params.get("lat", 0))
            lon = float(st.query_params.get("lon", 0))
            if lat != 0 and lon != 0 and 'user_location' not in st.session_state:
                st.session_state.user_location = (lat, lon)
                logging.info(f"User location permission granted: Latitude: {lat}, Longitude: {lon}")
                logging.info(f"Location successfully stored in session state")
                location_found = True
        except (ValueError, TypeError):
            logging.warning("Invalid location coordinates in URL parameters")
    
    return location_found

# Call the location checker (simplified - no refresh loops)
location_detected = check_and_store_location()

# Session state logging - but no user notification
if 'user_location' in st.session_state and 'location_session_logged' not in st.session_state:
    user_lat, user_lon = st.session_state.user_location
    logging.info(f"User location available in session state: Latitude: {user_lat}, Longitude: {user_lon}")
    st.session_state.location_session_logged = True

# Display previous messages and directions from history
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        display_structured_response(message["content"])
        # For historical messages, check if we have raw data to display directions
        if message.get("raw_data"):
            display_embedded_directions_for_all_organizations(message["raw_data"], "", app, message_index=idx)

# --- Log Download Function ---
def display_log_download_button(app_instance):
    """Display the log file download button."""
    if not app_instance:
        return
    
    # Get log filename and content
    log_filename = app_instance.get_log_filename()
    
    # Read log file content
    log_content = app_instance.read_log_file()
    
    # Create download button that spans the full width like chat input
    st.download_button(
        label="📥 Download Session Log",
        data=log_content,
        file_name=os.path.basename(log_filename),
        mime="text/plain",
        use_container_width=True,
        help="Download the session log file with all processing details"
    )

# --- Main Interaction Logic ---
if app:
    if prompt := st.chat_input("What are you looking for, where, and when?"):
        
        # --- Clear previous location settings for a fresh query ---
        if 'custom_start_location' in st.session_state:
            del st.session_state['custom_start_location']
        if 'custom_start_location_name' in st.session_state:
            del st.session_state['custom_start_location_name']
        if 'query_location' in st.session_state:
            del st.session_state['query_location']
        if 'query_location_name' in st.session_state:
            del st.session_state['query_location_name']
        if 'query_location_text' in st.session_state:
            del st.session_state['query_location_text']
        # --- End of clearing location settings ---
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            location_coords = None
            location_org = None
            has_location = False
            
            with st.spinner("Thinking..."):
                # Get user location from session state if available
                user_location = st.session_state.get('user_location')
                
                # Process query with location information
                response, raw_data = app.process_user_request_for_streamlit(prompt, user_location)

                # --- AUTOMATIC GOOGLE SHEETS LOGGING ---
                try:
                    app.log_session_to_sheets()
                    logging.info("Session automatically logged to Google Sheets")
                except Exception as e:
                    logging.warning(f"Automatic Google Sheets logging failed: {str(e)}")
                
                # --- LOCATION DETECTION LOGIC ---
                if raw_data and response:
                    # Find the first organization with valid coordinates
                    for record in raw_data:
                        # Get organization name from different possible formats
                        org_name = (
                            record.get('o.name') or 
                            record.get('name') or 
                            record.get('organizationName') or 
                            (record.get('org', {}).get('name') if isinstance(record.get('org'), dict) else record.get('org')) or
                            (record.get('o', {}).get('name') if isinstance(record.get('o'), dict) else record.get('o'))
                        )
                        
                        # Only proceed if we have an organization name and it's mentioned in the response
                        if org_name and org_name in response:
                            # Try to get address information
                            address = (
                                record.get('l.street') or 
                                record.get('street') or 
                                record.get('streetAddress') or 
                                record.get('address')
                            )
                            
                            city = (
                                record.get('l.city') or 
                                record.get('city') or
                                'Philadelphia'  # Default city
                            )
                            
                            state = (
                                record.get('l.state') or 
                                record.get('state') or 
                                'PA'  # Default state
                            )
                            
                            zipcode = (
                                record.get('l.zipcode') or 
                                record.get('zipcode') or 
                                record.get('zipCode') or 
                                ''
                            )
                            
                            if address:
                                # Build full address
                                full_address = f"{address}"
                                if city:
                                    full_address += f", {city}"
                                if state:
                                    full_address += f", {state}"
                                if zipcode:
                                    full_address += f" {zipcode}"
                                
                                full_address = full_address.strip()
                                
                                # Try to geocode this address
                                lat, lon = geocode_address(full_address, org_name)
                                if lat is not None and lon is not None:
                                    location_coords = [lat, lon]
                                    location_org = org_name
                                    has_location = True
                                    break  # Found the first valid coordinates, stop looking

                # --- END OF LOCATION DETECTION LOGIC ---

                display_structured_response(response)
                
                # Display embedded directions for all organizations if available (current message)
                if raw_data:
                    current_message_index = len(st.session_state.messages)  # Use next index for current message
                    display_embedded_directions_for_all_organizations(raw_data, prompt, app, message_index=current_message_index)

        st.session_state.messages.append({
            "role": "assistant", 
            "content": response,
            "raw_data": raw_data  # Store raw data for directions
        })
    
    # Display log download button at the end of chat if there are messages
    if st.session_state.messages:
        display_log_download_button(app)
        
else:
    st.warning("Application is not available due to an initialization error.")


def main():
    """Main entry point for the Streamlit application."""
    try:
        # The app is already initialized and running above
        pass
        
    except Exception as e:
        st.error(f"Failed to start enhanced application: {str(e)}")
        logging.error(f"Enhanced application startup failed: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()