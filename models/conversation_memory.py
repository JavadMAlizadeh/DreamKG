

import re
import logging
from datetime import datetime
from config import Config


class ConversationMemory:
    """
    Manages conversational memory and context for follow-up queries.
    Handles pronoun substitution, query continuity detection, and result caching.
    """
    
    def __init__(self, max_history=None):
        """
        Initialize conversation memory.
        
        Args:
            max_history (int): Maximum number of interactions to store
        """
        self.max_history = max_history or Config.MAX_CONVERSATION_HISTORY
        self.conversation_history = []  # List of interaction dictionaries
        self.current_context = None     # Current Neo4j results for reuse
        self.last_query = None         # Previous query for reference detection
        self.last_organizations = []   # Organization names from last result
        self.last_spatial_info = None  # Last spatial context
        
        logging.info(f"ConversationMemory initialized with max_history={self.max_history}")
        
    def add_interaction(self, query, results, spatial_info=None):
        """
        Add a new interaction to memory.
        
        Args:
            query (str): User query
            results (list): Neo4j query results
            spatial_info (dict): Spatial context information
        """
        # Extract organization names from results
        organization_names = []
        if results:
            for result in results:
                if not isinstance(result, dict):
                    continue

                org_name = (
                    result.get('o.name') or
                    result.get('name') or
                    result.get('organizationName')
                )

                if org_name:
                    organization_names.append(org_name)

        
        # Store interaction
        interaction = {
            'query': query,
            'results': results,
            'organization_names': organization_names,
            'spatial_info': spatial_info,
            'timestamp': datetime.now()
        }
        
        self.conversation_history.append(interaction)
        self.current_context = results
        self.last_query = query
        self.last_organizations = organization_names
        self.last_spatial_info = spatial_info
        
        # Maintain history size
        if len(self.conversation_history) > self.max_history:
            self.conversation_history.pop(0)
        
        logging.info(f"Memory updated: {len(organization_names)} organizations stored from query: '{query[:50]}...'")
    
    def should_use_memory(self, new_query):
        """
        Determine if the new query should use memory from previous interaction.
        
        Args:
            new_query (str): New user query to analyze
            
        Returns:
            bool: True if query should use memory, False otherwise
        """
        if not self.current_context or not self.last_query:
            logging.info("Memory decision: No previous context available")
            return False
        
        new_query_lower = new_query.lower()
        
        # Check for explicit pronoun references
        pronoun_patterns = [
            r'\bthey\b', r'\bthem\b', r'\btheir\b', r'\bthose\b',
            r'\bit\b', r'\bthat\s+(?:organization|place)\b', r'\bthis\s+(?:organization|place)\b'
        ]
        
        has_pronouns = any(re.search(pattern, new_query_lower) for pattern in pronoun_patterns)
        if has_pronouns:
            logging.info(f"Memory decision: Pronouns detected in query: {new_query}")
            return True
        
        # Check for follow-up question patterns
        followup_patterns = [
            r'^(?:what about|how about|do they|are they|can I|is there)',
            r'^(?:which ones|any of them|what are their)',
            r'^(?:show me their|tell me about their)',
            r'hours\?$', r'services\?$', r'address\?$', r'phone\?$'
        ]
        
        is_followup = any(re.search(pattern, new_query_lower) for pattern in followup_patterns)
        if is_followup:
            logging.info(f"Memory decision: Follow-up pattern detected: {new_query}")
            return True
        
        # Check if asking about specific details without location context
        detail_only_patterns = [
            r'^(?:what services|what are the hours|when are they open)',
            r'^(?:do any have|does anyone have|which have)',
            r'^(?:phone number|address|location) for'
        ]
        
        is_detail_query = any(re.search(pattern, new_query_lower) for pattern in detail_only_patterns)
        if is_detail_query and not self._has_new_location_context(new_query):
            logging.info(f"Memory decision: Detail-only query without new location: {new_query}")
            return True
        
        # Check for topic continuity (same service/topic, no new location)
        if self._has_topic_continuity(new_query) and not self._has_new_location_context(new_query):
            logging.info(f"Memory decision: Topic continuity detected: {new_query}")
            return True
        
        logging.info(f"Memory decision: New independent query: {new_query}")
        return False
    
    def _has_new_location_context(self, query):
        """
        Check if query introduces a new location context.
        
        Args:
            query (str): Query to check for location context
            
        Returns:
            bool: True if new location context detected
        """
        # Import spatial intelligence to reuse location detection
        # Note: This creates a circular import issue, so we'll use basic detection
        location_patterns = [
            r'\bnear\s+\w+', r'\bclose\s+to\s+\w+', r'\bin\s+\w+',
            r'\bat\s+\w+', r'\baround\s+\w+', r'\bwithin\s+\d+'
        ]
        return any(re.search(pattern, query.lower()) for pattern in location_patterns)
    
    def _has_topic_continuity(self, new_query):
        """
        Check if new query continues the same topic as previous query.
        
        Args:
            new_query (str): New query to check for topic continuity
            
        Returns:
            bool: True if topics overlap
        """
        if not self.last_query:
            return False
        
        # Extract key topics from both queries
        current_topics = self._extract_topics(self.last_query)
        new_topics = self._extract_topics(new_query)
        
        # Check for overlap
        return bool(current_topics.intersection(new_topics))
    
    def _extract_topics(self, query):
        """
        Extract key topics/services from a query.
        
        Args:
            query (str): Query to extract topics from
            
        Returns:
            set: Set of topic keywords found in query
        """
        query_lower = query.lower()
        topics = set()
        
        # Service-related topics
        service_keywords = [
            'printing', 'computers', 'wifi', 'internet', 'copying',
            'books', 'study', 'meeting', 'programs', 'classes',
            'hours', 'open', 'closed', 'schedule', 'time'
        ]
        
        for keyword in service_keywords:
            if keyword in query_lower:
                topics.add(keyword)
        
        return topics
    
    def get_memory_context(self):
        """
        Get formatted memory context for use in prompts.
        
        Returns:
            str: Formatted memory context string
        """
        if not self.current_context or not self.last_organizations:
            return ""
        
        context = f"\nMEMORY CONTEXT:\n"
        context += f"Previous Query: {self.last_query}\n"
        context += f"Organizations from Previous Results: {', '.join(self.last_organizations)}\n"
        
        if self.last_spatial_info:
            context += f"Previous Spatial Context: User was asking about location near {self.last_spatial_info.get('location_text', 'unknown')}\n"
        
        context += f"Available Previous Results: {len(self.current_context)} organizations with full details\n"
        
        return context
    
    def substitute_pronouns(self, query):
        """
        Replace pronouns with actual organization names from memory.
        
        Args:
            query (str): Query with potential pronouns
            
        Returns:
            str: Query with pronouns substituted
        """
        if not self.last_organizations:
            return query
        
        substituted_query = query
        organization_list = ", ".join(self.last_organizations)
        
        # Pronoun substitution patterns
        substitutions = [
            (r'\bthey\b', organization_list),
            (r'\bthem\b', organization_list),
            (r'\bthose\s+(?:libraries|places|organizations)\b', organization_list),
            (r'\bthose\b', organization_list)
        ]
        
        for pattern, replacement in substitutions:
            substituted_query = re.sub(pattern, replacement, substituted_query, flags=re.IGNORECASE)
        
        if substituted_query != query:
            logging.info(f"Pronoun substitution: '{query}' -> '{substituted_query}'")
        
        return substituted_query
    
    def clear_memory(self):
        """Clear all memory."""
        self.conversation_history = []
        self.current_context = None
        self.last_query = None
        self.last_organizations = []
        self.last_spatial_info = None
        logging.info("Memory cleared")
    
    def get_interaction_count(self):
        """
        Get the number of stored interactions.
        
        Returns:
            int: Number of interactions in memory
        """
        return len(self.conversation_history)
    
    def get_last_result_count(self):
        """
        Get the number of results from the last query.
        
        Returns:
            int: Number of results from last query, 0 if no results
        """
        return len(self.current_context) if self.current_context else 0