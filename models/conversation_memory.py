

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
    
    def is_simple_followup(self, query):
        """
        Check if this is a simple follow-up that can use cached results.
        
        Args:
            query (str): Query to check
            
        Returns:
            bool: True if simple follow-up
        """
        query_lower = query.lower()
        
        simple_followup_patterns = [
            r'^(?:what are their|what about their|do they have|can I|tell me about their)',
            r'^(?:which ones|any of them|how many)',
            r'hours\?',
            r'services\?',
            r'address\?',
            r'phone\?',
            r'location\?'
        ]
        
        return any(re.search(pattern, query_lower) for pattern in simple_followup_patterns)
    
    def is_focused_followup(self, query):
        """
        Check if this is a focused follow-up that should get a specific answer.
        
        Args:
            query (str): Query to check
            
        Returns:
            bool: True if focused follow-up
        """
        query_lower = query.lower()
        
        focused_patterns = [
            # ------------------------------------------------------------
            # 0) Generic "tell me about X (one org)" patterns
            # ------------------------------------------------------------
            r'^\s*(?:tell me about|details for|info for|information for)\b',

            # ------------------------------------------------------------
            # 1) OPEN/CLOSED STATUS (now/today/tomorrow/this morning/etc.)
            # ------------------------------------------------------------
            r'^\s*(?:is|are)\s+(?:it|they|this|that)\s+(?:open|closed)\b',
            r'\b(?:open|closed)\s+(?:now|right now|today|tonight|tomorrow)\b',
            r'\b(?:open|closed)\s+(?:this\s+)?(?:morning|afternoon|evening|night)\b',
            r'\b(?:are|is)\s+(?:it|they)\s+open\s+(?:on|this)\s+'
            r'(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:rs(?:day)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b',
            r'\b(?:are|is)\s+(?:it|they)\s+open\s+(?:this\s+)?weekend\b',
            r'\b(?:are|is)\s+(?:it|they)\s+open\s+(?:this\s+)?weekday\b',
            r'\b(?:which|any|are|is|do|does)\s+(?:one|ones|any\s+of\s+them|they|it)?\s*(?:open|closed)\s*(?:now|today|tonight|tomorrow|this\s+(?:morning|afternoon|evening|week|weekend)|on\s+(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:rs(?:day)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?))?\b',

            # ------------------------------------------------------------
            # 2) HOURS (very common follow-ups)
            # ------------------------------------------------------------
            r'\bhours?\b',
            r'\bwhat\s+time\s+(?:do|does)\s+(?:it|they)\s+(?:open|close)\b',
            r'\bwhen\s+(?:do|does)\s+(?:it|they)\s+(?:open|close)\b',
            r'\b(?:opening|closing)\s+time\b',
            r'\buntil\s+what\s+time\b',
            r'\bwhat\s+time\s+are\s+(?:you|they)\s+open\b',
            r'\bwhat\s+are\s+(?:their|the)\s+hours\s+(?:today|tomorrow)\b',
            r'\b(?:today|tomorrow)\s+hours\b',
            r'\bhours?\s+on\s+'
            r'(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:rs(?:day)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b',
            r'\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*:\s*\d',  # users paste like "Wednesday: ?"

            # ------------------------------------------------------------
            # 3) PHONE / CONTACT
            # ------------------------------------------------------------
            r'\bphone\b',
            r'\bphone\s+number\b',
            r'\bcontact\b',
            r'\bcall\b',
            r'\bemail\b',
            r'\bwebsite\b',
            r'\bhow\s+do\s+i\s+reach\b',
            r'\bwhat\s+is\s+(?:their|the)\s+(?:phone|number)\b',

            # ------------------------------------------------------------
            # 4) ADDRESS / LOCATION / DIRECTIONS / TRANSIT
            # ------------------------------------------------------------
            r'\baddress\b',
            r'\blocation\b',
            r'\bwhere\s+(?:is|are)\b',
            r'\bhow\s+do\s+i\s+get\s+there\b',
            r'\bdirections\b',
            r'\bnearby\b',
            r'\bclosest\b',
            r'\bhow\s+far\b',
            r'\bdistance\b',
            r'\b(bus|subway|train|trolley|septa|route)\b',
            r'\bparking\b',

            # ------------------------------------------------------------
            # 5) SERVICES AVAILABILITY (do they have X?)
            #    Works for library + homeless services + social services
            # ------------------------------------------------------------
            r'^\s*(?:do|does)\s+(?:it|they|this|that)\s+(?:have|offer|provide)\b',
            r'\bcan\s+i\s+(?:get|use|access)\b',
            r'\bis\s+(?:there|it)\s+(?:free|available)\b',
            r'\bdo\s+they\s+help\s+with\b',
            r'\bwhat\s+(?:services|resources)\s+(?:do\s+they|are\s+available)\b',

            # Specific high-frequency services/needs (broad coverage)
            r'\b(?:wi-?fi|internet|computers?|printing|copying|scanning)\b',
            r'\b(?:shelter|bed|housing|overnight|sleep)\b',
            r'\b(?:food|meals?|pantry|breakfast|lunch|dinner)\b',
            r'\b(?:showers?|hygiene|restroom|bathroom|toilet)\b',
            r'\b(?:laundry|clothes|clothing)\b',
            r'\b(?:case\s*management|social\s*worker|benefits|snap|medicaid|medicare|ssi|disability)\b',
            r'\b(?:mental\s*health|counseling|therapy|psychiatric)\b',
            r'\b(?:substance|addiction|recovery|detox|sober)\b',
            r'\b(?:legal|lawyer|id|identification|birth\s*certificate)\b',
            r'\b(?:job|employment|resume|workforce)\b',

            # ------------------------------------------------------------
            # 6) COST / FREE / PRICING
            # ------------------------------------------------------------
            r'\bhow\s+much\b',
            r'\bprice\b',
            r'\bcost\b',
            r'\bfee\b',
            r'\bfees\b',
            r'\bfree\b',
            r'\bpaid\b',

            # ------------------------------------------------------------
            # 7) ELIGIBILITY / REQUIREMENTS / DOCUMENTS
            # ------------------------------------------------------------
            r'\b(?:eligible|eligibility|qualify|qualification)\b',
            r'\bdo\s+i\s+need\b',
            r'\brequirements?\b',
            r'\bid\b',
            r'\bappointment\b',
            r'\bwalk[-\s]*in\b',
            r'\breferral\b',
            r'\bintake\b',
            r'\bapply\b',
            r'\bregistration\b',

            # ------------------------------------------------------------
            # 8) SAFETY-NET FOLLOW-UPS: "Which one" / "the first one" / "top result"
            #    These should still be treated as focused to avoid re-listing.
            # ------------------------------------------------------------
            r'\b(?:the\s+first\s+one|top\s+one|top\s+result|first\s+result)\b',
            r'\b(?:#|number)\s*1\b',
            r'\b(?:that\s+one|this\s+one)\b',

            # ------------------------------------------------------------
            # 9) OPTIONAL: If user explicitly mentions a known org name later
            #    (Handled better outside regex, but this helps.)
            # ------------------------------------------------------------
            r'\b(?:library|shelter|clinic|center|office|pantry)\b.*\b(?:open|hours|phone|address|services)\b',
        ]
        
        return any(re.search(pattern, query_lower) for pattern in focused_patterns)
    
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