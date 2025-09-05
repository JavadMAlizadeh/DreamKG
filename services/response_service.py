# Give a strict style to the response

import logging
import re
from langchain.chains import LLMChain
from langchain_groq import ChatGroq
from config import Config
from templates.prompts import PromptTemplateFactory


class ResponseService:
    """
    Handles response generation and formatting with strict formatting enforcement.
    """
    
    def __init__(self):
        """Initialize response service with LLM and prompt templates."""
        # Initialize LLM
        self.llm = ChatGroq(
            model=Config.LLM_MODEL, 
            temperature=Config.LLM_TEMPERATURE
        )
        
        # Initialize prompt templates
        self.focused_qa_prompt = PromptTemplateFactory.create_focused_qa_prompt()
        self.spatial_qa_prompt = PromptTemplateFactory.create_spatial_qa_prompt()
        self.simple_qa_prompt = PromptTemplateFactory.create_simple_qa_prompt()
        
        # Initialize LLM chains
        self.focused_qa_chain = LLMChain(llm=self.llm, prompt=self.focused_qa_prompt)
        self.spatial_qa_chain = LLMChain(llm=self.llm, prompt=self.spatial_qa_prompt)
        self.simple_qa_chain = LLMChain(llm=self.llm, prompt=self.simple_qa_prompt)
        
        logging.info("ResponseService initialized with strict formatting enforcement")
    
    def generate_response(self, query, results, is_spatial=False, is_focused=False):
        """
        Generate response using appropriate QA chain with strict formatting.
        
        Args:
            query (str): Original user query
            results (list): Database query results
            is_spatial (bool): Whether this was a spatial query
            is_focused (bool): Whether this requires focused response
            
        Returns:
            dict: Response generation result with enforced formatting
        """
        try:
            if not results:
                return {
                    'success': True,
                    'response': "No results found for your query.",
                    'chain_used': 'none'
                }
            
            # Generate initial response using appropriate chain
            if is_focused:
                qa_response = self.focused_qa_chain.invoke({
                    "context": results,
                    "question": query
                })
                chain_used = "focused"
                logging.info("Used focused QA chain")
                
            elif is_spatial:
                qa_response = self.spatial_qa_chain.invoke({
                    "context": results,
                    "question": query
                })
                chain_used = "spatial"
                logging.info("Used spatial QA chain")
                
            else:
                qa_response = self.simple_qa_chain.invoke({
                    "context": results,
                    "question": query
                })
                chain_used = "simple"
                logging.info("Used simple QA chain")
            
            response_text = qa_response.get('text', 'Sorry, an answer could not be generated.')
            
            # Apply strict formatting enforcement - return structured data for better display
            if is_focused:
                formatted_response = response_text  # Keep focused responses as-is
            else:
                formatted_response = self._create_structured_response(response_text, results, is_spatial)
            
            logging.info(f"Response generated and formatted using {chain_used} chain")
            
            return {
                'success': True,
                'response': formatted_response,
                'chain_used': chain_used
            }
            
        except Exception as e:
            logging.error(f"Response generation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'response': "Sorry, there was an error generating the response.",
                'chain_used': 'error'
            }
    
    def _create_structured_response(self, response_text, results, is_spatial):
        """
        Create a structured response that bypasses Streamlit markdown issues.
        
        Args:
            response_text (str): Original LLM response
            results (list): Database query results
            is_spatial (bool): Whether query was spatial
            
        Returns:
            dict: Structured response data
        """
        try:
            # Extract intro text
            intro_match = re.match(r'^(.*?)(?=(?:\d+\.|\*|•|-)|\Z)', response_text, re.DOTALL)
            intro_text = intro_match.group(1).strip() if intro_match else ""
            intro_text = self._clean_intro_text(intro_text, len(results), is_spatial)
            
            # Create organizations data
            organizations = []
            for i, result in enumerate(results, 1):
                org_data = self._extract_organization_data(result)
                organizations.append(self._format_organization_for_display(org_data, i, is_spatial))
            
            return {
                'type': 'structured',
                'intro': intro_text,
                'organizations': organizations
            }
            
        except Exception as e:
            logging.error(f"Structured response creation failed: {str(e)}")
            # Fallback to simple text
            return response_text
    
    def _format_organization_for_display(self, org_data, number, is_spatial):
        """Format organization for structured display."""
        org = {
            'number': number,
            'name': org_data['name'],
            'main_items': [],
            'hours': {},
            'services': {'free': [], 'paid': []}
        }
        
        # Add main details
        if is_spatial and org_data.get('distance'):
            org['main_items'].append(f"Distance: {org_data['distance']} miles away")
        
        if org_data.get('phone'):
            org['main_items'].append(f"Phone: {org_data['phone']}")
        
        if org_data.get('status'):
            org['main_items'].append(f"Status: {org_data['status']}")
        
        if org_data.get('category'):
            org['main_items'].append(f"Category: {org_data['category']}")
        
        if org_data.get('address'):
            org['main_items'].append(f"Address: {org_data['address']}")
        
        # Add hours
        hours_data = org_data.get('hours', {})
        if hours_data:
            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            for day in day_order:
                if day in hours_data:
                    org['hours'][day] = hours_data[day]
        
        # Add services
        services = org_data.get('services', [])
        for service in services:
            if isinstance(service, dict):
                service_name = service.get('service', 'Unknown Service')
                service_type = service.get('type', 'Free')
            else:
                service_name = str(service)
                service_type = 'Free'
            
            if service_type.lower() == 'paid':
                org['services']['paid'].append(service_name)
            else:
                org['services']['free'].append(service_name)
        
        # Sort services
        org['services']['free'].sort()
        org['services']['paid'].sort()
        
        return org
    
    def _extract_organization_data(self, result):
        """Extract and normalize organization data from database result."""
        try:
            # Handle different result formats
            name = (result.get('o.name') or 
                   result.get('name') or 
                   result.get('organizationName') or 
                   'Unknown Organization')
            
            phone = (result.get('o.phone') or 
                    result.get('phone') or 
                    result.get('phoneNumber') or 
                    None)
            
            status = (result.get('o.status') or 
                     result.get('status') or 
                     None)
            
            category = (result.get('o.category') or 
                       result.get('category') or 
                       None)
            
            # Build address
            address_parts = []
            street = (result.get('l.street') or result.get('street') or result.get('streetAddress'))
            city = (result.get('l.city') or result.get('city') or 'Philadelphia')
            state = (result.get('l.state') or result.get('state') or 'PA')
            zipcode = (result.get('l.zipcode') or result.get('zipcode') or result.get('zipCode'))
            
            if street:
                address_parts.append(street)
            if city:
                address_parts.append(city)
            if state:
                address_parts.append(state)
            if zipcode:
                address_parts.append(zipcode)
            
            address = ", ".join(address_parts) if address_parts else None
            
            # Extract distance
            distance = result.get('distance_miles')
            if distance is not None:
                distance = f"{distance:.1f}"
            
            # Extract hours
            hours = {}
            days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            for day in days:
                day_hours = (result.get(f't.{day}') or 
                           result.get(day) or 
                           result.get(day.capitalize()))
                if day_hours:
                    hours[day.capitalize()] = day_hours
            
            # Extract services
            services = []
            if 'services' in result and isinstance(result['services'], list):
                services = result['services']
            elif 'services' in result and isinstance(result['services'], dict):
                # Handle single service as dict
                services = [result['services']]
            
            return {
                'name': name,
                'phone': phone,
                'status': status,
                'category': category,
                'address': address,
                'distance': distance,
                'hours': hours,
                'services': services
            }
            
        except Exception as e:
            logging.error(f"Error extracting organization data: {str(e)}")
            return {'name': 'Unknown Organization'}
    
    def _clean_intro_text(self, intro_text, result_count, is_spatial):
        """Clean and standardize introductory text."""
        # Remove common LLM artifacts
        intro_text = re.sub(r'^(here are|here is|i found|found)\s+', '', intro_text, flags=re.IGNORECASE)
        intro_text = re.sub(r'\s+(here are the details|details|information)[:.]?\s*$', '', intro_text, flags=re.IGNORECASE)
        
        # Ensure it ends with a colon if it describes what follows
        if intro_text and not intro_text.endswith((':',)):
            intro_text += ":"
        
        return intro_text.strip()
    
    def generate_focused_response(self, query, results):
        """Generate focused response for specific follow-up questions."""
        return self.generate_response(query, results, is_spatial=False, is_focused=True)
    
    def generate_spatial_response(self, query, results):
        """Generate spatial response including distance information."""
        return self.generate_response(query, results, is_spatial=True, is_focused=False)
    
    def generate_simple_response(self, query, results):
        """Generate simple response with full organization details."""
        return self.generate_response(query, results, is_spatial=False, is_focused=False)
    
    def format_error_response(self, error_type, error_message, suggestions=None):
        """Format error responses with helpful information."""
        if error_type == 'geocoding':
            response = f"I couldn't find the location you mentioned. {error_message}"
            if not suggestions:
                suggestions = [
                    "Try being more specific (e.g., 'near City Hall' instead of 'downtown')",
                    "Use a street address or zip code",
                    "Check for typos in the location name"
                ]
        elif error_type == 'no_results':
            response = f"No organizations found matching your criteria."
            if not suggestions:
                suggestions = [
                    "Try expanding your search area",
                    "Check different days of the week",
                    "Look for similar services"
                ]
        elif error_type == 'query':
            response = f"There was an issue processing your request."
            if not suggestions:
                suggestions = [
                    "Try rephrasing your question",
                    "Be more specific about what you're looking for"
                ]
        else:
            response = f"An unexpected error occurred: {error_message}"
            suggestions = suggestions or ["Please try again later"]
        
        if suggestions:
            response += "\n\nSuggestions:"
            for suggestion in suggestions:
                response += f"\n● {suggestion}"
        
        return {
            'success': True,
            'response': response,
            'chain_used': 'error_formatter',
            'error_type': error_type
        }
    
    def generate_help_response(self):
        """Generate help response explaining system capabilities."""
        help_text = """
I can help you find information about organizations in Philadelphia! Here's what I can do:

**Spatial Queries:**
● "Libraries near City Hall"
● "Social security offices within 2 miles of Temple University"
● "Organizations in South Philly"

**Service Queries:**
● "Where can I find free Wi-Fi?"
● "Organizations with printing services"
● "Places open on Sunday"

**Follow-up Questions:**
After I find organizations, you can ask:
● "What are their hours on Monday?"
● "Do they have Wi-Fi?"
● "What are their paid services?"

**Time-based Queries:**
● "Libraries open after 7 PM"
● "Organizations open on weekends"

**Examples:**
● "Libraries near City Hall" → "What are their hours?"
● "Social security offices in North Philly" → "Which ones are open on Saturday?"
● "Organizations with free computers" → "Do they have printing?"

Just ask naturally - I'll understand what you're looking for!
"""
        
        return {
            'success': True,
            'response': help_text.strip(),
            'chain_used': 'help'
        }
    
    def generate_suggestion_response(self, result_count, is_spatial=False, used_memory=False, 
                                   expanded_radius=False, original_threshold=None, 
                                   expanded_threshold=None):
        """Generate helpful suggestions based on query results."""
        suggestions = []
        
        if used_memory:
            suggestions.append("💭 Memory: This answer is based on your previous query. Ask a new question to search again.")
        
        elif is_spatial:
            if expanded_radius and original_threshold and expanded_threshold:
                suggestions.append(f"🔍 No organizations found within {original_threshold} miles. Expanded search to {expanded_threshold} miles...")
            
            if result_count > 3:
                suggestions.append(f"💡 Tip: Found {result_count} organizations. Try asking focused follow-up questions like 'What are their paid services?' or 'Do they have Wi-Fi?'")
            elif result_count == 0:
                threshold = expanded_threshold or original_threshold or "the specified distance"
                suggestions.append(f"💡 Tip: No organizations found within {threshold} miles. Try expanding your search radius or check a different area.")
        
        else:
            if result_count > 1:
                suggestions.append(f"💡 Tip: Found {result_count} organizations. Ask focused follow-up questions like 'What are their paid services?' or 'What are their hours on Monday?'")
        
        return "\n".join(suggestions) if suggestions else ""
    
    def validate_results(self, results):
        """Validate query results for response generation."""
        if results is None:
            return {
                'valid': False,
                'message': "Results are None"
            }
        
        if not isinstance(results, list):
            return {
                'valid': False,
                'message': "Results must be a list"
            }
        
        if len(results) == 0:
            return {
                'valid': True,
                'message': "No results found"
            }
        
        # Check if results have expected structure
        sample_result = results[0]
        if not isinstance(sample_result, dict):
            return {
                'valid': False,
                'message': "Results must contain dictionaries"
            }
        
        return {
            'valid': True,
            'message': f"Valid results with {len(results)} items"
        }