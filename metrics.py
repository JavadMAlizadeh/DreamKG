"""
Enhanced Metrics Collector module for the Neo4j Organization Information System.
Tracks comprehensive statistics about queries, performance, usage patterns, and detailed token/latency metrics.
"""

import logging
import time
from datetime import datetime
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import json


@dataclass
class DetailedTokenMetrics:
    """Data class for detailed token metrics."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    token_generation_rate: float = 0.0  # tokens per second
    time_to_first_token: Optional[float] = None  # seconds
    inter_token_arrival_time: Optional[float] = None  # average time between tokens


@dataclass
class DetailedLatencyMetrics:
    """Data class for detailed latency metrics."""
    total_latency: float = 0.0
    internal_processing_latency: float = 0.0  # Time spent on internal processing
    llm_api_latency: float = 0.0  # Time spent waiting for LLM API
    local_processing_time: float = 0.0  # Time spent on local operations
    time_to_first_token: Optional[float] = None
    token_generation_time: Optional[float] = None  # Time from first token to last token


@dataclass
class QueryMetrics:
    """Data class for individual query metrics with enhanced token and latency tracking."""
    timestamp: datetime
    query: str
    success: bool
    
    # Enhanced latency metrics
    latency_metrics: DetailedLatencyMetrics = field(default_factory=DetailedLatencyMetrics)
    
    # Enhanced token metrics
    token_metrics: DetailedTokenMetrics = field(default_factory=DetailedTokenMetrics)
    
    # Original fields for backward compatibility
    is_spatial: bool = False
    used_memory: bool = False
    is_focused: bool = False
    result_count: int = 0
    geocoding_success: bool = False
    expanded_search: bool = False
    location_text: Optional[str] = None
    distance_threshold: Optional[float] = None
    error_message: Optional[str] = None
    cypher_query: Optional[str] = None
    
    # Timing breakdown tracking
    neo4j_query_time: float = 0.0
    geocoding_time: float = 0.0
    spatial_processing_time: float = 0.0
    memory_processing_time: float = 0.0


@dataclass
class SessionStats:
    """Data class for session-level statistics with enhanced metrics."""
    total_queries: int = 0
    successful_queries: int = 0
    
    # Enhanced latency statistics
    total_latency: float = 0.0
    min_latency: float = float('inf')
    max_latency: float = 0.0
    total_internal_processing_latency: float = 0.0
    total_llm_api_latency: float = 0.0
    total_local_processing_time: float = 0.0
    min_llm_latency: float = float('inf')
    max_llm_latency: float = 0.0
    
    # Enhanced token statistics
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_token_generation_time: float = 0.0
    total_time_to_first_token: float = 0.0
    queries_with_ttft: int = 0  # Queries that have time-to-first-token data
    
    # Processing time breakdowns
    total_neo4j_time: float = 0.0
    total_geocoding_time: float = 0.0
    total_spatial_processing_time: float = 0.0
    total_memory_processing_time: float = 0.0
    
    # Original fields for backward compatibility
    spatial_queries: int = 0
    memory_usage_count: int = 0
    focused_queries: int = 0
    geocoding_success_count: int = 0
    expanded_searches: int = 0
    zero_result_queries: int = 0
    location_requests: Counter = field(default_factory=Counter)
    query_categories: Counter = field(default_factory=Counter)
    error_types: Counter = field(default_factory=Counter)
    hourly_usage: Counter = field(default_factory=Counter)


class MetricsCollector:
    """
    Enhanced comprehensive metrics collection system with detailed token and latency tracking.
    """
    
    def __init__(self, session_id: str = None):
        """
        Initialize metrics collector with session tracking and enhanced timing.
        
        Args:
            session_id (str): Unique session identifier
        """
        self.session_id = session_id or f"session_{int(time.time())}"
        self.session_start = datetime.now()
        self.query_history: List[QueryMetrics] = []
        self.stats = SessionStats()
        
        # Enhanced timing tracking
        self.current_query_start: float = 0.0
        self.current_internal_start: float = 0.0
        self.current_llm_start: float = 0.0
        self.current_llm_end: float = 0.0
        self.current_first_token_time: Optional[float] = None
        self.current_query_data: Dict[str, Any] = {}
        
        logging.info(f"Enhanced MetricsCollector initialized for session: {self.session_id}")
    
    def start_query(self, query: str) -> str:
        """
        Start tracking a new query with enhanced timing.
        
        Args:
            query (str): User query text
            
        Returns:
            str: Query tracking ID
        """
        self.current_query_start = time.time()
        self.current_internal_start = time.time()
        query_id = f"{self.session_id}_{len(self.query_history)}"
        
        self.current_query_data = {
            'query_id': query_id,
            'query': query,
            'timestamp': datetime.now(),
            'start_time': self.current_query_start,
            'internal_start_time': self.current_internal_start,
            'processing_times': {
                'neo4j': 0.0,
                'geocoding': 0.0,
                'spatial': 0.0,
                'memory': 0.0
            }
        }
        
        # Reset timing trackers
        self.current_llm_start = 0.0
        self.current_llm_end = 0.0
        self.current_first_token_time = None
        
        logging.info(f"METRICS: Starting enhanced query tracking - ID: {query_id}, Query: '{query}'")
        return query_id
    
    def start_llm_timing(self):
        """Start timing LLM API calls."""
        self.current_llm_start = time.time()
        logging.info("METRICS: Starting LLM timing")
    
    def end_llm_timing(self):
        """End timing LLM API calls."""
        self.current_llm_end = time.time()
        if self.current_llm_start > 0:
            llm_latency = self.current_llm_end - self.current_llm_start
            self.current_query_data['llm_latency'] = llm_latency
            logging.info(f"METRICS: LLM latency recorded: {llm_latency:.3f}s")
    
    def record_first_token_time(self, first_token_time: float = None):
        """
        Record time to first token.
        
        Args:
            first_token_time (float): Time when first token was received, or None to use current time
        """
        if first_token_time is None:
            first_token_time = time.time()
        
        if self.current_llm_start > 0:
            ttft = first_token_time - self.current_llm_start
            self.current_first_token_time = ttft
            self.current_query_data['time_to_first_token'] = ttft
            logging.info(f"METRICS: Time to first token: {ttft:.3f}s")
    
    def record_processing_time(self, operation: str, duration: float):
        """
        Record processing time for specific operations.
        
        Args:
            operation (str): Operation name ('neo4j', 'geocoding', 'spatial', 'memory')
            duration (float): Duration in seconds
        """
        if operation in self.current_query_data.get('processing_times', {}):
            self.current_query_data['processing_times'][operation] = duration
            logging.info(f"METRICS: {operation} processing time: {duration:.3f}s")
    
    def record_spatial_detection(self, is_spatial: bool, location_text: str = None, 
                                distance_threshold: float = None):
        """Record spatial query detection results."""
        self.current_query_data.update({
            'is_spatial': is_spatial,
            'location_text': location_text,
            'distance_threshold': distance_threshold
        })
        
        if is_spatial:
            logging.info(f"METRICS: Spatial query detected - Location: {location_text}, Threshold: {distance_threshold}")
    
    def record_geocoding(self, success: bool, location_text: str = None, duration: float = None):
        """
        Record geocoding attempt results with timing.
        
        Args:
            success (bool): Whether geocoding was successful
            location_text (str): Location that was geocoded
            duration (float): Time taken for geocoding
        """
        self.current_query_data['geocoding_success'] = success
        if duration is not None:
            self.record_processing_time('geocoding', duration)
        
        if success:
            logging.info(f"METRICS: Geocoding successful for: {location_text}")
        else:
            logging.info(f"METRICS: Geocoding failed for: {location_text}")
    
    def record_memory_usage(self, used_memory: bool, is_focused: bool = False, duration: float = None):
        """
        Record memory usage in query processing with timing.
        
        Args:
            used_memory (bool): Whether memory was used
            is_focused (bool): Whether this was a focused follow-up
            duration (float): Time taken for memory processing
        """
        self.current_query_data.update({
            'used_memory': used_memory,
            'is_focused': is_focused
        })
        
        if duration is not None:
            self.record_processing_time('memory', duration)
        
        if used_memory:
            logging.info(f"METRICS: Memory used - Focused: {is_focused}")
    
    def record_query_result(self, success: bool, result_count: int = 0, 
                           expanded_search: bool = False, error_message: str = None,
                           cypher_query: str = None, neo4j_duration: float = None):
        """
        Record query execution results with Neo4j timing.
        
        Args:
            success (bool): Whether query was successful
            result_count (int): Number of results returned
            expanded_search (bool): Whether search radius was expanded
            error_message (str): Error message if failed
            cypher_query (str): Generated Cypher query
            neo4j_duration (float): Time taken for Neo4j query execution
        """
        self.current_query_data.update({
            'success': success,
            'result_count': result_count,
            'expanded_search': expanded_search,
            'error_message': error_message,
            'cypher_query': cypher_query
        })
        
        if neo4j_duration is not None:
            self.record_processing_time('neo4j', neo4j_duration)
        
        logging.info(f"METRICS: Query result - Success: {success}, Results: {result_count}, Expanded: {expanded_search}")
    
    def record_enhanced_token_usage(self, total_tokens: int = 0, input_tokens: int = 0, 
                                   output_tokens: int = 0, generation_time: float = None,
                                   time_to_first_token: float = None):
        """
        Record enhanced LLM token usage with timing information.
        
        Args:
            total_tokens (int): Total tokens used
            input_tokens (int): Input tokens used
            output_tokens (int): Output tokens used
            generation_time (float): Time taken to generate all tokens
            time_to_first_token (float): Time to first token
        """
        token_data = {
            'tokens_used': total_tokens,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens
        }
        
        # Calculate token generation rate
        if generation_time and generation_time > 0 and output_tokens > 0:
            token_generation_rate = output_tokens / generation_time
            token_data['token_generation_rate'] = token_generation_rate
            token_data['token_generation_time'] = generation_time
        
        if time_to_first_token is not None:
            token_data['time_to_first_token'] = time_to_first_token
        
        # Calculate inter-token arrival time
        if generation_time and output_tokens > 1:
            # Subtract time to first token to get time for remaining tokens
            remaining_time = generation_time - (time_to_first_token or 0)
            if remaining_time > 0:
                inter_token_time = remaining_time / (output_tokens - 1)
                token_data['inter_token_arrival_time'] = inter_token_time
        
        self.current_query_data.update(token_data)
        
        logging.info(f"METRICS: Enhanced token usage - Total: {total_tokens}, "
                    f"Rate: {token_data.get('token_generation_rate', 0):.1f} tokens/sec")
    
    def end_query(self) -> QueryMetrics:
        """
        End query tracking and record comprehensive metrics.
        
        Returns:
            QueryMetrics: Complete query metrics with enhanced tracking
        """
        if not self.current_query_data:
            logging.warning("METRICS: No active query to end")
            return None
        
        # Calculate comprehensive latencies
        end_time = time.time()
        total_latency = end_time - self.current_query_data.get('start_time', end_time)
        
        # Calculate internal processing latency (total - LLM time)
        llm_latency = self.current_query_data.get('llm_latency', 0.0)
        internal_processing_latency = total_latency - llm_latency
        
        # Calculate local processing time (sum of individual operations)
        processing_times = self.current_query_data.get('processing_times', {})
        local_processing_time = sum(processing_times.values())
        
        # Create enhanced latency metrics
        latency_metrics = DetailedLatencyMetrics(
            total_latency=total_latency,
            internal_processing_latency=internal_processing_latency,
            llm_api_latency=llm_latency,
            local_processing_time=local_processing_time,
            time_to_first_token=self.current_query_data.get('time_to_first_token'),
            token_generation_time=self.current_query_data.get('token_generation_time')
        )
        
        # Create enhanced token metrics
        token_metrics = DetailedTokenMetrics(
            input_tokens=self.current_query_data.get('input_tokens', 0),
            output_tokens=self.current_query_data.get('output_tokens', 0),
            total_tokens=self.current_query_data.get('tokens_used', 0),
            token_generation_rate=self.current_query_data.get('token_generation_rate', 0.0),
            time_to_first_token=self.current_query_data.get('time_to_first_token'),
            inter_token_arrival_time=self.current_query_data.get('inter_token_arrival_time')
        )
        
        # Create comprehensive query metrics object
        query_metrics = QueryMetrics(
            timestamp=self.current_query_data.get('timestamp', datetime.now()),
            query=self.current_query_data.get('query', ''),
            success=self.current_query_data.get('success', False),
            latency_metrics=latency_metrics,
            token_metrics=token_metrics,
            
            # Original fields for backward compatibility
            is_spatial=self.current_query_data.get('is_spatial', False),
            used_memory=self.current_query_data.get('used_memory', False),
            is_focused=self.current_query_data.get('is_focused', False),
            result_count=self.current_query_data.get('result_count', 0),
            geocoding_success=self.current_query_data.get('geocoding_success', False),
            expanded_search=self.current_query_data.get('expanded_search', False),
            location_text=self.current_query_data.get('location_text'),
            distance_threshold=self.current_query_data.get('distance_threshold'),
            error_message=self.current_query_data.get('error_message'),
            cypher_query=self.current_query_data.get('cypher_query'),
            
            # Processing time breakdowns
            neo4j_query_time=processing_times.get('neo4j', 0.0),
            geocoding_time=processing_times.get('geocoding', 0.0),
            spatial_processing_time=processing_times.get('spatial', 0.0),
            memory_processing_time=processing_times.get('memory', 0.0)
        )
        
        # Add to history
        self.query_history.append(query_metrics)
        
        # Update session statistics
        self._update_session_stats(query_metrics)
        
        # Log completion with enhanced metrics
        logging.info(f"METRICS: Enhanced query completed - "
                    f"Total: {total_latency:.3f}s, "
                    f"LLM: {llm_latency:.3f}s, "
                    f"Internal: {internal_processing_latency:.3f}s, "
                    f"Tokens: {token_metrics.total_tokens}, "
                    f"Rate: {token_metrics.token_generation_rate:.1f} tok/s")
        
        # Clear current query data
        self.current_query_data = {}
        
        return query_metrics
    
    def _update_session_stats(self, query_metrics: QueryMetrics):
        """
        Update session-level statistics with enhanced metrics.
        
        Args:
            query_metrics (QueryMetrics): Query metrics to incorporate
        """
        self.stats.total_queries += 1
        
        if query_metrics.success:
            self.stats.successful_queries += 1
        
        # Enhanced latency statistics
        latency = query_metrics.latency_metrics
        self.stats.total_latency += latency.total_latency
        self.stats.min_latency = min(self.stats.min_latency, latency.total_latency)
        self.stats.max_latency = max(self.stats.max_latency, latency.total_latency)
        self.stats.total_internal_processing_latency += latency.internal_processing_latency
        self.stats.total_llm_api_latency += latency.llm_api_latency
        self.stats.total_local_processing_time += latency.local_processing_time
        
        if latency.llm_api_latency > 0:
            self.stats.min_llm_latency = min(self.stats.min_llm_latency, latency.llm_api_latency)
            self.stats.max_llm_latency = max(self.stats.max_llm_latency, latency.llm_api_latency)
        
        # Enhanced token statistics
        tokens = query_metrics.token_metrics
        self.stats.total_tokens += tokens.total_tokens
        self.stats.total_input_tokens += tokens.input_tokens
        self.stats.total_output_tokens += tokens.output_tokens
        
        if tokens.time_to_first_token is not None:
            self.stats.total_time_to_first_token += tokens.time_to_first_token
            self.stats.queries_with_ttft += 1
        
        if latency.token_generation_time:
            self.stats.total_token_generation_time += latency.token_generation_time
        
        # Processing time breakdowns
        self.stats.total_neo4j_time += query_metrics.neo4j_query_time
        self.stats.total_geocoding_time += query_metrics.geocoding_time
        self.stats.total_spatial_processing_time += query_metrics.spatial_processing_time
        self.stats.total_memory_processing_time += query_metrics.memory_processing_time
        
        # Original statistics (unchanged)
        if query_metrics.is_spatial:
            self.stats.spatial_queries += 1
        if query_metrics.used_memory:
            self.stats.memory_usage_count += 1
        if query_metrics.is_focused:
            self.stats.focused_queries += 1
        if query_metrics.geocoding_success:
            self.stats.geocoding_success_count += 1
        if query_metrics.expanded_search:
            self.stats.expanded_searches += 1
        if query_metrics.result_count == 0:
            self.stats.zero_result_queries += 1
        
        # Location tracking
        if query_metrics.location_text:
            self.stats.location_requests[query_metrics.location_text.lower()] += 1
        
        # Error tracking
        if query_metrics.error_message:
            error_type = self._categorize_error(query_metrics.error_message)
            self.stats.error_types[error_type] += 1
        
        # Query categorization
        category = self._categorize_query(query_metrics.query)
        self.stats.query_categories[category] += 1
        
        # Hourly usage
        hour = query_metrics.timestamp.hour
        self.stats.hourly_usage[hour] += 1
    
    def _categorize_error(self, error_message: str) -> str:
        """Categorize error messages."""
        error_lower = error_message.lower()
        if 'geocode' in error_lower:
            return 'geocoding'
        elif 'timeout' in error_lower:
            return 'timeout'
        elif 'connection' in error_lower:
            return 'connection'
        elif 'query' in error_lower:
            return 'query_execution'
        else:
            return 'other'
    
    def _categorize_query(self, query: str) -> str:
        """Categorize queries by type."""
        query_lower = query.lower()
        if any(word in query_lower for word in ['library', 'libraries']):
            return 'library'
        elif any(word in query_lower for word in ['social security', 'ss office']):
            return 'social_security'
        elif any(word in query_lower for word in ['wifi', 'computer', 'internet']):
            return 'technology'
        elif any(word in query_lower for word in ['hour', 'open', 'close']):
            return 'hours'
        elif any(word in query_lower for word in ['service', 'services']):
            return 'services'
        else:
            return 'other'
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics with enhanced token and latency metrics.
        
        Returns:
            Dict: Complete statistics dictionary with enhanced metrics
        """
        if self.stats.total_queries == 0:
            return {
                'session_info': {
                    'session_id': self.session_id,
                    'start_time': self.session_start.isoformat(),
                    'duration': str(datetime.now() - self.session_start),
                    'total_queries': 0
                },
                'message': 'No queries processed yet'
            }
        
        # Calculate percentages and averages
        success_rate = (self.stats.successful_queries / self.stats.total_queries) * 100
        avg_total_latency = self.stats.total_latency / self.stats.total_queries
        avg_internal_latency = self.stats.total_internal_processing_latency / self.stats.total_queries
        avg_llm_latency = self.stats.total_llm_api_latency / self.stats.total_queries
        avg_local_processing = self.stats.total_local_processing_time / self.stats.total_queries
        
        # Token averages
        avg_tokens = self.stats.total_tokens / self.stats.total_queries if self.stats.total_queries > 0 else 0
        avg_input_tokens = self.stats.total_input_tokens / self.stats.total_queries if self.stats.total_queries > 0 else 0
        avg_output_tokens = self.stats.total_output_tokens / self.stats.total_queries if self.stats.total_queries > 0 else 0
        
        # Time to first token average
        avg_ttft = self.stats.total_time_to_first_token / self.stats.queries_with_ttft if self.stats.queries_with_ttft > 0 else 0
        
        # Token generation rate average
        avg_token_gen_rate = 0.0
        if self.stats.total_token_generation_time > 0 and self.stats.total_output_tokens > 0:
            avg_token_gen_rate = self.stats.total_output_tokens / self.stats.total_token_generation_time
        
        # Processing time averages
        avg_neo4j_time = self.stats.total_neo4j_time / self.stats.total_queries
        avg_geocoding_time = self.stats.total_geocoding_time / self.stats.total_queries
        avg_spatial_time = self.stats.total_spatial_processing_time / self.stats.total_queries
        avg_memory_time = self.stats.total_memory_processing_time / self.stats.total_queries
        
        # Feature usage percentages
        spatial_percentage = (self.stats.spatial_queries / self.stats.total_queries) * 100
        memory_percentage = (self.stats.memory_usage_count / self.stats.total_queries) * 100
        focused_percentage = (self.stats.focused_queries / self.stats.total_queries) * 100
        geocoding_percentage = (self.stats.geocoding_success_count / max(self.stats.spatial_queries, 1)) * 100
        expanded_percentage = (self.stats.expanded_searches / self.stats.total_queries) * 100
        zero_results_percentage = (self.stats.zero_result_queries / self.stats.total_queries) * 100
        
        return {
            'session_info': {
                'session_id': self.session_id,
                'start_time': self.session_start.isoformat(),
                'duration': str(datetime.now() - self.session_start),
                'total_queries': self.stats.total_queries
            },
            'query_stats': {
                'total_queries': self.stats.total_queries,
                'successful_queries': self.stats.successful_queries,
                'success_rate': f"{success_rate:.1f}%",
                'failed_queries': self.stats.total_queries - self.stats.successful_queries
            },
            'enhanced_latency_metrics': {
                'total_latency': {
                    'average': f"{avg_total_latency:.3f}s",
                    'min': f"{self.stats.min_latency:.3f}s",
                    'max': f"{self.stats.max_latency:.3f}s",
                    'total': f"{self.stats.total_latency:.3f}s"
                },
                'internal_processing_latency': {
                    'average': f"{avg_internal_latency:.3f}s",
                    'total': f"{self.stats.total_internal_processing_latency:.3f}s",
                    'percentage_of_total': f"{(avg_internal_latency / avg_total_latency * 100) if avg_total_latency > 0 else 0:.1f}%"
                },
                'llm_api_latency': {
                    'average': f"{avg_llm_latency:.3f}s",
                    'min': f"{self.stats.min_llm_latency:.3f}s" if self.stats.min_llm_latency != float('inf') else "N/A",
                    'max': f"{self.stats.max_llm_latency:.3f}s",
                    'total': f"{self.stats.total_llm_api_latency:.3f}s",
                    'percentage_of_total': f"{(avg_llm_latency / avg_total_latency * 100) if avg_total_latency > 0 else 0:.1f}%"
                },
                'local_processing_time': {
                    'average': f"{avg_local_processing:.3f}s",
                    'total': f"{self.stats.total_local_processing_time:.3f}s"
                },
                'time_to_first_token': {
                    'average': f"{avg_ttft:.3f}s",
                    'total': f"{self.stats.total_time_to_first_token:.3f}s",
                    'queries_with_data': self.stats.queries_with_ttft
                }
            },
            'enhanced_token_metrics': {
                'total_tokens': {
                    'total': self.stats.total_tokens,
                    'average_per_query': f"{avg_tokens:.1f}"
                },
                'input_tokens': {
                    'total': self.stats.total_input_tokens,
                    'average_per_query': f"{avg_input_tokens:.1f}"
                },
                'output_tokens': {
                    'total': self.stats.total_output_tokens,
                    'average_per_query': f"{avg_output_tokens:.1f}"
                },
                'token_generation_rate': {
                    'average': f"{avg_token_gen_rate:.1f} tokens/sec",
                    'total_generation_time': f"{self.stats.total_token_generation_time:.3f}s"
                }
            },
            'processing_time_breakdown': {
                'neo4j_queries': {
                    'average': f"{avg_neo4j_time:.3f}s",
                    'total': f"{self.stats.total_neo4j_time:.3f}s"
                },
                'geocoding': {
                    'average': f"{avg_geocoding_time:.3f}s",
                    'total': f"{self.stats.total_geocoding_time:.3f}s"
                },
                'spatial_processing': {
                    'average': f"{avg_spatial_time:.3f}s",
                    'total': f"{self.stats.total_spatial_processing_time:.3f}s"
                },
                'memory_processing': {
                    'average': f"{avg_memory_time:.3f}s",
                    'total': f"{self.stats.total_memory_processing_time:.3f}s"
                }
            },
            'feature_usage': {
                'spatial_queries': f"{spatial_percentage:.1f}%",
                'memory_usage': f"{memory_percentage:.1f}%",
                'focused_queries': f"{focused_percentage:.1f}%",
                'geocoding_success': f"{geocoding_percentage:.1f}%",
                'expanded_searches': f"{expanded_percentage:.1f}%",
                'zero_results': f"{zero_results_percentage:.1f}%"
            },
            'top_locations': dict(self.stats.location_requests.most_common(5)),
            'query_categories': dict(self.stats.query_categories.most_common()),
            'error_breakdown': dict(self.stats.error_types.most_common()),
            'hourly_usage': dict(self.stats.hourly_usage)
        }
    
    def format_statistics_report(self) -> str:
        """
        Generate a formatted statistics report with enhanced metrics.
        
        Returns:
            str: Formatted report text with detailed token and latency metrics
        """
        stats = self.get_statistics()
        
        if 'message' in stats:
            return stats['message']
        
        report = []
        report.append("="*60)
        report.append("ENHANCED APPLICATION METRICS REPORT")
        report.append("="*60)
        
        # Session info
        session = stats['session_info']
        report.append(f"Session ID: {session['session_id']}")
        report.append(f"Duration: {session['duration']}")
        report.append(f"Started: {session['start_time']}")
        report.append("")
        
        # Query statistics
        query_stats = stats['query_stats']
        report.append("QUERY STATISTICS")
        report.append("-" * 16)
        report.append(f"Total Queries: {query_stats['total_queries']}")
        report.append(f"Success Rate: {query_stats['success_rate']}")
        report.append(f"Failed Queries: {query_stats['failed_queries']}")
        report.append("")
        
        # Enhanced Latency Metrics
        latency = stats['enhanced_latency_metrics']
        report.append("ENHANCED LATENCY METRICS")
        report.append("-" * 25)
        report.append("Total Latency:")
        report.append(f"  Average: {latency['total_latency']['average']}")
        report.append(f"  Range: {latency['total_latency']['min']} - {latency['total_latency']['max']}")
        report.append(f"  Total: {latency['total_latency']['total']}")
        report.append("")
        report.append("Internal Processing Latency:")
        report.append(f"  Average: {latency['internal_processing_latency']['average']}")
        report.append(f"  Total: {latency['internal_processing_latency']['total']}")
        report.append(f"  % of Total: {latency['internal_processing_latency']['percentage_of_total']}")
        report.append("")
        report.append("LLM API Latency:")
        report.append(f"  Average: {latency['llm_api_latency']['average']}")
        report.append(f"  Range: {latency['llm_api_latency']['min']} - {latency['llm_api_latency']['max']}")
        report.append(f"  Total: {latency['llm_api_latency']['total']}")
        report.append(f"  % of Total: {latency['llm_api_latency']['percentage_of_total']}")
        report.append("")
        report.append("Time to First Token:")
        report.append(f"  Average: {latency['time_to_first_token']['average']}")
        report.append(f"  Total: {latency['time_to_first_token']['total']}")
        report.append(f"  Queries with Data: {latency['time_to_first_token']['queries_with_data']}")
        report.append("")
        report.append("Local Processing Time:")
        report.append(f"  Average: {latency['local_processing_time']['average']}")
        report.append(f"  Total: {latency['local_processing_time']['total']}")
        report.append("")
        
        # Enhanced Token Metrics
        tokens = stats['enhanced_token_metrics']
        report.append("ENHANCED TOKEN METRICS")
        report.append("-" * 22)
        report.append("Total Tokens:")
        report.append(f"  Total: {tokens['total_tokens']['total']:,}")
        report.append(f"  Average per Query: {tokens['total_tokens']['average_per_query']}")
        report.append("")
        report.append("Input Tokens:")
        report.append(f"  Total: {tokens['input_tokens']['total']:,}")
        report.append(f"  Average per Query: {tokens['input_tokens']['average_per_query']}")
        report.append("")
        report.append("Output Tokens:")
        report.append(f"  Total: {tokens['output_tokens']['total']:,}")
        report.append(f"  Average per Query: {tokens['output_tokens']['average_per_query']}")
        report.append("")
        report.append("Token Generation Rate:")
        report.append(f"  Average: {tokens['token_generation_rate']['average']}")
        report.append(f"  Total Generation Time: {tokens['token_generation_rate']['total_generation_time']}")
        report.append("")
        
        # Processing Time Breakdown
        processing = stats['processing_time_breakdown']
        report.append("PROCESSING TIME BREAKDOWN")
        report.append("-" * 27)
        report.append("Neo4j Database Queries:")
        report.append(f"  Average: {processing['neo4j_queries']['average']}")
        report.append(f"  Total: {processing['neo4j_queries']['total']}")
        report.append("")
        report.append("Geocoding Operations:")
        report.append(f"  Average: {processing['geocoding']['average']}")
        report.append(f"  Total: {processing['geocoding']['total']}")
        report.append("")
        report.append("Spatial Processing:")
        report.append(f"  Average: {processing['spatial_processing']['average']}")
        report.append(f"  Total: {processing['spatial_processing']['total']}")
        report.append("")
        report.append("Memory Processing:")
        report.append(f"  Average: {processing['memory_processing']['average']}")
        report.append(f"  Total: {processing['memory_processing']['total']}")
        report.append("")
        
        # Feature usage
        features = stats['feature_usage']
        report.append("FEATURE USAGE")
        report.append("-" * 13)
        report.append(f"Spatial Queries: {features['spatial_queries']}")
        report.append(f"Memory Usage: {features['memory_usage']}")
        report.append(f"Focused Queries: {features['focused_queries']}")
        report.append(f"Geocoding Success: {features['geocoding_success']}")
        report.append(f"Expanded Searches: {features['expanded_searches']}")
        report.append(f"Zero Results: {features['zero_results']}")
        report.append("")
        
        # Top locations
        if stats['top_locations']:
            report.append("TOP LOCATIONS")
            report.append("-" * 13)
            for location, count in stats['top_locations'].items():
                report.append(f"  {location}: {count}")
            report.append("")
        
        # Query categories
        if stats['query_categories']:
            report.append("QUERY CATEGORIES")
            report.append("-" * 16)
            for category, count in stats['query_categories'].items():
                report.append(f"  {category}: {count}")
            report.append("")
        
        # Error breakdown
        if stats['error_breakdown']:
            report.append("ERROR BREAKDOWN")
            report.append("-" * 15)
            for error_type, count in stats['error_breakdown'].items():
                report.append(f"  {error_type}: {count}")
            report.append("")
        
        return "\n".join(report)
    
    def export_raw_data(self) -> Dict[str, Any]:
        """
        Export raw metrics data with enhanced token and latency information.
        
        Returns:
            Dict: Complete raw metrics data including enhanced metrics
        """
        return {
            'session_id': self.session_id,
            'session_start': self.session_start.isoformat(),
            'query_history': [
                {
                    'timestamp': q.timestamp.isoformat(),
                    'query': q.query,
                    'success': q.success,
                    
                    # Enhanced latency metrics
                    'total_latency': q.latency_metrics.total_latency,
                    'internal_processing_latency': q.latency_metrics.internal_processing_latency,
                    'llm_api_latency': q.latency_metrics.llm_api_latency,
                    'local_processing_time': q.latency_metrics.local_processing_time,
                    'time_to_first_token': q.latency_metrics.time_to_first_token,
                    'token_generation_time': q.latency_metrics.token_generation_time,
                    
                    # Enhanced token metrics
                    'input_tokens': q.token_metrics.input_tokens,
                    'output_tokens': q.token_metrics.output_tokens,
                    'total_tokens': q.token_metrics.total_tokens,
                    'token_generation_rate': q.token_metrics.token_generation_rate,
                    'inter_token_arrival_time': q.token_metrics.inter_token_arrival_time,
                    
                    # Processing time breakdowns
                    'neo4j_query_time': q.neo4j_query_time,
                    'geocoding_time': q.geocoding_time,
                    'spatial_processing_time': q.spatial_processing_time,
                    'memory_processing_time': q.memory_processing_time,
                    
                    # Original fields
                    'is_spatial': q.is_spatial,
                    'used_memory': q.used_memory,
                    'is_focused': q.is_focused,
                    'result_count': q.result_count,
                    'geocoding_success': q.geocoding_success,
                    'expanded_search': q.expanded_search,
                    'location_text': q.location_text,
                    'distance_threshold': q.distance_threshold,
                    'error_message': q.error_message
                }
                for q in self.query_history
            ],
            'session_stats': {
                'total_queries': self.stats.total_queries,
                'successful_queries': self.stats.successful_queries,
                
                # Enhanced latency stats
                'total_latency': self.stats.total_latency,
                'min_latency': self.stats.min_latency,
                'max_latency': self.stats.max_latency,
                'total_internal_processing_latency': self.stats.total_internal_processing_latency,
                'total_llm_api_latency': self.stats.total_llm_api_latency,
                'total_local_processing_time': self.stats.total_local_processing_time,
                'min_llm_latency': self.stats.min_llm_latency,
                'max_llm_latency': self.stats.max_llm_latency,
                
                # Enhanced token stats
                'total_tokens': self.stats.total_tokens,
                'total_input_tokens': self.stats.total_input_tokens,
                'total_output_tokens': self.stats.total_output_tokens,
                'total_token_generation_time': self.stats.total_token_generation_time,
                'total_time_to_first_token': self.stats.total_time_to_first_token,
                'queries_with_ttft': self.stats.queries_with_ttft,
                
                # Processing time breakdowns
                'total_neo4j_time': self.stats.total_neo4j_time,
                'total_geocoding_time': self.stats.total_geocoding_time,
                'total_spatial_processing_time': self.stats.total_spatial_processing_time,
                'total_memory_processing_time': self.stats.total_memory_processing_time,
                
                # Original stats
                'spatial_queries': self.stats.spatial_queries,
                'memory_usage_count': self.stats.memory_usage_count,
                'focused_queries': self.stats.focused_queries,
                'geocoding_success_count': self.stats.geocoding_success_count,
                'expanded_searches': self.stats.expanded_searches,
                'zero_result_queries': self.stats.zero_result_queries
            }
        }
    
    def log_statistics_to_file(self):
        """Log enhanced statistics to the log file."""
        report = self.format_statistics_report()
        logging.info(f"ENHANCED METRICS REPORT:\n{report}")
        
        # Also log raw stats for analysis
        stats_data = self.get_statistics()
        logging.info(f"ENHANCED METRICS RAW DATA: {json.dumps(stats_data, indent=2)}")
    
    # Legacy methods for backward compatibility
    def record_token_usage(self, total_tokens: int = 0, input_tokens: int = 0, output_tokens: int = 0):
        """Legacy token usage method for backward compatibility."""
        self.record_enhanced_token_usage(total_tokens, input_tokens, output_tokens)