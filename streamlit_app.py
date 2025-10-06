# Deployment.

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
import uuid
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
    
    def __init__(self, session_id=None):
        """Initialize the application with enhanced metrics tracking."""
        # Generate session ID if not provided
        if session_id is None:
            import uuid
            session_id = str(uuid.uuid4())
        
        self.session_id = session_id
        
        # Setup logging with session ID
        self.log_filename = Config.setup_logging_with_session_id(session_id)
        Config.validate_config()
        
        # Initialize enhanced metrics collector first
        self.metrics = MetricsCollector(session_id=session_id)

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
        
        logging.info(f"OrganizationInfoApp initialized for session: {self.session_id}")
    
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
        """Read the current session's log file content - SECURE VERSION."""
        try:
            if hasattr(self, 'log_filename') and os.path.exists(self.log_filename):
                with open(self.log_filename, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                return "Log file not found for this session."
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

            # LIMIT TO TOP 5 RESULTS
            if query_result.get('results'):
                query_result['results'] = query_result['results'][:10]

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

            # LIMIT TO TOP 5 RESULTS
            if query_result.get('results'):
                query_result['results'] = query_result['results'][:10]

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

        # LIMIT TO TOP 5 RESULTS
        if cached_results:
            cached_results = cached_results[:10]
        
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
            str or dict: Formatted response content
        """
        logging.info(f"Final Answer:\n\n{response_result['response']}")

        # Get the main response
        content = response_result['response']
        
        # Add helpful suggestions only if we have results
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
                # BULLETPROOF: Handle any type of content safely
                try:
                    if isinstance(content, dict):
                        # For structured responses, add suggestions as a separate field
                        content['suggestions'] = suggestions
                    elif isinstance(content, str):
                        # For string responses, concatenate suggestions
                        content += f"\n\n{suggestions}"
                    else:
                        # Fallback: convert to string and concatenate
                        content = str(content) + f"\n\n{suggestions}"
                except Exception as e:
                    # Ultimate fallback: just return original content if anything fails
                    logging.warning(f"Could not add suggestions due to error: {e}")
                    # Return original content unchanged
                    pass
        
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

# Replace the display_structured_response function with this version (starting around line 644)

def display_structured_response(response_data, raw_data=None, user_query="", app_instance=None, message_index=None, start_coordinates=None, all_categories_data=None, current_category_index=None):
    """
    Display structured response with synchronized selection:
    - SHORT ANSWER: Shows the selected option
    - EXPANDABLE OPTIONS: All options with complete details (NO CHECKBOXES)
    - EXPANDABLE DIRECTIONS: Dropdown + Maps + directions (synced with dropdown only)
    
    MODIFIED: Removed all checkboxes - selection only via dropdown
    """
    # Use the query passed to this function directly - no session state storage needed
    effective_user_query = user_query if user_query else ""
    
    # Handle old format (string responses)
    if isinstance(response_data, str):
        st.markdown(response_data)
        return
        
    # Handle new structured format
    if isinstance(response_data, dict) and response_data.get('type') == 'structured':
        organizations = response_data.get('organizations', [])
        
        if not organizations:
            st.write("No organizations found.")
            return
        
        # Create unique key suffix based on message index or current time
        key_suffix = f"_{message_index}" if message_index is not None else f"_{int(time.time() * 1000)}"
        
        # Get organization names for selection
        org_names = [org['name'] for org in organizations]
        
        # SHARED SESSION STATE KEY - used by dropdown only now
        selection_key = f"destination_selector{key_suffix}"
        
        # Initialize selection if not set
        if selection_key not in st.session_state:
            st.session_state[selection_key] = org_names[0]  # Default to first organization
        
        # Find the selected organization by name
        selected_org_name = st.session_state[selection_key]
        selected_org = organizations[0]  # Default to first organization
        for org in organizations:
            if org['name'] == selected_org_name:
                selected_org = org
                break
        
        # ===== SHORT ANSWER - Dynamic and context-aware =====
        st.markdown(f"**{selected_org['name']}**")

        # Analyze query to determine what to show - USE EFFECTIVE QUERY
        query_lower = effective_user_query.lower() if effective_user_query else ""

        # Build concise info string with NO extra spacing
        short_text = ""

        # Distance (always show if spatial)
        for item in selected_org.get('main_items', []):
            if 'Distance:' in item:
                short_text += f"● {item}<br>"
                break

        # Phone (always show)
        for item in selected_org.get('main_items', []):
            if 'Phone:' in item:
                short_text += f"● {item}<br>"
                break

        # Address (always show)
        for item in selected_org.get('main_items', []):
            if 'Address:' in item:
                short_text += f"● {item}<br>"
                break

        # Hours - check if query mentions a specific day
        days_map = {
            'monday': 'Monday', 'mon': 'Monday',
            'tuesday': 'Tuesday', 'tue': 'Tuesday', 'tues': 'Tuesday',
            'wednesday': 'Wednesday', 'wed': 'Wednesday',
            'thursday': 'Thursday', 'thu': 'Thursday', 'thur': 'Thursday', 'thurs': 'Thursday',
            'friday': 'Friday', 'fri': 'Friday',
            'saturday': 'Saturday', 'sat': 'Saturday',
            'sunday': 'Sunday', 'sun': 'Sunday'
        }

        # Check if a specific day is mentioned in the query
        mentioned_day = None
        for day_variant, full_day in days_map.items():
            if day_variant in query_lower:
                mentioned_day = full_day
                break

        # SHORT ANSWER HOURS - show ONLY if a specific day is mentioned
        if mentioned_day:
            hours = selected_org.get('hours', {})
            if hours and mentioned_day in hours:
                short_text += f"● Time: {mentioned_day}, {hours[mentioned_day]}<br>"
    

        # Services - show ONLY requested services based on NORMALIZED query keywords
        services = selected_org.get('services', {})
        all_free = services.get('free', [])
        all_paid = services.get('paid', [])

        if all_free or all_paid:
            # Use the app's query service to get normalized keywords
            requested_services = set()
            
            if app_instance:
                # Method 1: Extract and normalize service keywords using the app's system
                try:
                    # Use the same normalization that happens in query processing
                    normalized_query = effective_user_query.lower()
                    
                    # Get keyword mappings from Config if available
                    from config import Config
                    
                    # Use Config.KEYWORD_NORMALIZATION if it exists, otherwise use fallback
                    if hasattr(Config, 'KEYWORD_NORMALIZATION'):
                        keyword_mappings = Config.KEYWORD_NORMALIZATION
                    else:
                        # Fallback keyword mappings
                        keyword_mappings = {
                            'stay': 'shelter',
                            'place to stay': 'shelter',
                            'somewhere to stay': 'shelter',
                            'food': 'food',
                            'eat': 'food',
                            'meal': 'food',
                            'library': 'library',
                            'book': 'library',
                            'wifi': 'library',
                            'internet': 'library',
                            'mental health': 'mental health',
                            'counseling': 'mental health',
                            'therapy': 'mental health',
                            'retirement': 'retirement'
                        }
                    
                    # Normalize keywords in the query
                    for raw_keyword, normalized_keyword in keyword_mappings.items():
                        if raw_keyword in normalized_query:
                            requested_services.add(normalized_keyword)
                            logging.info(f"Normalized '{raw_keyword}' to '{normalized_keyword}' for short answer")
                    
                    # Also check Config.CATEGORY_SERVICES with normalized matching
                    from config import Config
                    for category_services in Config.CATEGORY_SERVICES.values():
                        for service in category_services:
                            service_lower = service.lower()
                            # Check if normalized service appears in query
                            if service_lower in normalized_query:
                                requested_services.add(service_lower)
                            # Check individual words
                            query_words = normalized_query.split()
                            for word in query_words:
                                if word in service_lower.split():
                                    requested_services.add(service_lower)
                
                except Exception as e:
                    logging.warning(f"Could not normalize keywords: {e}")
                    # Fallback to original logic
                    from config import Config
                    query_words = query_lower.split()
                    for category_services in Config.CATEGORY_SERVICES.values():
                        for service in category_services:
                            service_lower = service.lower()
                            if service_lower in query_lower:
                                requested_services.add(service_lower)
                            for word in query_words:
                                if word in service_lower.split():
                                    requested_services.add(service_lower)
            else:
                # Fallback if no app instance
                from config import Config
                query_words = query_lower.split()
                for category_services in Config.CATEGORY_SERVICES.values():
                    for service in category_services:
                        service_lower = service.lower()
                        if service_lower in query_lower:
                            requested_services.add(service_lower)
                        for word in query_words:
                            if word in service_lower.split():
                                requested_services.add(service_lower)
            
            # If we found requested services, filter to show only those
            if requested_services:
                logging.info(f"Requested services for short answer (normalized): {requested_services}")
                matching_free = [s for s in all_free if any(req in s.lower() for req in requested_services)]
                matching_paid = [s for s in all_paid if any(req in s.lower() for req in requested_services)]
                
                if matching_free or matching_paid:
                    # Combine services into a single line
                    service_list = []
                    for service in matching_free:
                        service_list.append(f"{service} (Free)")
                    for service in matching_paid:
                        service_list.append(f"{service} (Paid)")
                    
                    short_text += f"● Services: {', '.join(service_list)}<br>"

        # Display short answer as single HTML block (no extra spacing)
        if short_text:
            st.markdown(short_text.rstrip('<br>'), unsafe_allow_html=True)
        
        # ===== MORE OPTIONS SECTION - NO CHECKBOXES =====
        # Show a simple toggle to control visibility instead of expander
        options_visible_key = f"show_options{key_suffix}"
        if options_visible_key not in st.session_state:
            st.session_state[options_visible_key] = False
        
        # Toggle button outside any expander
        if st.button(
            "－ Hide information" if st.session_state[options_visible_key] else "＋ More information",
            key=f"toggle_options{key_suffix}",
            use_container_width=True
        ):
            st.session_state[options_visible_key] = not st.session_state[options_visible_key]
            st.rerun()
        
        # Show options if toggled on
        if st.session_state[options_visible_key]:

            # Display ALL organizations with complete details (NO CHECKBOXES)
            for org_idx, org in enumerate(organizations):
                # Determine if this org is currently selected
                is_selected = (org['name'] == st.session_state[selection_key])
                
                # Organization header - highlight if selected
                if is_selected:
                    st.markdown(f"➤ **{org['number']}. {org['name']}**")
                else:
                    st.markdown(f"**{org['number']}. {org['name']}**")
                
                # All details
                full_text = ""
                
                # Distance
                if any('Distance:' in item for item in org.get('main_items', [])):
                    distance_item = [item for item in org['main_items'] if 'Distance:' in item][0]
                    full_text += f"● {distance_item}<br>"
                
                # Phone
                if any('Phone:' in item for item in org.get('main_items', [])):
                    phone_item = [item for item in org['main_items'] if 'Phone:' in item][0]
                    full_text += f"● {phone_item}<br>"
                
                # Address
                if any('Address:' in item for item in org.get('main_items', [])):
                    address_item = [item for item in org['main_items'] if 'Address:' in item][0]
                    full_text += f"● {address_item}<br>"
                
                # FULL ANSWER HOURS - ALWAYS show ALL hours regardless of query
                hours_full = org.get('hours', {})
                if hours_full:
                    full_text += "● Hours:<br>"
                    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    for day in day_order:
                        if day in hours_full:
                            full_text += f"&nbsp;&nbsp;&nbsp;&nbsp;○ {day}: {hours_full[day]}<br>"
                
                # ALL Services
                services = org.get('services', {})
                all_free = services.get('free', [])
                all_paid = services.get('paid', [])
                
                if all_free or all_paid:
                    full_text += "● Services:<br>"
                    
                    if all_free:
                        for service in all_free:
                            full_text += f"&nbsp;&nbsp;&nbsp;&nbsp;○ Free: {service}<br>"
                    
                    if all_paid:
                        for service in all_paid:
                            full_text += f"&nbsp;&nbsp;&nbsp;&nbsp;○ Paid: {service}<br>"
                
                # Display all information
                if full_text:
                    st.markdown(full_text.rstrip('<br>'), unsafe_allow_html=True)
                
                st.write("")  # Original spacing between organizations
        
        # ===== DIRECTIONS SECTION - DROPDOWN ONLY (NO CHECKBOXES) =====
        if raw_data:
            # Show a simple toggle to control visibility instead of expander
            directions_visible_key = f"show_directions{key_suffix}"
            if directions_visible_key not in st.session_state:
                st.session_state[directions_visible_key] = False
            
            # Toggle button outside any expander
            if st.button(
                "－ Hide directions" if st.session_state[directions_visible_key] else "＋ Get directions",
                key=f"toggle_directions{key_suffix}",
                use_container_width=True
            ):
                st.session_state[directions_visible_key] = not st.session_state[directions_visible_key]
                st.rerun()
            
            # Show directions if toggled on
            if st.session_state[directions_visible_key]:
                # Call the directions function with all parameters
                display_embedded_directions_for_all_organizations(
                    raw_data=raw_data,
                    user_query=user_query,
                    app_instance=app_instance,
                    message_index=message_index,
                    start_coordinates=start_coordinates,
                    all_categories_data=all_categories_data,
                    current_category_index=current_category_index,
                    shared_selection_key=selection_key  # PASS THE SHARED KEY
                )
    
    else:
        # Fallback
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
* Do you know if there’s a library on West Lehigh Avenue with free Wi-Fi on Tuesdays?
* Can you help me find a mental health center nearby?
* I’m looking for food, a library where I can print a document, and somewhere to stay.

**Before You Continue:**
* Please enable location access to view results near you.<br>        
* Options are sorted by proximity to your target location.<br>
* Your session activity will be securely logged and transmitted to our servers to support monitoring and service improvements.
""", unsafe_allow_html=True)

