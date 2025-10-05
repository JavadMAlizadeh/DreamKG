import re
import logging
import time
from langchain.chains import LLMChain
from langchain_groq import ChatGroq
from langchain.callbacks import get_openai_callback
from config import Config
from models.spatial_intelligence import SpatialIntelligence
from models.conversation_memory import ConversationMemory
from database.neo4j_client import Neo4jClient
from templates.prompts import PromptTemplateFactory

# REMOVED: SimpleRateLimiter class entirely

class QueryService:
    """
    Enhanced query service with comprehensive token and latency tracking.
    NO RATE LIMITING - Direct API calls for maximum speed.
    """
    
    def __init__(self, neo4j_client, spatial_intel=None, memory=None, metrics_collector=None):
        """
        Initialize enhanced query service with dependencies.
        
        Args:
            neo4j_client (Neo4jClient): Database client
            spatial_intel (SpatialIntelligence): Spatial intelligence service
            memory (ConversationMemory): Conversation memory manager
            metrics_collector (EnhancedMetricsCollector): Enhanced metrics tracking system
        """
        self.neo4j_client = neo4j_client
        self.spatial_intel = spatial_intel or SpatialIntelligence()
        self.memory = memory or ConversationMemory()
        self.metrics = metrics_collector  # Can be None
        
        # Initialize LLM
        self.llm = ChatGroq(
            model=Config.LLM_MODEL, 
            temperature=Config.LLM_TEMPERATURE
        )
        
        # Initialize prompt templates
        self.spatial_cypher_prompt = PromptTemplateFactory.create_spatial_cypher_prompt()
        self.regular_cypher_prompt = PromptTemplateFactory.create_regular_cypher_prompt()
        
        # Initialize LLM chains
        self.spatial_cypher_chain = LLMChain(llm=self.llm, prompt=self.spatial_cypher_prompt)
        self.regular_cypher_chain = LLMChain(llm=self.llm, prompt=self.regular_cypher_prompt)

        # REMOVED: Rate limiter initialization

        # Service synonym mapping (unchanged from original)
        self.service_synonyms = {
            # Social Security Services - FIXED to match actual database service names
            'appeal': ['appeal', 'appeals', 'decision', 'dispute', 'challenge', 'disputing', 'appealing'],
            'benefit': ['benefit', 'benefits', 'retirement', 'disability', 'ssi', 'medicare', 'social security', 'apply for benefits'],
            'apply': ['apply', 'application', 'applications', 'filing', 'apply for'],
            '1099': ['1099', 'statement', 'statements', 'proof', 'earnings', 'history', 'replacement 1099'],
            
            # FIXED: Use keywords that match "Change Address/Direct Deposit"
            'change': ['change', 'update', 'modify', 'direct deposit', 'change address', 'change direct deposit', 'direct deposit information'],
            'address': ['address', 'direct deposit', 'change address', 'update address'],
            'direct': ['direct deposit', 'direct deposit information', 'change direct deposit'],
            'deposit': ['deposit', 'direct deposit', 'change direct deposit'],
            
            'estimate': ['estimate', 'estimates', 'calculator', 'calculation'],
            'proof': ['proof', 'print proof', 'statements'],
            'history': ['history', 'earnings', 'review earnings'],
            'withdrawal': ['withdrawal', 'atm', 'cash'],
            'transfer': ['transfer', 'funds transfer', 'money transfer'],
            'international': ['international', 'international transactions', 'overseas'],
            'overnight': ['overnight', 'express', 'expedited', 'rush', 'overnight delivery'],
            
            # Library Technology Services - FIXED WiFi mapping
            'computer': ['computer', 'computers', 'public computers', 'computer access', 'computer labs', 'computer or internet access'],
            'wi-fi': ['wifi', 'wi-fi', 'internet', 'wireless'],  # FIXED: Map to 'wi-fi' with hyphen
            'print': ['print', 'printing', 'printer'],
            'copy': ['copy', 'copying', 'copies', 'copier'],
            'scan': ['scan', 'scanning', 'scanner', 'scanners'],
            
            # Library Educational Services
            'class': ['class', 'classes', 'education', 'learning', 'computer class', 'health education', 'sex education', 'parenting education'],
            'ged': ['ged', 'adult education', 'basic literacy', 'literacy'],
            'homework': ['homework', 'homework help', 'tutoring', 'study'],
            'job': ['job', 'job assistance', 'job search', 'job readiness', 'workforce development', 'employment', 'help find work', 'resume development'],
            'citizenship': ['citizenship', 'citizenship class', 'new americans', 'services for new americans'],
            
            # Library Children Services
            'story': ['story', 'story time', 'story times', 'storytime', 'children'],
            'after': ['after-school', 'after school', 'kids programs', 'youth programs', 'after school care'],
            'summer': ['summer', 'summer learning', 'summer programs', 'day camp'],
            'stem': ['stem', 'science', 'technology', 'engineering', 'math', 'coding', 'programming'],
            
            # Library Collections & Research
            'book': ['book', 'books', 'collection', 'large collection'],
            'special': ['special', 'special collections', 'research', 'archives'],
            'foreign': ['foreign', 'chinese', 'spanish', 'language collection', 'multilingual'],
            'audio': ['audio', 'audiobooks', 'braille', 'large print', 'accessibility'],
            
            # Library Events & Programs
            'event': ['event', 'events', 'author events', 'author talks', 'exhibitions'],
            'workshop': ['workshop', 'workshops', 'programs', 'community programs'],
            'tour': ['tour', 'tours', 'guided tours'],
            'game': ['game', 'games', 'gaming', 'board games', 'chess', 'chess club'],
            'music': ['music', 'music classes', 'arts'],
            'cooking': ['cooking', 'cooking classes', 'culinary'],
            
            # Library Spaces & Facilities
            'meeting': ['meeting', 'meeting room', 'meeting rooms', 'meeting spaces', 'conference'],
            'study': ['study', 'study room', 'study rooms', 'quiet space'],
            'restroom': ['restroom', 'restrooms', 'bathroom', 'facilities'],
            'drop': ['book drop', 'return', 'drop box', 'drop off'],
            
            # Library Special Services
            'mail': ['mail', 'delivery', 'postage', 'shipping'],
            'social': ['social services', 'social support', 'community support'],
            'health': ['health', 'health classes', 'wellness', 'health education', 'medical care', 'disease screening'],
            'film': ['film', 'movies', 'foreign film', 'video'],

            # Shelter, Food Bank, Mental Health Services
            'shelter': ['stay', 'shelter', 'housing', 'safe housing', 'short-term housing', 'residential housing', 'help find housing'],
            'food': ['food', 'meals', 'meal', 'emergency food', 'food pantry', 'nutrition', 'food delivery'],
            'mental health': ['mental health', 'mental health care', 'counseling', 'therapy', 'psychiatric', 'support groups', 'peer support', 'bereavement', 'anger management', 'group therapy'],
            'substance abuse': ['substance abuse', 'addiction', 'recovery', 'sober living', 'detox', '12-step', 'outpatient treatment'],
            'financial': ['financial', 'financial assistance', 'emergency payments', 'pay for housing', 'pay for utilities', 'government benefits'],
            'legal': ['legal', 'advocacy & legal aid'],
            'clothing': ['clothing', 'clothes'],
            'hygiene': ['hygiene', 'personal care', 'personal hygiene'],
            'parenting': ['parenting', 'parenting education'],
            'hotline': ['hotline', 'help hotlines'],
        }
        
        # FIXED: Keyword normalization mappings - normalize TO database format
        self.keyword_normalizations = {
            # WiFi normalization - FIXED: normalize TO wi-fi (database format)
            'wifi': 'wi-fi',          # FIXED: wifi -> wi-fi
            'internet': 'wi-fi',      # internet -> wi-fi
            'wireless': 'wi-fi',      # wireless -> wi-fi

            # Food/Meal normalization - ADD THESE
            'meal': 'food',         
            'meals': 'food',
            'dining': 'food',
            'lunch': 'food',
            'dinner': 'food',
            'breakfast': 'food',
            
            # Other normalizations (normalize to singular/database format)
            'appeals': 'appeal',
            'benefits': 'benefit',
            'applications': 'apply',
            'computers': 'computer',
            'classes': 'class',
            'workshops': 'workshop',
            'programs': 'program',
            'collections': 'collection',
            'rooms': 'room',
            'spaces': 'space',
            'events': 'event',
            'services': 'service',
            'books': 'book',
            'cards': 'card',
            'statements': 'statement',
            'estimates': 'estimate',
            'meals': 'food',
            'meal': 'food',
            'housing': 'shelter',
            'stay': 'shelter',
            'clothes': 'clothing',
            
            # Service variations
            'printing': 'print',
            'copying': 'copy',
            'scanning': 'scan',
            'tutoring': 'homework help',
            'employment': 'job assistance',
            'storytime': 'story time',
            'after-school': 'after school',
            'programming': 'coding',
            'audiobooks': 'audio',
            'bathroom': 'restroom',
            'conference': 'meeting room',
            'quiet space': 'study room',
            'return': 'book drop',
            'shipping': 'mail delivery',
            'wellness': 'health',
            'movies': 'film',
            'cash': 'atm',
            'express': 'overnight',
            'rush': 'overnight',
            'addiction': 'substance abuse',
            'recovery': 'substance abuse',
            'sober living': 'substance abuse',
            'detox': 'substance abuse',
            'therapy': 'mental health',
            'counseling': 'mental health',
            
            # Service action normalization
            'appealing': 'appeal',
            'disputing': 'appeal',
            'challenging': 'appeal',
            'applying': 'apply',
            'filing': 'apply',
            'requesting': 'request',
            'changing': 'change',
            'updating': 'change',
            'calculating': 'estimate',
            'learning': 'class',
            'studying': 'study',
            'gaming': 'game',
            'teaching': 'class',
            'training': 'class'
        }

        logging.info("Enhanced QueryService initialized with NO RATE LIMITING for maximum speed")

    def process_query_with_coordinates(self, user_query, coordinates):
        """
        Process a user query with predefined coordinates (bypassing spatial intelligence).
        This is used for scenarios 1 and 3 where we use default or user location directly.
        
        Args:
            user_query (str): User's question
            coordinates (tuple): (latitude, longitude) to use for spatial queries
            
        Returns:
            dict: Query processing result
        """
        try:
            logging.info(f"Processing query with predefined coordinates: {user_query}")
            logging.info(f"Using coordinates: {coordinates}")
            
            # Step 0: Normalize service keywords and extract service context
            normalization_start_time = time.time()
            normalized_query = self._normalize_service_keywords(user_query)
            service_keywords = self._extract_service_keywords(normalized_query)
            primary_service = self._get_primary_service_keyword(normalized_query)
            normalization_duration = time.time() - normalization_start_time
            
            if normalized_query != user_query:
                logging.info(f"Normalized query: {user_query} -> {normalized_query}")
            if service_keywords:
                logging.info(f"Detected service keywords: {service_keywords}")
            if primary_service:
                logging.info(f"Primary service keyword: {primary_service}")
            
            # Step 1: Check if we should use memory
            memory_start_time = time.time()
            use_memory = self.memory.should_use_memory(normalized_query)
            memory_duration = time.time() - memory_start_time
            logging.info(f"Memory usage decision: {use_memory}")
            
            # Record memory processing time
            if self.metrics:
                self.metrics.record_processing_time('memory', memory_duration)
            
            # Step 2: Process query with memory if applicable
            processed_query = normalized_query
            memory_context = ""
            
            if use_memory:
                processed_query = self.memory.substitute_pronouns(normalized_query)
                memory_context = self.memory.get_memory_context()
                logging.info("Using memory context for query processing")
            
            # Step 3: Create spatial context with provided coordinates
            distance_threshold = Config.DEFAULT_DISTANCE_THRESHOLD
            location_text = "user location" if coordinates != (39.952335, -75.163789) else "City Hall (default)"
            
            spatial_context = f"""
USER LOCATION: {coordinates[0]}, {coordinates[1]} ({location_text})
DISTANCE THRESHOLD: {distance_threshold} miles
USER COORDINATES: user_latitude = {coordinates[0]}, user_longitude = {coordinates[1]}
DISTANCE THRESHOLD: distance_threshold = {distance_threshold}

SPATIAL QUERY INSTRUCTIONS:
- Include distance calculations in your Cypher query using the provided coordinates
- Filter results ONLY by the distance threshold (distance_miles <= {distance_threshold})
- DO NOT add location-based filters (street, city, zipcode, state) - distance filtering handles location
- Sort results by distance (closest first)
- Include distance_miles in the result set
- The coordinates represent the {location_text} - use distance, not text matching
"""
            
            # Create spatial info for memory
            spatial_info = {
                'location_text': location_text,
                'coordinates': coordinates,
                'distance_threshold': distance_threshold
            }
            
            # Step 4: Enhance contexts with service intelligence
            if service_keywords or primary_service:
                service_context = self._create_service_context(service_keywords, primary_service)
                memory_context += service_context
                spatial_context += service_context
            
            # Step 5: Generate and execute Cypher query with enhanced metrics tracking
            query_result = self._execute_cypher_query_with_enhanced_metrics(
                processed_query, True, spatial_context, 
                memory_context, coordinates, distance_threshold
            )
            
            # Record Neo4j duration to metrics
            if self.metrics and 'neo4j_duration' in query_result:
                self.metrics.record_query_result(
                    success=query_result['success'],
                    result_count=len(query_result['results']) if query_result['results'] else 0,
                    expanded_search=False,
                    error_message=query_result.get('error'),
                    cypher_query=query_result.get('cypher_query'),
                    neo4j_duration=query_result['neo4j_duration']
                )
            
            if query_result['success'] and not query_result['results']:
                # Try expanded radius if no results
                logging.info("Attempting expanded radius search with predefined coordinates")
                expanded_result = self._retry_with_expanded_radius_and_enhanced_metrics(
                    processed_query, spatial_context, memory_context,
                    coordinates, distance_threshold
                )
                
                # If the expanded search found something, replace the original result
                if expanded_result['success'] and expanded_result['results']:
                    spatial_info['distance_threshold'] = expanded_result['distance_threshold']
                    # Combine metrics from both attempts
                    original_metrics = self._extract_metrics_from_result(query_result)
                    expanded_metrics = self._extract_metrics_from_result(expanded_result)
                    combined_metrics = self._combine_metrics(original_metrics, expanded_metrics)
                    query_result = expanded_result
                    query_result['expanded_radius'] = True
                    query_result.update(combined_metrics)
                
                # If expanded search also failed, try finding closest organization
                elif not expanded_result['results']:
                    logging.info("Attempting closest organization search with predefined coordinates")
                    closest_result = self._find_closest_organization_with_enhanced_metrics(
                        processed_query, spatial_context, memory_context, coordinates
                    )
                    
                    # If closest search found something, replace the result
                    if closest_result['success'] and closest_result['results']:
                        spatial_info['distance_threshold'] = None  # No threshold for closest search
                        # Combine metrics from all three attempts
                        original_metrics = self._extract_metrics_from_result(query_result)
                        expanded_metrics = self._extract_metrics_from_result(expanded_result)
                        closest_metrics = self._extract_metrics_from_result(closest_result)
                        combined_metrics = self._combine_metrics(
                            self._combine_metrics(original_metrics, expanded_metrics), 
                            closest_metrics
                        )
                        query_result = closest_result
                        query_result['expanded_radius'] = True
                        query_result['closest_search'] = True
                        query_result.update(combined_metrics)
            
            # Step 6: Update memory if we got results
            results = query_result['results']
            if results and not use_memory:
                self.memory.add_interaction(user_query, results, spatial_info)
                logging.info(f"Added interaction to memory: {len(results)} results stored")
            elif not results and not use_memory:
                self.memory.clear_memory()
                logging.info("Cleared memory due to failed new query")
            
            return {
                'success': True,
                'results': results,
                'spatial_info': spatial_info,
                'used_memory': use_memory,
                'expanded_radius': query_result.get('expanded_radius', False),
                'closest_search': query_result.get('closest_search', False),
                'is_spatial': True,  # Always spatial when using coordinates
                'token_usage': query_result.get('token_usage', {}),
                'cypher_query': query_result.get('cypher_query'),
                'service_keywords': service_keywords,
                'primary_service': primary_service,
                # Enhanced metrics
                'neo4j_duration': query_result.get('neo4j_duration', 0.0),
                'llm_duration': query_result.get('llm_duration', 0.0),
                'spatial_duration': query_result.get('spatial_duration', 0.0),
                'first_token_time': query_result.get('first_token_time'),
                'generation_time': query_result.get('generation_time'),
                'normalization_duration': normalization_duration,
                'memory_duration': memory_duration,
                'spatial_detection_duration': 0.0  # No spatial detection when using predefined coordinates
            }
            
        except Exception as e:
            logging.error(f"Query processing with coordinates failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'results': None,
                'spatial_info': None,
                'used_memory': False,
                'expanded_radius': False,
                'closest_search': False,
                'is_spatial': True,
                'token_usage': {},
                'service_keywords': [],
                'primary_service': None,
                # Enhanced metrics (default values)
                'neo4j_duration': 0.0,
                'llm_duration': 0.0,
                'spatial_duration': 0.0,
                'first_token_time': None,
                'generation_time': None,
                'normalization_duration': 0.0,
                'memory_duration': 0.0,
                'spatial_detection_duration': 0.0
            }

    def _execute_cypher_query_with_enhanced_metrics(self, query, is_spatial, spatial_context, memory_context, 
                                                   user_coordinates, distance_threshold):
        """
        Generate and execute Cypher query with comprehensive metrics tracking.
        NO RATE LIMITING - Direct API calls.
        """
        try:
            # Start LLM timing
            if self.metrics:
                self.metrics.start_llm_timing()
            
            # REMOVED: Rate limiting call
            
            # Track token generation timing
            llm_start_time = time.time()
            first_token_received = False
            first_token_time = None
            
            # Method 1: Try with OpenAI callback (works with many providers)
            token_usage = {}
            try:
                with get_openai_callback() as cb:
                    if is_spatial and user_coordinates:
                        cypher_response = self.spatial_cypher_chain.invoke({
                            "schema": self.neo4j_client.get_schema(),
                            "question": query,
                            "spatial_context": spatial_context,
                            "memory_context": memory_context,
                            "user_latitude": user_coordinates[0],
                            "user_longitude": user_coordinates[1],
                            "distance_threshold": distance_threshold
                        })
                        logging.info("Used spatial Cypher generation chain")
                        logging.info(f"Spatial context sent to LLM:\n{spatial_context}")
                    else:
                        cypher_response = self.regular_cypher_chain.invoke({
                            "schema": self.neo4j_client.get_schema(),
                            "question": query,
                            "memory_context": memory_context
                        })
                        logging.info("Used regular Cypher generation chain")
                    
                    # Record first token time (approximate)
                    if not first_token_received:
                        first_token_time = time.time() - llm_start_time
                        first_token_received = True
                        if self.metrics:
                            self.metrics.record_first_token_time()
                    
                    # Extract token usage from callback
                    if cb.total_tokens > 0:
                        token_usage = {
                            'total_tokens': cb.total_tokens,
                            'input_tokens': cb.prompt_tokens,
                            'output_tokens': cb.completion_tokens
                        }
                        logging.info(f"Token usage from OpenAI callback: {token_usage}")
                    
            except Exception as callback_error:
                logging.warning(f"OpenAI callback failed: {callback_error}")
                
                # Method 2: Direct LLM call to get usage
                if is_spatial and user_coordinates:
                    prompt_vars = {
                        "schema": self.neo4j_client.get_schema(),
                        "question": query,
                        "spatial_context": spatial_context,
                        "memory_context": memory_context,
                        "user_latitude": user_coordinates[0],
                        "user_longitude": user_coordinates[1],
                        "distance_threshold": distance_threshold
                    }
                    formatted_prompt = self.spatial_cypher_prompt.format(**prompt_vars)
                    logging.info("Used spatial Cypher generation chain")
                    logging.info(f"Spatial context sent to LLM:\n{spatial_context}")
                else:
                    prompt_vars = {
                        "schema": self.neo4j_client.get_schema(),
                        "question": query,
                        "memory_context": memory_context
                    }
                    formatted_prompt = self.regular_cypher_prompt.format(**prompt_vars)
                    logging.info("Used regular Cypher generation chain")
                
                # Call LLM directly to get raw response
                try:
                    raw_response = self.llm.invoke(formatted_prompt)
                    cypher_response = {'text': raw_response.content}
                    
                    # Record first token time (approximate)
                    if not first_token_received:
                        first_token_time = time.time() - llm_start_time
                        first_token_received = True
                        if self.metrics:
                            self.metrics.record_first_token_time()
                    
                    # Try to extract token usage from raw response
                    if hasattr(raw_response, 'response_metadata'):
                        metadata = raw_response.response_metadata
                        if 'usage' in metadata:
                            usage = metadata['usage']
                            token_usage = {
                                'total_tokens': usage.get('total_tokens', 0),
                                'input_tokens': usage.get('prompt_tokens', 0),
                                'output_tokens': usage.get('completion_tokens', 0)
                            }
                            logging.info(f"Token usage from raw response metadata: {token_usage}")
                        elif 'token_usage' in metadata:
                            usage = metadata['token_usage']
                            token_usage = {
                                'total_tokens': usage.get('total_tokens', 0),
                                'input_tokens': usage.get('prompt_tokens', 0),
                                'output_tokens': usage.get('completion_tokens', 0)
                            }
                            logging.info(f"Token usage from raw response token_usage: {token_usage}")
                    
                    # Additional check for usage info in the response object itself
                    if not token_usage and hasattr(raw_response, 'usage_metadata'):
                        usage = raw_response.usage_metadata
                        token_usage = {
                            'total_tokens': usage.get('total_tokens', 0),
                            'input_tokens': usage.get('input_tokens', 0),
                            'output_tokens': usage.get('output_tokens', 0)
                        }
                        logging.info(f"Token usage from usage_metadata: {token_usage}")
                    
                except Exception as raw_error:
                    logging.error(f"Raw LLM call failed: {raw_error}")
                    # Fall back to chain response without token tracking
                    cypher_response = cypher_response if 'cypher_response' in locals() else {'text': ''}
            
            # End LLM timing
            llm_end_time = time.time()
            llm_duration = llm_end_time - llm_start_time
            if self.metrics:
                self.metrics.end_llm_timing()
            
            # Calculate token generation metrics
            generation_time = llm_duration - (first_token_time or 0)
            
            cypher_query = cypher_response.get('text', '')

            # IMPORTANT: Clean the LLM response to remove explanatory text
            cypher_query = self._clean_cypher_response(cypher_query)

            logging.info(f"Generated Cypher Query:\n\n{cypher_query}")
            
            # Validate spatial query doesn't contain location filters
            if is_spatial and user_coordinates:
                self._validate_spatial_cypher(cypher_query)
            
            # If we still don't have token usage, try to estimate based on text length
            if not token_usage or token_usage.get('total_tokens', 0) == 0:
                # Rough estimation: ~4 characters per token for most models
                input_text = str(self.neo4j_client.get_schema()) + query + spatial_context + memory_context
                output_text = cypher_query
                
                estimated_input = max(1, len(input_text) // 4)
                estimated_output = max(1, len(output_text) // 4)
                estimated_total = estimated_input + estimated_output
                
                token_usage = {
                    'total_tokens': estimated_total,
                    'input_tokens': estimated_input,
                    'output_tokens': estimated_output,
                    'estimated': True
                }
                logging.info(f"Using estimated token usage: {token_usage}")
            
            # Record enhanced token usage to metrics if available
            if self.metrics and token_usage:
                self.metrics.record_enhanced_token_usage(
                    total_tokens=token_usage.get('total_tokens', 0),
                    input_tokens=token_usage.get('input_tokens', 0),
                    output_tokens=token_usage.get('output_tokens', 0),
                    generation_time=generation_time if generation_time > 0 else None,
                    time_to_first_token=first_token_time
                )
            
            # Execute Neo4j query with timing
            neo4j_start_time = time.time()
            results = self.neo4j_client.query(cypher_query)
            neo4j_duration = time.time() - neo4j_start_time
            
            logging.info(f"Result from Neo4j Database:\n\n{results}")
            logging.info(f"Query returned {len(results) if results else 0} results")
            logging.info(f"Neo4j query execution time: {neo4j_duration:.3f}s")

            return {
                'success': True,
                'results': results,
                'cypher_query': cypher_query,
                'token_usage': token_usage,
                'neo4j_duration': neo4j_duration,
                'llm_duration': llm_duration,
                'first_token_time': first_token_time,
                'generation_time': generation_time
            }
            
        except Exception as e:
            # SIMPLIFIED ERROR HANDLING - NO RATE LIMIT RETRIES
            logging.error(f"Cypher query execution failed: {str(e)}")
            return {
                'success': False,
                'error': f"Query execution failed: {str(e)}",
                'results': None,
                'token_usage': token_usage if 'token_usage' in locals() else {},
                'neo4j_duration': 0.0,
                'llm_duration': 0.0
            }

    def _retry_with_expanded_radius_and_enhanced_metrics(self, query, spatial_context, memory_context, 
                                                        user_coordinates, original_threshold):
        """Retry spatial query with expanded radius and comprehensive metrics tracking."""
        try:
            # REMOVED: Rate limiting call
        
            expanded_threshold = Config.EXPANDED_DISTANCE_THRESHOLD
            logging.info(f"Retrying spatial query with expanded radius: {expanded_threshold} miles")
            
            # Update spatial context for expanded search
            expanded_spatial_context = spatial_context.replace(
                f"DISTANCE THRESHOLD: {original_threshold} miles", 
                f"DISTANCE THRESHOLD: {expanded_threshold} miles (expanded from {original_threshold} miles)"
            ).replace(
                f"distance_threshold = {original_threshold}", 
                f"distance_threshold = {expanded_threshold}"
            ).replace(
                f"distance_miles <= {original_threshold}",
                f"distance_miles <= {expanded_threshold}"
            )
            
            # Record spatial processing time
            spatial_start_time = time.time()
            
            # Track LLM timing
            if self.metrics:
                self.metrics.start_llm_timing()
            
            llm_start_time = time.time()
            first_token_time = None
            
            # Try with callback first
            token_usage = {}
            try:
                with get_openai_callback() as cb:
                    cypher_response = self.spatial_cypher_chain.invoke({
                        "schema": self.neo4j_client.get_schema(),
                        "question": query,
                        "spatial_context": expanded_spatial_context,
                        "memory_context": memory_context,
                        "user_latitude": user_coordinates[0],
                        "user_longitude": user_coordinates[1],
                        "distance_threshold": expanded_threshold
                    })
                    
                    # Record first token time (approximate)
                    first_token_time = time.time() - llm_start_time
                    if self.metrics:
                        self.metrics.record_first_token_time()
                    
                    if cb.total_tokens > 0:
                        token_usage = {
                            'total_tokens': cb.total_tokens,
                            'input_tokens': cb.prompt_tokens,
                            'output_tokens': cb.completion_tokens
                        }
                        logging.info(f"Expanded query token usage: {token_usage}")
                        
            except Exception as e:
                logging.warning(f"Expanded query callback failed: {e}")
                # Estimate tokens if callback fails
                input_text = str(self.neo4j_client.get_schema()) + query + expanded_spatial_context + memory_context
                output_text = cypher_response.get('text', '') if 'cypher_response' in locals() else ''
                
                estimated_input = max(1, len(input_text) // 4)
                estimated_output = max(1, len(output_text) // 4)
                
                token_usage = {
                    'total_tokens': estimated_input + estimated_output,
                    'input_tokens': estimated_input,
                    'output_tokens': estimated_output,
                    'estimated': True
                }
            
            # End LLM timing
            llm_end_time = time.time()
            llm_duration = llm_end_time - llm_start_time
            generation_time = llm_duration - (first_token_time or 0)
            
            if self.metrics:
                self.metrics.end_llm_timing()
            
            expanded_cypher_query = cypher_response.get('text', '')
            expanded_cypher_query = self._clean_cypher_response(expanded_cypher_query)
            logging.info(f"Generated expanded Cypher Query:\n\n{expanded_cypher_query}")
            
            # Validate expanded spatial query
            self._validate_spatial_cypher(expanded_cypher_query)
            
            # Record spatial processing time
            spatial_duration = time.time() - spatial_start_time - llm_duration
            if self.metrics:
                self.metrics.record_processing_time('spatial', spatial_duration)
            
            # Record enhanced token usage to metrics if available
            if self.metrics and token_usage:
                self.metrics.record_enhanced_token_usage(
                    total_tokens=token_usage.get('total_tokens', 0),
                    input_tokens=token_usage.get('input_tokens', 0),
                    output_tokens=token_usage.get('output_tokens', 0),
                    generation_time=generation_time if generation_time > 0 else None,
                    time_to_first_token=first_token_time
                )
            
            # Execute expanded query with timing
            neo4j_start_time = time.time()
            expanded_results = self.neo4j_client.query(expanded_cypher_query)
            neo4j_duration = time.time() - neo4j_start_time
            
            logging.info(f"Expanded radius result from Neo4j Database:\n\n{expanded_results}")
            logging.info(f"Expanded radius result: {len(expanded_results) if expanded_results else 0} results")
            logging.info(f"Expanded Neo4j query execution time: {neo4j_duration:.3f}s")

            return {
                'success': bool(expanded_results),
                'results': expanded_results,
                'distance_threshold': expanded_threshold,
                'cypher_query': expanded_cypher_query,
                'token_usage': token_usage,
                'neo4j_duration': neo4j_duration,
                'llm_duration': llm_duration,
                'spatial_duration': spatial_duration,
                'first_token_time': first_token_time,
                'generation_time': generation_time
            }
            
        except Exception as e:
            logging.error(f"Expanded query execution failed: {str(e)}")
            return {
                'success': False,
                'error': f"Expanded query failed: {str(e)}",
                'results': None,
                'token_usage': {},
                'neo4j_duration': 0.0,
                'llm_duration': 0.0,
                'spatial_duration': 0.0
            }
    
    def _find_closest_organization_with_enhanced_metrics(self, query, spatial_context, memory_context, 
                                                        user_coordinates):
        """Find the closest organization regardless of distance with comprehensive metrics tracking."""
        try:
            # REMOVED: Rate limiting call

            logging.info("Attempting to find closest organization regardless of distance")
            
            # Update spatial context for closest search (no distance threshold)
            closest_spatial_context = spatial_context.replace(
                f"DISTANCE THRESHOLD: {Config.DEFAULT_DISTANCE_THRESHOLD} miles", 
                "DISTANCE THRESHOLD: No limit (finding closest organization)"
            ).replace(
                f"DISTANCE THRESHOLD: {Config.EXPANDED_DISTANCE_THRESHOLD} miles (expanded from {Config.DEFAULT_DISTANCE_THRESHOLD} miles)", 
                "DISTANCE THRESHOLD: No limit (finding closest organization)"
            ).replace(
                f"distance_threshold = {Config.DEFAULT_DISTANCE_THRESHOLD}", 
                "distance_threshold = 999999"  # Very large number to effectively remove distance filtering
            ).replace(
                f"distance_threshold = {Config.EXPANDED_DISTANCE_THRESHOLD}", 
                "distance_threshold = 999999"  # Very large number to effectively remove distance filtering
            ).replace(
                f"distance_miles <= {Config.DEFAULT_DISTANCE_THRESHOLD}",
                "true"  # Remove distance filtering entirely
            ).replace(
                f"distance_miles <= {Config.EXPANDED_DISTANCE_THRESHOLD}",
                "true"  # Remove distance filtering entirely
            )
            
            # Add instruction to limit to just the closest result
            closest_spatial_context += "\n\nSPECIAL INSTRUCTION: Return only the closest organization (LIMIT 1)"
            
            # Record spatial processing time
            spatial_start_time = time.time()
            
            # Track LLM timing
            if self.metrics:
                self.metrics.start_llm_timing()
            
            llm_start_time = time.time()
            first_token_time = None
            
            # Try with callback first
            token_usage = {}
            try:
                with get_openai_callback() as cb:
                    cypher_response = self.spatial_cypher_chain.invoke({
                        "schema": self.neo4j_client.get_schema(),
                        "question": query,
                        "spatial_context": closest_spatial_context,
                        "memory_context": memory_context,
                        "user_latitude": user_coordinates[0],
                        "user_longitude": user_coordinates[1],
                        "distance_threshold": 999999  # Very large number
                    })
                    
                    # Record first token time (approximate)
                    first_token_time = time.time() - llm_start_time
                    if self.metrics:
                        self.metrics.record_first_token_time()
                    
                    if cb.total_tokens > 0:
                        token_usage = {
                            'total_tokens': cb.total_tokens,
                            'input_tokens': cb.prompt_tokens,
                            'output_tokens': cb.completion_tokens
                        }
                        logging.info(f"Closest search token usage: {token_usage}")
                        
            except Exception as e:
                logging.warning(f"Closest search callback failed: {e}")
                # Estimate tokens if callback fails
                input_text = str(self.neo4j_client.get_schema()) + query + closest_spatial_context + memory_context
                output_text = cypher_response.get('text', '') if 'cypher_response' in locals() else ''
                
                estimated_input = max(1, len(input_text) // 4)
                estimated_output = max(1, len(output_text) // 4)
                
                token_usage = {
                    'total_tokens': estimated_input + estimated_output,
                    'input_tokens': estimated_input,
                    'output_tokens': estimated_output,
                    'estimated': True
                }
            
            # End LLM timing
            llm_end_time = time.time()
            llm_duration = llm_end_time - llm_start_time
            generation_time = llm_duration - (first_token_time or 0)
            
            if self.metrics:
                self.metrics.end_llm_timing()
            
            closest_cypher_query = cypher_response.get('text', '')
            closest_cypher_query = self._clean_cypher_response(closest_cypher_query)
            
            # Ensure the query has LIMIT 1 to get only the closest
            if 'LIMIT' not in closest_cypher_query.upper():
                # Add LIMIT 1 before ORDER BY if it exists, otherwise at the end
                if 'ORDER BY' in closest_cypher_query.upper():
                    closest_cypher_query = closest_cypher_query.replace(
                        'ORDER BY distance_miles ASC', 
                        'ORDER BY distance_miles ASC\nLIMIT 1'
                    )
                else:
                    closest_cypher_query += '\nLIMIT 1'
            
            logging.info(f"Generated closest organization Cypher Query:\n\n{closest_cypher_query}")
            
            # Record spatial processing time
            spatial_duration = time.time() - spatial_start_time - llm_duration
            if self.metrics:
                self.metrics.record_processing_time('spatial', spatial_duration)
            
            # Record enhanced token usage to metrics if available
            if self.metrics and token_usage:
                self.metrics.record_enhanced_token_usage(
                    total_tokens=token_usage.get('total_tokens', 0),
                    input_tokens=token_usage.get('input_tokens', 0),
                    output_tokens=token_usage.get('output_tokens', 0),
                    generation_time=generation_time if generation_time > 0 else None,
                    time_to_first_token=first_token_time
                )
            
            # Execute closest search query with timing
            neo4j_start_time = time.time()
            closest_results = self.neo4j_client.query(closest_cypher_query)
            neo4j_duration = time.time() - neo4j_start_time
            
            logging.info(f"Closest organization result from Neo4j Database:\n\n{closest_results}")
            logging.info(f"Closest organization result: {len(closest_results) if closest_results else 0} results")
            logging.info(f"Closest search Neo4j query execution time: {neo4j_duration:.3f}s")

            return {
                'success': bool(closest_results),
                'results': closest_results,
                'distance_threshold': None,  # No threshold used
                'cypher_query': closest_cypher_query,
                'token_usage': token_usage,
                'closest_search': True,
                'neo4j_duration': neo4j_duration,
                'llm_duration': llm_duration,
                'spatial_duration': spatial_duration,
                'first_token_time': first_token_time,
                'generation_time': generation_time
            }
            
        except Exception as e:
            logging.error(f"Closest organization search failed: {str(e)}")
            return {
                'success': False,
                'error': f"Closest organization search failed: {str(e)}",
                'results': None,
                'token_usage': {},
                'closest_search': True,
                'neo4j_duration': 0.0,
                'llm_duration': 0.0,
                'spatial_duration': 0.0
            }

    # ALL OTHER METHODS REMAIN UNCHANGED - just remove any rate limiting calls

    def _normalize_service_keywords(self, query):
        """Normalize service-related keywords in the query for better matching."""
        import re
        
        query_lower = query.lower()
        normalized_query = query
        
        # Apply keyword normalizations
        for original, normalized in self.keyword_normalizations.items():
            if original in query_lower:
                # Use word boundaries to avoid partial matches
                pattern = re.compile(r'\b' + re.escape(original) + r'\b', re.IGNORECASE)
                normalized_query = pattern.sub(normalized, normalized_query)
        
        if normalized_query != query:
            logging.info(f"FIXED NORMALIZATION: '{query}' -> '{normalized_query}'")
        
        return normalized_query
    
    def _extract_service_keywords(self, query):
        """Extract and expand service keywords from query using synonym mapping."""
        query_lower = query.lower()
        keywords = []
        
        # Check each service category
        for category, synonyms in self.service_synonyms.items():
            for synonym in synonyms:
                if synonym in query_lower:
                    # Add the base category keyword
                    if category not in keywords:
                        keywords.append(category)
                    break
        
        # Also extract direct keywords from normalized query
        direct_keywords = []
        
        # Common service keywords that should be searched directly
        # FIXED: Include 'wi-fi' instead of 'wifi'
        direct_service_words = [
            'wi-fi', 'computer', 'print', 'copy', 'scan', 'class', 'workshop',  # FIXED: wi-fi with hyphen
            'story time', 'meeting room', 'study room', 'book', 'appeal',
            'benefit', 'card', 'statement', 'job', 'homework', 'esl',
            'deposit', 'change', 'direct', 'shelter', 'food', 'mental health', 'substance abuse'
        ]
        
        for word in direct_service_words:
            if word in query_lower:
                direct_keywords.append(word)
        
        # Combine and deduplicate
        all_keywords = list(set(keywords + direct_keywords))
        
        if all_keywords:
            logging.info(f"FIXED: Extracted service keywords: {all_keywords}")
        
        return all_keywords
    
    def _get_primary_service_keyword(self, query):
        """Get the primary service keyword for Cypher query generation."""
        keywords = self._extract_service_keywords(query)
        
        if not keywords:
            return None
        
        # FIXED: Priority order with wi-fi properly positioned
        priority_order = [
            # Social Security specific services (most specific first)
            'appeal', 'change', 'direct', 'address', '1099', 'card', 'benefit', 'estimate', 'proof', 'history',
            'withdrawal', 'transfer', 'international', 'overnight',

            # New Categories (High Priority)
            'hotline', 'shelter', 'food', 'mental health', 'substance abuse', 'financial', 'legal',
            
            # Library Technology services - FIXED: wi-fi first
            'wi-fi', 'computer', 'print', 'copy', 'scan',  # FIXED: wi-fi instead of wifi
            
            # Library Education services
            'esl', 'homework', 'job', 'citizenship', 'class',
            
            # Library Children services
            'story', 'after', 'stem', 'summer',
            
            # Library Facilities
            'meeting', 'study', 'drop',
            
            # General services (least specific)
            'workshop', 'event', 'tour', 'game', 'book', 'parenting', 'clothing', 'hygiene'
        ]
        
        # Return the highest priority keyword found
        for priority_keyword in priority_order:
            if priority_keyword in keywords:
                logging.info(f"FIXED: Selected primary service keyword: '{priority_keyword}'")
                return priority_keyword
        
        # If no priority match, return the first keyword
        return keywords[0]
    
    def _extract_all_service_keywords(self, query):
        """
        Extract ALL service keywords from query (not just primary).
        Returns list of service keywords in order of specificity.
        
        Args:
            query (str): User query
            
        Returns:
            list: All detected service keywords
        """
        query_lower = query.lower()
        detected_services = []
        
        # Check each service category
        for category, synonyms in self.service_synonyms.items():
            for synonym in synonyms:
                if synonym in query_lower:
                    if category not in detected_services:
                        detected_services.append(category)
                    break
        
        # Also extract direct keywords
        direct_service_words = [
            'wi-fi', 'computer', 'print', 'copy', 'scan', 'class', 'workshop',
            'story time', 'meeting room', 'study room', 'book', 'appeal',
            'benefit', 'card', 'statement', 'job', 'homework', 'esl',
            'deposit', 'change', 'direct', 'shelter', 'food', 'mental health', 
            'substance abuse', 'counseling', 'therapy', 'pantry', 'meals'
        ]
        
        for word in direct_service_words:
            if word in query_lower and word not in detected_services:
                detected_services.append(word)
        
        if detected_services:
            logging.info(f"Extracted all service keywords: {detected_services}")
        
        return detected_services    
        
    def categorize_services_by_category(self, query):
        """
        Categorize requested services into their organization categories.
        Uses LLM to intelligently map services to categories based on meaning.
        Returns categories in priority order.
        
        Args:
            query (str): User query
            
        Returns:
            dict: {category_name: [services_for_that_category]}
        """
        from config import Config
        
        # Extract all service keywords
        normalized_query = self._normalize_service_keywords(query)
        all_services = self._extract_all_service_keywords(normalized_query)
        
        if not all_services:
            return {}
        
        logging.info(f"Detected services to categorize: {all_services}")
        
        # Use LLM to categorize services with ENHANCED semantic understanding
        categorization_prompt = f"""
    You are an expert at categorizing social services into organization types. Given these detected services from a user query, assign each service to the MOST APPROPRIATE category based on its SEMANTIC MEANING and PRIMARY PURPOSE.

    USER QUERY: {query}
    DETECTED SERVICES: {', '.join(all_services)}

    AVAILABLE CATEGORIES AND THEIR CORE PURPOSES:
    1. **Food Bank** - Organizations providing FOOD assistance, meals, emergency supplies, shelter, clothing, and social support services
    2. **Library** - Educational institutions offering books, computers, wi-fi, classes, programs, and community spaces  
    3. **Social Security Office** - Government offices handling benefits, retirement, disability, appeals, cards, and official documents
    4. **Mental Health** - Healthcare facilities providing therapy, counseling, psychiatric care, and mental health treatment
    5. **Temporary Shelter** - Emergency housing facilities offering shelter, housing assistance, and crisis support services

    COMPREHENSIVE SERVICE EXAMPLES BY CATEGORY:

    **Food Bank Services:**
    - FOOD RELATED: meal, meals, food, emergency food, food pantry, food delivery, nutrition, dining, lunch, dinner, breakfast
    - SHELTER/HOUSING: temporary shelter, clothing, help find housing, safe housing, short-term housing
    - SUPPORT: counseling, case management, community support, navigating the system
    - BASIC NEEDS: personal hygiene, baby supplies, home goods, toys & gifts

    **Library Services:**
    - TECHNOLOGY: wi-fi, wifi, internet, computer, computers, printing, printer, copying, scanning
    - EDUCATION: classes, workshops, ESL, GED, literacy, homework help, tutoring
    - CHILDREN: story time, after-school programs, summer programs, STEM classes
    - SPACE: meeting rooms, study rooms, books, collections, research

    **Social Security Office Services:**
    - BENEFITS: benefits, retirement, disability, SSI, medicare, social security
    - DOCUMENTS: appeal, card replacement, 1099, statements, proof of benefits
    - ACCOUNT: change address, direct deposit, earnings history

    **Mental Health Services:**
    - CLINICAL: therapy, counseling, psychiatric care, mental health evaluation, medication management
    - TREATMENT: addiction recovery, substance abuse, detox, residential treatment, outpatient treatment
    - SUPPORT: support groups, peer support, group therapy, individual counseling

    **Temporary Shelter Services:**
    - HOUSING: shelter, emergency housing, residential housing, help find housing
    - CRISIS: emergency payments, weather relief, disaster response
    - SUPPORT: case management, counseling, financial assistance

    CRITICAL SEMANTIC UNDERSTANDING RULES:
    1. **"meal" or "meals"** → Food Bank (PRIMARY: food assistance)
    2. **"food" or "dining"** → Food Bank (PRIMARY: food services)
    3. **"printer" or "printing"** → Library (PRIMARY: technology services)
    4. **"wi-fi" or "wifi" or "internet"** → Library (PRIMARY: technology access)
    5. **"computer"** → Library (PRIMARY: technology access)
    6. **"counseling"** → If mental health specific → Mental Health, otherwise → Food Bank (general support)
    7. **"shelter" or "housing"** → If emergency/crisis → Temporary Shelter, if support/navigation → Food Bank
    8. **"therapy" or "psychiatric"** → Mental Health (PRIMARY: clinical treatment)
    9. **"benefits" or "retirement"** → Social Security Office (PRIMARY: government benefits)
    10. **"appeal"** → Social Security Office (PRIMARY: decision appeals)

    MATCHING STRATEGY:
    - Understand the SEMANTIC MEANING, not just exact word matching
    - "meal" = "meals" = "food" = "dining" → All map to Food Bank
    - "printer" = "printing" → Both map to Library  
    - "computer" = "computers" → Both map to Library
    - Consider the PRIMARY PURPOSE of the service when categorizing
    - If a service fits multiple categories, choose based on PRIMARY meaning in user's context
    - Only return categories that have at least one service

    OUTPUT FORMAT (JSON only, no explanation):
    {{
        "Food Bank": ["meal"],
        "Library": ["printer"]
    }}

    Now categorize the detected services:
    """
        
        try:
            # Call LLM for categorization
            from langchain_groq import ChatGroq
            llm = ChatGroq(model=Config.LLM_MODEL, temperature=0)
            
            response = llm.invoke(categorization_prompt)
            response_text = response.content.strip()
            
            # Parse JSON response
            import json
            # Extract JSON if wrapped in markdown
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            categorized = json.loads(response_text)
            
            # Sort by category order
            ordered_categories = {}
            for category in Config.CATEGORY_ORDER:
                if category in categorized and categorized[category]:
                    ordered_categories[category] = categorized[category]
            
            logging.info(f"Services categorized by LLM: {ordered_categories}")
            return ordered_categories
            
        except Exception as e:
            logging.error(f"LLM categorization failed: {str(e)}")
            
            # Enhanced fallback with semantic understanding
            categorized = {}
            
            # Define semantic mappings for fallback
            semantic_mappings = {
                'Food Bank': ['meal', 'meals', 'food', 'dining', 'lunch', 'dinner', 'breakfast', 
                            'emergency food', 'food pantry', 'nutrition'],
                'Library': ['printer', 'printing', 'print', 'computer', 'computers', 'wifi', 'wi-fi', 
                        'internet', 'copy', 'copying', 'scan', 'scanning', 'book', 'books'],
                'Social Security Office': ['benefit', 'benefits', 'retirement', 'appeal', 'appeals', 
                                        'card', 'social security', 'disability', 'ssi'],
                'Mental Health': ['therapy', 'counseling', 'psychiatric', 'mental health', 
                                'addiction', 'substance abuse', 'recovery'],
                'Temporary Shelter': ['stay', 'shelter', 'housing', 'emergency housing']
            }
            
            for service in all_services:
                service_lower = service.lower()
                
                # Check semantic mappings
                for category, keywords in semantic_mappings.items():
                    if any(keyword in service_lower or service_lower in keyword for keyword in keywords):
                        if category not in categorized:
                            categorized[category] = []
                        if service not in categorized[category]:
                            categorized[category].append(service)
                        break
            
            # Sort by priority order
            ordered_categories = {}
            for category in Config.CATEGORY_ORDER:
                if category in categorized:
                    ordered_categories[category] = categorized[category]
            
            logging.info(f"Services categorized (enhanced fallback): {ordered_categories}")
            return ordered_categories

    def _validate_spatial_cypher(self, cypher_query):
        """Validate that spatial Cypher query doesn't contain location-based filters."""
        query_lower = cypher_query.lower()
        
        # Check for problematic location filters
        problematic_patterns = [
            r'tolower\(l\.city\)',
            r'tolower\(l\.street\)',
            r'tolower\(l\.zipcode\)',
            r'tolower\(l\.state\)',
            r'l\.city\s*contains',
            r'l\.street\s*contains',
            r'l\.zipcode\s*=',
            r'l\.state\s*='
        ]
        
        for pattern in problematic_patterns:
            if re.search(pattern, query_lower):
                logging.warning(f"SPATIAL QUERY VALIDATION WARNING: Found location filter in spatial query: {pattern}")
                logging.warning(f"This may cause incorrect results. Spatial queries should only use distance filtering.")

    def _create_service_context(self, service_keywords, primary_service):
        """Create service context to help with Cypher query generation."""
        if not service_keywords and not primary_service:
            return ""
        
        context = "\n\nSERVICE INTELLIGENCE CONTEXT:\n"
        
        if primary_service:
            context += f"Primary Service Detected: '{primary_service}'\n"
            context += f"Recommended Cypher Pattern: WHERE toLower(s.name) CONTAINS '{primary_service}'\n"
        
        if service_keywords:
            context += f"All Service Keywords: {', '.join(service_keywords)}\n"
        
        # Add specific guidance based on detected services
        service_guidance = {
            'appeal': "Use 'appeal' to match 'Appeal a Decision' service",
            'benefit': "Use 'benefit' to match various benefit-related services",
            'wi-fi': "Use 'wi-fi' to match 'Wi-Fi' and 'Public Computers, Wi-Fi'",
            'computer': "Use 'computer' to match 'Public Computers' and 'Computer Labs'",
            'print': "Use 'print' to match 'Printing' services",
            'story': "Use 'story' to match 'Story Time' and 'Story Times'",
            'job': "Use 'job' to match 'Job Assistance' and 'Job Search Assistance'",
            'homework': "Use 'homework' to match 'Homework Help'",
            'esl': "Use 'esl' to match 'ESL Classes' and 'ESL Services'",
            'shelter': "Use 'shelter' or 'housing' for shelter-related queries",
            'food': "Use 'food' or 'meals' for food bank queries",
            'mental health': "Use 'mental health', 'counseling', or 'therapy' for mental health services",
            'substance abuse': "Use 'substance abuse', 'addiction', or 'recovery' for related services"
        }
        
        if primary_service in service_guidance:
            context += f"Service Guidance: {service_guidance[primary_service]}\n"
        
        return context

    def process_query(self, user_query):
        """Process a user query through the complete pipeline with enhanced metrics."""
        try:
            logging.info(f"Processing query: {user_query}")
            
            # Step 0: Normalize service keywords and extract service context
            normalization_start_time = time.time()
            normalized_query = self._normalize_service_keywords(user_query)
            service_keywords = self._extract_service_keywords(normalized_query)
            primary_service = self._get_primary_service_keyword(normalized_query)
            normalization_duration = time.time() - normalization_start_time
            
            if normalized_query != user_query:
                logging.info(f"Normalized query: {user_query} -> {normalized_query}")
            if service_keywords:
                logging.info(f"Detected service keywords: {service_keywords}")
            if primary_service:
                logging.info(f"Primary service keyword: {primary_service}")
            
            # Step 1: Check if we should use memory
            memory_start_time = time.time()
            use_memory = self.memory.should_use_memory(normalized_query)
            memory_duration = time.time() - memory_start_time
            logging.info(f"Memory usage decision: {use_memory}")
            
            # Record memory processing time
            if self.metrics:
                self.metrics.record_processing_time('memory', memory_duration)
            
            # Step 2: Process query with memory if applicable
            processed_query = normalized_query
            memory_context = ""
            
            if use_memory:
                processed_query = self.memory.substitute_pronouns(normalized_query)
                memory_context = self.memory.get_memory_context()
                logging.info("Using memory context for query processing")
            
            # Step 3: Detect spatial requirements
            spatial_detection_start_time = time.time()
            is_spatial_query = self.spatial_intel.detect_spatial_query(processed_query)
            spatial_detection_duration = time.time() - spatial_detection_start_time
            logging.info(f"Spatial query detection: {is_spatial_query}")
            
            # Step 4: Process spatial context if needed
            spatial_context = ""
            spatial_info = None
            user_coordinates = None
            distance_threshold = None
            
            if is_spatial_query:
                spatial_result = self._process_spatial_query(processed_query)
                if not spatial_result['success']:
                    return spatial_result
                
                spatial_context = spatial_result['spatial_context']
                spatial_info = spatial_result['spatial_info']
                user_coordinates = spatial_result['user_coordinates']
                distance_threshold = spatial_result['distance_threshold']
            
            # Step 5: Enhance contexts with service intelligence
            if service_keywords or primary_service:
                service_context = self._create_service_context(service_keywords, primary_service)
                memory_context += service_context
                spatial_context += service_context
            
            # Step 6: Generate and execute Cypher query with enhanced metrics tracking
            query_result = self._execute_cypher_query_with_enhanced_metrics(
                processed_query, is_spatial_query, spatial_context, 
                memory_context, user_coordinates, distance_threshold
            )
            
            # Record Neo4j duration to metrics
            if self.metrics and 'neo4j_duration' in query_result:
                self.metrics.record_query_result(
                    success=query_result['success'],
                    result_count=len(query_result['results']) if query_result['results'] else 0,
                    expanded_search=False,
                    error_message=query_result.get('error'),
                    cypher_query=query_result.get('cypher_query'),
                    neo4j_duration=query_result['neo4j_duration']
                )
            
            if query_result['success'] and not query_result['results']:
                # Try expanded radius for spatial queries if no results
                if is_spatial_query and distance_threshold < Config.EXPANDED_DISTANCE_THRESHOLD:
                    logging.info("Attempting expanded radius search")
                    expanded_result = self._retry_with_expanded_radius_and_enhanced_metrics(
                        processed_query, spatial_context, memory_context,
                        user_coordinates, distance_threshold
                    )
                    
                    # If the expanded search found something, replace the original result
                    if expanded_result['success'] and expanded_result['results']:
                        if spatial_info:
                            spatial_info['distance_threshold'] = expanded_result['distance_threshold']
                        # Combine metrics from both attempts
                        original_metrics = self._extract_metrics_from_result(query_result)
                        expanded_metrics = self._extract_metrics_from_result(expanded_result)
                        combined_metrics = self._combine_metrics(original_metrics, expanded_metrics)
                        query_result = expanded_result
                        query_result['expanded_radius'] = True
                        query_result.update(combined_metrics)
                    
                    # If expanded search also failed, try finding closest organization
                    elif not expanded_result['results'] and is_spatial_query:
                        logging.info("Attempting closest organization search")
                        closest_result = self._find_closest_organization_with_enhanced_metrics(
                            processed_query, spatial_context, memory_context, user_coordinates
                        )
                        
                        # If closest search found something, replace the result
                        if closest_result['success'] and closest_result['results']:
                            if spatial_info:
                                spatial_info['distance_threshold'] = None  # No threshold for closest search
                            # Combine metrics from all three attempts
                            original_metrics = self._extract_metrics_from_result(query_result)
                            expanded_metrics = self._extract_metrics_from_result(expanded_result)
                            closest_metrics = self._extract_metrics_from_result(closest_result)
                            combined_metrics = self._combine_metrics(
                                self._combine_metrics(original_metrics, expanded_metrics), 
                                closest_metrics
                            )
                            query_result = closest_result
                            query_result['expanded_radius'] = True
                            query_result['closest_search'] = True
                            query_result.update(combined_metrics)
            
            # Step 7: Update memory if we got results
            results = query_result['results']
            if results and not use_memory:
                self.memory.add_interaction(user_query, results, spatial_info)
                logging.info(f"Added interaction to memory: {len(results)} results stored")
            elif not results and not use_memory:
                self.memory.clear_memory()
                logging.info("Cleared memory due to failed new query")
            
            return {
                'success': True,
                'results': results,
                'spatial_info': spatial_info,
                'used_memory': use_memory,
                'expanded_radius': query_result.get('expanded_radius', False),
                'closest_search': query_result.get('closest_search', False),
                'is_spatial': is_spatial_query,
                'token_usage': query_result.get('token_usage', {}),
                'cypher_query': query_result.get('cypher_query'),
                'service_keywords': service_keywords,
                'primary_service': primary_service,
                # Enhanced metrics
                'neo4j_duration': query_result.get('neo4j_duration', 0.0),
                'llm_duration': query_result.get('llm_duration', 0.0),
                'spatial_duration': query_result.get('spatial_duration', 0.0),
                'first_token_time': query_result.get('first_token_time'),
                'generation_time': query_result.get('generation_time'),
                'normalization_duration': normalization_duration,
                'memory_duration': memory_duration,
                'spatial_detection_duration': spatial_detection_duration
            }
            
        except Exception as e:
            logging.error(f"Query processing failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'results': None,
                'spatial_info': None,
                'used_memory': False,
                'expanded_radius': False,
                'closest_search': False,
                'is_spatial': False,
                'token_usage': {},
                'service_keywords': [],
                'primary_service': None,
                # Enhanced metrics (default values)
                'neo4j_duration': 0.0,
                'llm_duration': 0.0,
                'spatial_duration': 0.0,
                'first_token_time': None,
                'generation_time': None,
                'normalization_duration': 0.0,
                'memory_duration': 0.0,
                'spatial_detection_duration': 0.0
            }
    
    def _extract_metrics_from_result(self, result):
        """Extract metrics from a query result for combining."""
        return {
            'neo4j_duration': result.get('neo4j_duration', 0.0),
            'llm_duration': result.get('llm_duration', 0.0),
            'spatial_duration': result.get('spatial_duration', 0.0),
            'token_usage': result.get('token_usage', {}),
            'first_token_time': result.get('first_token_time'),
            'generation_time': result.get('generation_time')
        }
    
    def _combine_metrics(self, metrics1, metrics2):
        """Combine metrics from multiple query attempts."""
        combined_token_usage = self._combine_token_usage(
            metrics1.get('token_usage', {}), 
            metrics2.get('token_usage', {})
        )
        
        return {
            'neo4j_duration': metrics1.get('neo4j_duration', 0.0) + metrics2.get('neo4j_duration', 0.0),
            'llm_duration': metrics1.get('llm_duration', 0.0) + metrics2.get('llm_duration', 0.0),
            'spatial_duration': metrics1.get('spatial_duration', 0.0) + metrics2.get('spatial_duration', 0.0),
            'token_usage': combined_token_usage,
            'first_token_time': metrics1.get('first_token_time') or metrics2.get('first_token_time'),
            'generation_time': (metrics1.get('generation_time') or 0.0) + (metrics2.get('generation_time') or 0.0)
        }
    
    def _process_spatial_query(self, query):
        """Process spatial aspects of a query with timing."""
        try:
            spatial_start_time = time.time()
            
            # Extract location from query
            location_text = self.spatial_intel.extract_location_from_query(query)
            
            if not location_text:
                return {
                    'success': False,
                    'error': "Spatial keywords detected but no location extracted"
                }
            
            # Geocode location with timing
            geocoding_start_time = time.time()
            user_coordinates = self.spatial_intel.geocode_location(location_text)
            geocoding_duration = time.time() - geocoding_start_time
            
            if not user_coordinates:
                # Record failed geocoding
                if self.metrics:
                    self.metrics.record_geocoding(False, location_text, geocoding_duration)
                return {
                    'success': False,
                    'error': f"Could not geocode location: {location_text}"
                }
            
            # Record successful geocoding
            if self.metrics:
                self.metrics.record_geocoding(True, location_text, geocoding_duration)
            
            # Get distance threshold
            distance_threshold = self.spatial_intel.get_distance_threshold(query)
            
            # Create spatial context with clear instructions
            spatial_context = self.spatial_intel.create_spatial_context(
                user_coordinates, distance_threshold, location_text
            )
            
            # Create spatial info
            spatial_info = self.spatial_intel.create_spatial_info(
                location_text, user_coordinates, distance_threshold
            )
            
            # Record total spatial processing time
            total_spatial_duration = time.time() - spatial_start_time
            if self.metrics:
                self.metrics.record_processing_time('spatial', total_spatial_duration)
            
            logging.info(f"Spatial processing successful: {location_text} -> {user_coordinates}, threshold: {distance_threshold}")
            logging.info(f"Spatial processing time: {total_spatial_duration:.3f}s (geocoding: {geocoding_duration:.3f}s)")
            
            return {
                'success': True,
                'spatial_context': spatial_context,
                'spatial_info': spatial_info,
                'user_coordinates': user_coordinates,
                'distance_threshold': distance_threshold,
                'location_text': location_text,
                'spatial_duration': total_spatial_duration,
                'geocoding_duration': geocoding_duration
            }
            
        except Exception as e:
            logging.error(f"Spatial processing failed: {str(e)}")
            return {
                'success': False,
                'error': f"Spatial processing error: {str(e)}"
            }
    
    def _combine_token_usage(self, usage1, usage2):
        """Combine token usage from multiple LLM calls."""
        return {
            'total_tokens': usage1.get('total_tokens', 0) + usage2.get('total_tokens', 0),
            'input_tokens': usage1.get('input_tokens', 0) + usage2.get('input_tokens', 0),
            'output_tokens': usage1.get('output_tokens', 0) + usage2.get('output_tokens', 0)
        }
    
    # Keep all the other methods from the original class unchanged for backward compatibility
    def is_simple_followup(self, query):
        """Check if query is a simple follow-up that can use cached results."""
        return self.memory.is_simple_followup(query)
    
    def is_focused_followup(self, query):
        """Check if query is a focused follow-up requiring specific answer."""
        return self.memory.is_focused_followup(query)
    
    def get_cached_results(self):
        """Get cached results from memory."""
        return self.memory.current_context
    
    def has_spatial_memory(self):
        """Check if last query had spatial context."""
        return self.memory.last_spatial_info is not None
    
    def clear_memory(self):
        """Clear conversation memory."""
        self.memory.clear_memory()
    
    def get_memory_stats(self):
        """Get memory statistics."""
        return {
            'interaction_count': self.memory.get_interaction_count(),
            'last_result_count': self.memory.get_last_result_count(),
            'has_context': self.memory.current_context is not None,
            'has_spatial_context': self.memory.last_spatial_info is not None
        }
    
    def _clean_cypher_response(self, cypher_response_text):
        """
        Clean the LLM response to extract only the executable Cypher query.
        Removes explanatory text, markdown formatting, and fixes curly brace escaping.
        
        Args:
            cypher_response_text (str): Raw response from LLM
            
        Returns:
            str: Clean Cypher query ready for execution
        """
        cypher_text = cypher_response_text.strip()
        
        # Remove common prefixes that LLMs add
        prefixes_to_remove = [
            "Here is the Cypher query:",
            "Here's the Cypher query:",
            "The Cypher query is:",
            "Cypher query:",
            "Query:",
            "Here is the query:",
            "Here's the query:",
        ]
        
        for prefix in prefixes_to_remove:
            if cypher_text.lower().startswith(prefix.lower()):
                cypher_text = cypher_text[len(prefix):].strip()
                break
        
        # Remove markdown code blocks
        if cypher_text.startswith("```"):
            # Find the end of the opening code block
            lines = cypher_text.split('\n')
            if len(lines) > 1:
                # Remove first line (opening ```)
                lines = lines[1:]
                # Remove last line if it's closing ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cypher_text = '\n'.join(lines)
        
        # Remove any remaining ``` at the end
        cypher_text = cypher_text.replace("```", "").strip()
        
        # CRITICAL FIX: Convert escaped curly braces back to Neo4j format
        # LangChain template escaping creates {{{{ and }}}} 
        # We need to convert them back to single { and } for Neo4j
        
         # Fix EXISTS clause braces: {{{{ becomes {
        cypher_text = cypher_text.replace("{{", "{")
        cypher_text = cypher_text.replace("}}", "}")
        
        # Keep COLLECT braces as double: {{service becomes {service
        # The COLLECT pattern should remain as {service: s.name, type: r.type}
        # This is already handled correctly by the above replacements
        
        # Additional cleanup: remove any non-Cypher explanatory text at the beginning
        lines = cypher_text.split('\n')
        cypher_start_keywords = ['MATCH', 'OPTIONAL', 'WITH', 'CREATE', 'MERGE', 'DELETE', 'DETACH', 'SET', 'REMOVE', 'RETURN', 'CALL', 'USING', 'UNWIND']
        
        # Find the first line that starts with a Cypher keyword
        start_index = 0
        for i, line in enumerate(lines):
            line_trimmed = line.strip().upper()
            if any(line_trimmed.startswith(keyword) for keyword in cypher_start_keywords):
                start_index = i
                break
        
        # Take everything from the first Cypher line onwards
        if start_index > 0:
            cypher_text = '\n'.join(lines[start_index:])
        
        # Final cleanup
        cypher_text = cypher_text.strip()
        
        logging.info(f"Cleaned Cypher query from LLM response. Original length: {len(cypher_response_text)}, Cleaned length: {len(cypher_text)}")
        logging.info(f"Curly brace conversion applied for Neo4j compatibility")
        
        return cypher_text