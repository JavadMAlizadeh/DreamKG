"""
Enhanced Response Service with optimized two-tier data structure.
This version prepares data specifically for collapsible display.
"""

import logging
import re
from langchain_groq import ChatGroq
from config import Config
from templates.prompts import PromptTemplateFactory


class ResponseService:
    """
    Enhanced response service that structures data for two-tier display.
    """
    
    def __init__(self):
        """Initialize response service with LLM and prompt templates."""
        self.llm = ChatGroq(
            model=Config.LLM_MODEL, 
            temperature=Config.LLM_TEMPERATURE
        )
        
        # Initialize prompt templates
        self.focused_qa_prompt = PromptTemplateFactory.create_focused_qa_prompt()
        self.spatial_qa_prompt = PromptTemplateFactory.create_spatial_qa_prompt()
        self.simple_qa_prompt = PromptTemplateFactory.create_simple_qa_prompt()
        
        # Initialize LLM chains
        self.focused_qa_chain = self.focused_qa_prompt | self.llm
        self.spatial_qa_chain = self.spatial_qa_prompt | self.llm
        self.simple_qa_chain = self.simple_qa_prompt | self.llm
        
        logging.info("ResponseService initialized with two-tier display support")
    
    def generate_response(self, query, results, is_spatial=False, is_focused=False):
        """
        Generate response with enhanced two-tier structure.
        
        Args:
            query (str): Original user query
            results (list): Database query results
            is_spatial (bool): Whether this was a spatial query
            is_focused (bool): Whether this requires focused response
            
        Returns:
            dict: Response with two-tier structure
        """
        try:
            if not results:
                return {
                    'success': True,
                    'response': "No results found for your query.",
                    'chain_used': 'none'
                }
            
            # Generate response using appropriate chain
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
            
            response_text = qa_response.content if hasattr(qa_response, 'content') else str(qa_response)
            
            # Create enhanced two-tier structured response
            if is_focused:
                formatted_response = response_text
            else:
                formatted_response = self._create_two_tier_response(
                    response_text, results, is_spatial, query  # PASS query
                )
            
            logging.info(f"Enhanced two-tier response generated using {chain_used} chain")
            
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
    
    def _create_two_tier_response(self, response_text, results, is_spatial, user_query=""):
        """Create a structured response compatible with the display function."""
        try:
            # Extract intro text
            intro_match = re.match(r'^(.*?)(?=(?:\d+\.|\*|●|-)|\Z)', response_text, re.DOTALL)
            intro_text = intro_match.group(1).strip() if intro_match else ""
            intro_text = self._clean_intro_text(intro_text, len(results), is_spatial)
            
            # Create organizations data
            organizations = []
            for i, result in enumerate(results, 1):
                org_data = self._extract_organization_data(result)
                organizations.append(self._format_organization_for_display(org_data, i, is_spatial, user_query))  # PASS user_query
            
            return {
                'type': 'structured',
                'intro': intro_text,
                'organizations': organizations
            }
            
        except Exception as e:
            logging.error(f"Two-tier response creation failed: {str(e)}")
            return response_text

    def _format_organization_for_display(self, org_data, number, is_spatial, user_query=""):
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
        
        if org_data.get('address'):
            org['main_items'].append(f"Address: {org_data['address']}")
        
        # Services - Show only requested services (first 3 as inline list)
        services = org_data.get('services', [])
        free_services = []
        for service in services:
            if isinstance(service, dict):
                if service.get('type', 'Free').lower() != 'paid':
                    free_services.append(service.get('service', 'Unknown'))
            else:
                free_services.append(str(service))
        
        if free_services:
            preview_services = sorted(free_services)[:3]
            services_text = ", ".join(preview_services)
            org['main_items'].append(f"Services: {services_text}")
        
        # REMOVED: Time-specific logic from short view
        # Hours will ONLY appear in the expandable full details section
        
        # Add ALL hours to the full details section (this is separate from main_items)
        hours_data = org_data.get('hours', {})
        if hours_data:
            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            for day in day_order:
                if day in hours_data:
                    org['hours'][day] = hours_data[day]
        
        # Add services to full details
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
    
    def _format_organization_two_tier(self, org_data, number, is_spatial):
        """
        Format organization with explicit short/long view separation.
        
        Args:
            org_data (dict): Extracted organization data
            number (int): Organization number in list
            is_spatial (bool): Whether this is a spatial query
            
        Returns:
            dict: Organization data with short_view and long_view
        """
        # ===== SHORT VIEW DATA =====
        short_view = {
            'number': number,
            'name': org_data['name'],
            'distance': org_data.get('distance'),  # Will be None for non-spatial
            'status': org_data.get('status'),
            'category': org_data.get('category'),
            'key_services': []  # Top 3 services for preview
        }
        
        # Get top services for preview
        services = org_data.get('services', [])
        free_services = []
        for service in services:
            if isinstance(service, dict):
                if service.get('type', 'Free').lower() != 'paid':
                    free_services.append(service.get('service', 'Unknown'))
            else:
                free_services.append(str(service))
        
        short_view['key_services'] = sorted(free_services)[:3]
        short_view['total_services_count'] = len(free_services)
        
        # ===== LONG VIEW DATA (Full Details) =====
        long_view = {
            'phone': org_data.get('phone'),
            'address': org_data.get('address'),
            'hours': org_data.get('hours', {}),
            'all_services': {
                'free': [],
                'paid': []
            }
        }
        
        # Organize all services by type
        for service in services:
            if isinstance(service, dict):
                service_name = service.get('service', 'Unknown Service')
                service_type = service.get('type', 'Free')
            else:
                service_name = str(service)
                service_type = 'Free'
            
            if service_type.lower() == 'paid':
                long_view['all_services']['paid'].append(service_name)
            else:
                long_view['all_services']['free'].append(service_name)
        
        # Sort services alphabetically
        long_view['all_services']['free'].sort()
        long_view['all_services']['paid'].sort()
        
        return {
            'short_view': short_view,
            'long_view': long_view
        }
    
    def _extract_organization_data(self, result):
        """
        Extract and normalize organization data from database result.
        (Same as before - no changes needed)
        """
        try:
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

            # DEBUG: Log all keys in the result
            logging.info(f"Result keys for {name}: {list(result.keys())}")

            for day in days:
                day_hours = (result.get(f't.{day}') or 
                        result.get(day) or 
                        result.get(day.capitalize()))
                if day_hours:
                    hours[day.capitalize()] = day_hours
                    logging.info(f"Found hours for {day.capitalize()}: {day_hours}")
            
            # Extract services
            services = []
            if 'services' in result and isinstance(result['services'], list):
                services = result['services']
            elif 'services' in result and isinstance(result['services'], dict):
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
        intro_text = re.sub(r'^(here are|here is|i found|found)\s+', '', intro_text, flags=re.IGNORECASE)
        intro_text = re.sub(r'\s+(here are the details|details|information)[:.]?\s*$', '', intro_text, flags=re.IGNORECASE)
        
        if intro_text and not intro_text.endswith((':',)):
            intro_text += ":"
        
        return intro_text.strip()
    
    # Keep all other methods from original ResponseService...
    def generate_focused_response(self, query, results):
        """Generate focused response for specific follow-up questions."""
        return self.generate_response(query, results, is_spatial=False, is_focused=True)
    
    def generate_spatial_response(self, query, results):
        """Generate spatial response including distance information."""
        return self.generate_response(query, results, is_spatial=True, is_focused=False)
    
    def generate_simple_response(self, query, results):
        """Generate simple response with full organization details."""
        return self.generate_response(query, results, is_spatial=False, is_focused=False)


    # ===== ENHANCED DISPLAY FUNCTION FOR TWO-TIER =====
    def display_two_tier_response(response_data):
        """
        Display response using the enhanced two-tier structure.
        
        Args:
            response_data: Response dict with short_view/long_view structure
        """
        import streamlit as st
        
        # Handle string responses
        if isinstance(response_data, str):
            st.markdown(response_data)
            return
        
        # Check if this is a two-tier response
        if isinstance(response_data, dict):
            if response_data.get('display_mode') == 'two_tier':
                # Display intro
                if response_data.get('intro'):
                    st.markdown(response_data['intro'])
                    st.write("")
                
                # Display each organization with two-tier view
                for org in response_data.get('organizations', []):
                    short = org.get('short_view', {})
                    long = org.get('long_view', {})
                    
                    # SHORT VIEW
                    st.markdown(f"**{short['number']}. {short['name']}**")
                    
                    # Build short info line
                    info_parts = []
                    if short.get('distance'):
                        info_parts.append(f"📍 {short['distance']} miles")
                    if short.get('status'):
                        emoji = "✅" if short['status'].lower() == "open" else "❌"
                        info_parts.append(f"{emoji} {short['status']}")
                    if short.get('category'):
                        info_parts.append(f"🏢 {short['category']}")
                    
                    if info_parts:
                        st.markdown(" • ".join(info_parts))
                    
                    # Key services preview
                    if short.get('key_services'):
                        services_text = ", ".join(short['key_services'])
                        extra_count = short.get('total_services_count', 0) - len(short['key_services'])
                        if extra_count > 0:
                            services_text += f" (+{extra_count} more)"
                        st.markdown(f"🎯 {services_text}")
                    
                    # EXPANDABLE LONG VIEW
                    with st.expander("➕ Show full details", expanded=False):
                        if long.get('phone'):
                            st.markdown(f"**📞 Phone:** {long['phone']}")
                        if long.get('address'):
                            st.markdown(f"**📍 Address:** {long['address']}")
                        
                        # Hours
                        if long.get('hours'):
                            st.markdown("**🕐 Hours:**")
                            for day, time in long['hours'].items():
                                if time.lower() == 'closed':
                                    st.markdown(f"  • {day}: *Closed*")
                                else:
                                    st.markdown(f"  • {day}: {time}")
                        
                        # All services
                        all_services = long.get('all_services', {})
                        if all_services.get('free') or all_services.get('paid'):
                            st.markdown("**🎯 All Services:**")
                            
                            if all_services.get('free'):
                                st.markdown("  *Free Services:*")
                                for service in all_services['free']:
                                    st.markdown(f"    • {service}")
                            
                            if all_services.get('paid'):
                                st.markdown("  *Paid Services:*")
                                for service in all_services['paid']:
                                    st.markdown(f"    • {service}")
                    
                    st.write("")
            
            elif response_data.get('type') == 'structured':
                # Fallback to original structured display
                st.markdown("Using fallback display...")
                st.write(response_data)
            else:
                # Unknown format
                st.markdown(str(response_data))
        else:
            st.markdown(str(response_data))

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
    
    