# Request user location after the welcome message to avoid any spacing issues
get_user_location()

st.markdown("---")

# --- Application Initialization ---
def get_session_app():
    """Get or create app instance for current session with proper isolation."""
    # Use Streamlit's session_state for proper per-session isolation
    if 'app_instance' not in st.session_state:
        # Create unique session ID for this user
        import uuid
        session_id = str(uuid.uuid4())
        st.session_state.session_id = session_id
        
        try:
            # Create app instance with session ID
            st.session_state.app_instance = OrganizationInfoApp(session_id=session_id)
            logging.info(f"Created new app instance for session: {session_id[:8]}...")
        except Exception as e:
            st.error(f"Failed to initialize app: {str(e)}")
            return None
    
    return st.session_state.app_instance

app = get_session_app()


# --- Configuration for Directions ---
DIRECTIONS_HEIGHT = 500  # Height for directions iframe
PLACEHOLDER_HEIGHT = 350  # Height for placeholder when directions fail to load

# --- Embedded Directions Display ---
def get_user_location_for_directions(override_start_coords=None, leg_key_suffix=""):
    """
    Get user's current location for directions based on priority order.
    Priority: 1. Leg-specific custom location, 2. Override coordinates (from previous leg), 3. User's actual location, 4. Default
    """
    # Priority 1: Check if THIS LEG has a custom starting point
    custom_location_key = f"custom_start_location{leg_key_suffix}"
    custom_location_name_key = f"custom_start_location_name{leg_key_suffix}"
    
    if custom_location_key in st.session_state and st.session_state[custom_location_key]:
        custom_lat, custom_lon = st.session_state[custom_location_key]
        logging.info(f"Using leg-specific custom start location: {custom_lat}, {custom_lon}")
        return st.session_state[custom_location_key]
    
    # Priority 2: Use override coordinates if provided (from previous leg's selection)
    if override_start_coords:
        logging.info(f"Using override start coordinates from previous leg: {override_start_coords}")
        return override_start_coords
    
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
    """
    Geocode a starting address to coordinates, or parse if already in coordinate format.
    
    Supports multiple coordinate formats:
    - Simple coordinates: (39.9677, -75.1594) or 39.9677, -75.1594
    - Labeled coordinates: My Location (39.9725, -75.1599)
    - Previous stop: Previous Stop (39.9677, -75.1594)
    - Custom location: Custom (39.9677, -75.1594)
    - Regular addresses: street names, landmarks, etc.
    """
    try:
        import re
        
        # Remove extra whitespace and normalize
        cleaned = address.strip()
        
        # Pattern 1: Labeled coordinates - "Label (lat, lon)"
        # Matches: "My Location (39.9725, -75.1599)", "Previous Stop (39.9677, -75.1594)", etc.
        labeled_pattern = r'^.+?\s*\(\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*\)$'
        labeled_match = re.match(labeled_pattern, cleaned)
        
        if labeled_match:
            lat = float(labeled_match.group(1))
            lon = float(labeled_match.group(2))
            
            # Validate coordinate ranges
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                # Extract the label for display
                label = cleaned.split('(')[0].strip()
                coord_display = f"{label} ({lat:.4f}, {lon:.4f})"
                logging.info(f"Parsed labeled coordinates: {coord_display}")
                return lat, lon, coord_display
            else:
                logging.warning(f"Labeled coordinates out of valid range: {lat}, {lon}")
                return None, None, None
        
        # Pattern 2: Simple coordinates with or without parentheses
        # Matches: "(39.9677, -75.1594)", "39.9677, -75.1594", "39.9677,-75.1594"
        cleaned_no_parens = cleaned.replace('(', '').replace(')', '').strip()
        simple_coord_pattern = r'^(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)$'
        simple_match = re.match(simple_coord_pattern, cleaned_no_parens)
        
        if simple_match:
            lat = float(simple_match.group(1))
            lon = float(simple_match.group(2))
            
            # Validate coordinate ranges
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                coord_display = f"Coordinates ({lat:.4f}, {lon:.4f})"
                logging.info(f"Parsed simple coordinates: {lat}, {lon}")
                return lat, lon, coord_display
            else:
                logging.warning(f"Simple coordinates out of valid range: {lat}, {lon}")
                return None, None, None
        
        # Pattern 3: Regular address - proceed with geocoding
        geolocator = Nominatim(
            user_agent="dreamkg_app/1.0 (javad.mohammadalizadeh@gmail.com)",
            timeout=10
        )
        time.sleep(2)  # Rate limiting
        
        # Add Philadelphia context for better results
        search_query = f"{address}, Philadelphia, PA" if "Philadelphia" not in address else address
        location = geolocator.geocode(search_query)
        
        if location:
            logging.info(f"Geocoded address '{address}' to: {location.latitude}, {location.longitude}")
            return location.latitude, location.longitude, location.address
        else:
            logging.warning(f"Could not geocode address: {address}")
            return None, None, None
            
    except Exception as e:
        logging.error(f"Geocoding error for '{address}': {str(e)}")
        return None, None, None
        
        # If not coordinates, proceed with normal geocoding
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
        logging.error(f"Geocoding error for '{address}': {str(e)}")
        return None, None, None

def update_selection_from_dropdown(shared_key, dropdown_key):
    """Helper to sync dropdown selection to shared state"""
    if dropdown_key in st.session_state:
        st.session_state[shared_key] = st.session_state[dropdown_key]

def display_embedded_directions_for_all_organizations(raw_data, user_query="", app_instance=None, message_index=None, start_coordinates=None, all_categories_data=None, current_category_index=None, shared_selection_key=None):
    """
    FIXED VERSION: Proper synchronization with checkboxes and dynamic map updates
    """
    if not raw_data:
        return
    
    # LIMIT TO TOP 10 RESULTS FOR DIRECTIONS
    limited_raw_data = raw_data[:10]
    
    # Create unique key suffix based on message index or current time
    key_suffix = f"_{message_index}" if message_index is not None else f"_{int(time.time() * 1000)}"
    
    # LEG-SPECIFIC session state keys
    custom_location_key = f"custom_start_location{key_suffix}"
    custom_location_name_key = f"custom_start_location_name{key_suffix}"
    
    # USE THE SHARED SELECTION KEY passed from parent function
    if shared_selection_key is None:
        # Fallback to creating our own if not passed (shouldn't happen)
        shared_selection_key = f"destination_selector{key_suffix}"
    
    try:
        # Extract user's mentioned location using existing spatial intelligence
        query_location_text = extract_user_location_from_query(user_query, raw_data, app_instance)
        
        # ============================================================================
        # DYNAMIC ROUTING - Check if previous leg has a selection
        # ============================================================================
        dynamic_start_coordinates = None
        previous_selection_info = None
        
        # Only apply dynamic routing if we have multi-category data and this isn't the first leg
        if all_categories_data and current_category_index and current_category_index > 1:
            # Build the key for the previous leg's selection
            prev_leg_index = current_category_index - 1
            # Extract message number from key_suffix (format: "_msgidx_catidx")
            if "_" in str(message_index):
                msg_num = str(message_index).split("_")[0]
            else:
                msg_num = str(message_index)
            
            prev_leg_selection_key = f"destination_selector_{msg_num}_{prev_leg_index}"
            
            # Check if user made a selection in the previous leg
            if prev_leg_selection_key in st.session_state:
                selected_org_name = st.session_state[prev_leg_selection_key]
                
                # Get the previous leg's raw data
                prev_leg_data = all_categories_data[prev_leg_index - 1]['raw_data']
                
                # Find the selected organization's coordinates
                for record in prev_leg_data:
                    org_name = (
                        record.get('o.name') or 
                        record.get('name') or 
                        record.get('organizationName')
                    )
                    
                    if org_name == selected_org_name:
                        # Extract coordinates
                        lat = record.get('l.latitude') or record.get('latitude')
                        lon = record.get('l.longitude') or record.get('longitude')
                        
                        if lat and lon:
                            dynamic_start_coordinates = (float(lat), float(lon))
                            previous_selection_info = {
                                'org_name': selected_org_name,
                                'coordinates': dynamic_start_coordinates
                            }
                            logging.info(f"Dynamic routing: Using coordinates from {selected_org_name}: {dynamic_start_coordinates}")
                            break
        
        # Override start_coordinates if we found a dynamic route
        if dynamic_start_coordinates:
            start_coordinates = dynamic_start_coordinates
        
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
        org_options = []  # Will store "1. Org Name" format
        org_name_to_display = {}  # Maps actual name to display format
        org_data = {}  # Maps actual name to data
        
        org_number = 1  # Counter for numbering
        for record in limited_raw_data:
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
                
                # Get coordinates directly from the record (already in Neo4j data)
                lat = record.get('l.latitude') or record.get('latitude')
                lon = record.get('l.longitude') or record.get('longitude')

                if lat is not None and lon is not None:
                    # Build address for display
                    address = (
                        record.get('l.street') or 
                        record.get('street') or 
                        record.get('streetAddress') or 
                        record.get('address')
                    )
                    
                    city = (
                        record.get('l.city') or 
                        record.get('city') or
                        'Philadelphia'
                    )
                    
                    state = (
                        record.get('l.state') or 
                        record.get('state') or 
                        'PA'
                    )
                    
                    zipcode = (
                        record.get('l.zipcode') or 
                        record.get('zipcode') or 
                        record.get('zipCode') or 
                        ''
                    )
                    
                    # Build full address for display
                    full_address = f"{address}, {city}, {state} {zipcode}".strip() if address else f"{city}, {state}"
                    
                    # Create numbered display format
                    display_name = f"{org_number}. {org_name}"
                    
                    org_options.append(display_name)
                    org_name_to_display[org_name] = display_name
                    org_data[org_name] = {
                        'lat': float(lat),
                        'lon': float(lon),
                        'address': full_address,
                        'record': record,
                        'display_name': display_name
                    }
                    
                    org_number += 1
        
        if not org_options:
            st.warning("No organizations with valid addresses found for directions.")
            return
        
        # FIXED: Get current selection from SHARED key
        current_selection = st.session_state.get(shared_selection_key)
        
        # Find the display name and index for current selection
        default_index = 0
        if current_selection:
            if current_selection in org_name_to_display:
                # Current selection is actual org name, get its display format
                display_selection = org_name_to_display[current_selection]
                if display_selection in org_options:
                    default_index = org_options.index(display_selection)
            elif current_selection in org_options:
                # Current selection is already in display format
                default_index = org_options.index(current_selection)
        
        # Extract actual org name from display format (remove "1. " prefix)
        selected_display = org_options[default_index]
        selected_org = selected_display.split(". ", 1)[1] if ". " in selected_display else selected_display
        
        if selected_org and selected_org in org_data:
            org_info = org_data[selected_org]
            lat, lon = org_info['lat'], org_info['lon']
            
            # Determine what to show in the text input placeholder and value
            default_location_text = ""
            placeholder_text = "e.g., 1234 Market Street, Philadelphia"

            # Priority-based location text for input field
            if custom_location_key in st.session_state and st.session_state[custom_location_key]:
                # THIS LEG has a custom location
                custom_lat, custom_lon = st.session_state[custom_location_key]
                default_location_text = st.session_state.get(custom_location_name_key, f"Custom ({custom_lat:.4f}, {custom_lon:.4f})")
                placeholder_text = f"Custom location: {default_location_text}"
            elif start_coordinates and start_coordinates != st.session_state.get('user_location'):
                # Using optimized routing coordinates (from previous stop)
                start_lat, start_lon = start_coordinates
                default_location_text = f"Previous Stop ({start_lat:.4f}, {start_lon:.4f})"
                placeholder_text = f"Starting from previous stop: {start_lat:.4f}, {start_lon:.4f}"
            elif 'user_location' in st.session_state and st.session_state.user_location:
                # User's actual location is available
                user_lat, user_lon = st.session_state.user_location
                default_location_text = f"My Location ({user_lat:.4f}, {user_lon:.4f})"
                placeholder_text = f"Using your location: {user_lat:.4f}, {user_lon:.4f}"
            elif 'query_location_text' in st.session_state:
                # Query-based location
                default_location_text = st.session_state.query_location_text
                placeholder_text = f"From query: {st.session_state.query_location_text}"

            
            # ===== STARTING LOCATION (TOP) =====
            col1, col2 = st.columns([4, 1])
            with col1:
                # Show different help text based on what location we're using
                help_text = "You can change this starting point if needed"
                if 'user_location' in st.session_state and st.session_state.user_location:
                    help_text = "Using your actual location. You can override this with a custom address."
                
                custom_address = st.text_input(
                    "○ Starting location:",
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
            
            # Handle location update button
            if set_location and custom_address:
                with st.spinner("Processing location..."):
                    start_lat, start_lon, full_address = geocode_start_location(custom_address)
                    
                    if start_lat and start_lon:
                        # Store in leg-specific session state keys
                        st.session_state[custom_location_key] = (start_lat, start_lon)
                        st.session_state[custom_location_name_key] = full_address or custom_address
                        logging.info(f"Custom start location set for leg {key_suffix}: {full_address or custom_address}")
                        st.rerun()
                    else:
                        st.error("Could not find that location. Please try a different address or coordinates.")
                        logging.error(f"Failed to geocode: {custom_address}")

            # ===== DESTINATION DROPDOWN - FIXED SYNCHRONIZATION =====
            # CRITICAL FIX: Check if dropdown selection differs from shared state
            # If so, update shared state and force immediate rerun
            temp_dropdown_key = f"dropdown_temp{key_suffix}"
            
            # Get what's currently selected in the dropdown (if it exists from previous render)
            if temp_dropdown_key in st.session_state:
                temp_selected_display = st.session_state[temp_dropdown_key]
                temp_selected_org = temp_selected_display.split(". ", 1)[1] if ". " in temp_selected_display else temp_selected_display
                
                # If dropdown selection differs from shared selection, sync and rerun
                if temp_selected_org != st.session_state.get(shared_selection_key):
                    logging.info(f"Dropdown out of sync: '{temp_selected_org}' vs shared '{st.session_state.get(shared_selection_key)}'")
                    st.session_state[shared_selection_key] = temp_selected_org
                    st.rerun()  # FORCE IMMEDIATE RERUN
            
            # Render the dropdown with current selection
            selected_display_new = st.selectbox(
                "⚑ Destination:",
                options=org_options,
                index=default_index,
                key=temp_dropdown_key,
                label_visibility="visible"
            )
            
            # Extract actual org name from current dropdown selection
            selected_org_new = selected_display_new.split(". ", 1)[1] if ". " in selected_display_new else selected_display_new
            
            # Use the newly selected org if it's in our data
            if selected_org_new in org_data:
                selected_org = selected_org_new
                org_info = org_data[selected_org]
                lat, lon = org_info['lat'], org_info['lon']

            # Get user location for directions (after potential update)
            user_lat, user_lon = get_user_location_for_directions(start_coordinates, leg_key_suffix=key_suffix)
            
            # Transportation mode selector (simplified) with unique keys
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                driving = st.button("🚗 Driving", key=f"driving_all_orgs{key_suffix}", use_container_width=True)
            with col2:
                walking = st.button("🚶🏽 Walking", key=f"walking_all_orgs{key_suffix}", use_container_width=True)
            with col3:
                cycling = st.button("🚴‍♀️ Cycling", key=f"cycling_all_orgs{key_suffix}", use_container_width=True)
            with col4:
                transit = st.button("🚆 Transit", key=f"transit_all_orgs{key_suffix}", use_container_width=True)

            # Determine transportation mode
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
                # Check if we have a saved global mode, default to driving
                transport_mode = st.session_state.get("global_transport_mode", "driving")


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
                
                # Embed Street View
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
        logging.error(f"Directions error: {str(e)}")

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

# Initialize default transport mode to driving
if "global_transport_mode" not in st.session_state:
    st.session_state.global_transport_mode = "driving"

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
        # Get the original query for this message
        original_query = message.get("original_query", "")
        
        # Check if multi-category message
        if isinstance(message["content"], dict) and message["content"].get("type") == "multi_category_complete":
            for cat_idx, cat_data in enumerate(message["content"]["categories"], 1):
                category = cat_data['category']
                services = cat_data['services']
                response = cat_data['response']
                raw_data = cat_data['raw_data']
                
                st.markdown(f"<span style='font-size: 24px;'><strong>Stop {cat_idx}: {category}</strong></span>", unsafe_allow_html=True)
                st.write("")
                
                display_structured_response(
                    response,
                    raw_data=raw_data,
                    user_query=original_query,
                    app_instance=app,
                    message_index=f"{idx}_{cat_idx}",
                    start_coordinates=cat_data.get('start_coordinates'),
                    all_categories_data=message["content"]["categories"],
                    current_category_index=cat_idx
                )
                
                st.write("")
        else:
            # Regular message
            display_structured_response(
                message["content"],
                user_query=original_query  # ADD THIS
            )

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
        
        # ============================================================================
        # EXTRACT TIME CONTEXT FIRST - Before any flow decisions
        # ============================================================================
        time_context = ""
        days_of_week = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        prompt_lower = prompt.lower()
        
        # Check for specific day mentions
        for day in days_of_week:
            if day in prompt_lower:
                time_context = f" on {day.capitalize()}"
                
                # Check for time-of-day requirements
                if "after hours" in prompt_lower:
                    time_context += " after 8pm"
                    logging.info(f"Normalized 'after hours' to 'after 8pm'. Full context: '{time_context}'")
                else:
                    # ORIGINAL LOGIC for specific times like "after 5pm"
                    time_of_day_pattern = r'(after|before|around|at)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))'
                    time_match = re.search(time_of_day_pattern, prompt)
                    if time_match:
                        time_phrase = time_match.group(0)
                        time_context += f" {time_phrase}"
                        logging.info(f"Extracted time context from query: '{day}' + '{time_phrase}'")
                    else:
                        logging.info(f"Extracted time context from query: '{day}'")
                break
        
        # If no specific day, check for general time indicators
        if not time_context:
            time_indicators = ['hour', 'hours', 'open', 'close', 'closing', 'opening', 'time', 'weekday', 'weekend']
            if any(indicator in prompt_lower for indicator in time_indicators):
                time_context = " (user asking about hours)"
                logging.info(f"Detected time-related query")
        
        # ============================================================================
        # Clear previous location settings for fresh query
        # ============================================================================
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
        
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            # Get user location
            user_location = st.session_state.get('user_location')
            
            # STEP 1: Categorize services by organization category
            categorized_services = app.query_service.categorize_services_by_category(prompt)
            
            if not categorized_services:
                # ====================================================================
                # SINGLE CATEGORY FLOW - Apply time context here too
                # ====================================================================
                logging.info("No specific categories detected - using original flow")
                
                # Create query with time context if available
                query_with_time = prompt + time_context if time_context else prompt
                logging.info(f"Single-category query with time context: {query_with_time}")
                
                with st.spinner("Searching..."):
                    response, raw_data = app.process_user_request_for_streamlit(query_with_time, user_location)
                    
                    try:
                        app.log_session_to_sheets()
                    except Exception as e:
                        logging.warning(f"Google Sheets logging failed: {str(e)}")
                
                display_structured_response(response)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response,
                    "raw_data": raw_data,
                    "original_query": prompt
                })
            
            else:
                # ====================================================================
                # MULTI-CATEGORY FLOW - Time context already extracted above
                # ====================================================================
                logging.info(f"Processing {len(categorized_services)} categories: {list(categorized_services.keys())}")
                
                all_category_responses = []
                all_raw_data = []
                
                # Initialize with user's location for first stop
                search_coordinates = user_location
                previous_results = None
                last_successful_coordinates = user_location
                
                for cat_idx, (category, services) in enumerate(categorized_services.items(), 1):

                    # LOG ORIGINAL USER QUERY
                    if cat_idx == 1:
                        logging.info(f"\n{'='*70}")
                        logging.info(f"ORIGINAL USER QUERY: {prompt}")
                        logging.info(f"EXTRACTED TIME CONTEXT: {time_context}")
                        logging.info(f"{'='*70}\n")
                    
                    # FIRST LEG: Apply intended location logic
                    if cat_idx == 1:
                        is_personal_location = app._is_personal_location_query(prompt)
                        
                        if is_personal_location:
                            # Personal location queries use user's location for search AND map
                            if user_location:
                                search_coordinates = user_location
                                map_start_coordinates = user_location
                                logging.info(f"First leg (personal location): Using user location for search AND map: {user_location}")
                            else:
                                search_coordinates = (39.952335, -75.163789)
                                map_start_coordinates = (39.952335, -75.163789)
                                logging.info(f"First leg (personal location, no permission): Using City Hall for search AND map")
                        else:
                            # Specific location mentioned
                            has_specific_location = app.spatial_intel.extract_location_from_query(prompt)
                            
                            if has_specific_location:
                                # Search based on mentioned location, map starts from user location
                                specific_coords = app.spatial_intel.geocode_location(has_specific_location)
                                search_coordinates = specific_coords if specific_coords else (39.952335, -75.163789)
                                map_start_coordinates = user_location if user_location else (39.952335, -75.163789)
                                logging.info(f"First leg (specific location '{has_specific_location}'): Search from {search_coordinates}, map from {map_start_coordinates}")
                            else:
                                # No location mentioned - use user location for both
                                search_coordinates = user_location if user_location else (39.952335, -75.163789)
                                map_start_coordinates = search_coordinates
                                logging.info(f"First leg (no location): Using {search_coordinates} for search AND map")
                        
                        last_successful_coordinates = search_coordinates
                    
                    # SUBSEQUENT LEGS: Use optimized routing
                    elif previous_results and len(previous_results) > 0:
                        first_result = previous_results[0]
                        prev_lat = (first_result.get('l.latitude') or first_result.get('latitude'))
                        prev_lon = (first_result.get('l.longitude') or first_result.get('longitude'))
                        
                        if prev_lat and prev_lon:
                            search_coordinates = (float(prev_lat), float(prev_lon))
                            map_start_coordinates = search_coordinates
                            last_successful_coordinates = search_coordinates
                            prev_org_name = (first_result.get('o.name') or first_result.get('name') or 'previous location')
                            logging.info(f"Leg {cat_idx} (optimized): Search AND map from '{prev_org_name}' at {search_coordinates}")
                        else:
                            search_coordinates = last_successful_coordinates
                            map_start_coordinates = last_successful_coordinates
                            logging.warning(f"Leg {cat_idx}: Using last successful coordinates: {last_successful_coordinates}")
                    else:
                        search_coordinates = user_location if user_location else (39.952335, -75.163789)
                        map_start_coordinates = search_coordinates
                        logging.info(f"Leg {cat_idx}: Fallback to {search_coordinates}")
                    
                    logging.info(f"\n{'='*70}")
                    logging.info(f"CATEGORY LOOP {cat_idx}/{len(categorized_services)}: {category}")
                    logging.info(f"Services in this category: {services}")
                    logging.info(f"Search starting coordinates: {search_coordinates}")
                    logging.info(f"{'='*70}\n")
                    
                    # Create category-specific query with time context
                    services_text = " and ".join(services)
                    category_query = f"organizations in {category} category that offer {services_text}{time_context}"
                    logging.info(f"Category query with time context: {category_query}")
                    
                    # Run flow with optimized coordinates
                    with st.spinner(f"Searching {category} for {services_text}..."):
                        # Use process_query_with_coordinates with optimized starting point
                        query_result = app.query_service.process_query_with_coordinates(category_query, search_coordinates)
                        
                        # Generate response - PASS THE ORIGINAL PROMPT, NOT category_query
                        response_result = app.response_service.generate_response(
                            prompt,  # Use original user query
                            query_result['results'],
                            is_spatial=True,
                            is_focused=False
                        )
                        
                        response = response_result['response']
                        raw_data = query_result['results']

                        # Log session metrics to file
                        app.metrics.log_statistics_to_file()

                        # Log to Google Sheets
                        try:
                            app.log_session_to_sheets()
                            logging.info(f"Session logged for category: {category}")
                        except Exception as e:
                            logging.warning(f"Google Sheets logging failed: {str(e)}")
                    
                    # Store for history FIRST
                    all_category_responses.append({
                        'category': category,
                        'services': services,
                        'response': response,
                        'raw_data': raw_data,
                        'start_coordinates': map_start_coordinates
                    })
                    all_raw_data.extend(raw_data if raw_data else [])

                    # Only update previous_results if we got results
                    if raw_data and len(raw_data) > 0:
                        previous_results = raw_data
                        logging.info(f"Stored {len(raw_data)} results for next iteration")
                    else:
                        logging.info(f"No results to store. Next iteration will use last successful coordinates: {last_successful_coordinates}")
                    
                    # Separator between categories (except last one)
                    if cat_idx < len(categorized_services):
                        st.write("")
                    
                    logging.info(f"Completed {category} category loop\n")
                
                # STEP 4: Save to session history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": {
                        "type": "multi_category_complete",
                        "categories": all_category_responses
                    },
                    "raw_data": all_raw_data,
                    "original_query": prompt
                })
                
                # STEP 5: Display all categories NOW (after saving)
                for cat_idx, cat_data in enumerate(all_category_responses, 1):
                    category = cat_data['category']
                    response = cat_data['response']
                    raw_data = cat_data['raw_data']
                    
                    st.markdown(f"<span style='font-size: 24px;'><strong>Stop {cat_idx}: {category}</strong></span>", unsafe_allow_html=True)
                    st.write("")
                    
                    current_message_index = len(st.session_state.messages) - 1
                    
                    display_structured_response(
                        response, 
                        raw_data=raw_data,
                        user_query=prompt,
                        app_instance=app,
                        message_index=f"{current_message_index}_{cat_idx}",
                        start_coordinates=cat_data.get('start_coordinates'),
                        all_categories_data=all_category_responses,
                        current_category_index=cat_idx
                    )
                    
                    if cat_idx < len(all_category_responses):
                        st.write("")
                            
else:
    st.warning("Application is not available due to an initialization error.")

# Download button - outside all conditional blocks
if app and st.session_state.messages:
    display_log_download_button(app)

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