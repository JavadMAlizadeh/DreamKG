import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq

# Assuming these custom classes are in paths accessible to your project
from time_alternatives import TimeMatcher
from address_alternatives import AddressFinder
from service_alternatives import KeywordSynonymFinder

class QueryProcessor:
    """
    A class to process natural language queries into Cypher queries.
    It encapsulates API clients, helper modules, and file paths.
    """
    def __init__(self, groq_api_key: str, address_file: str, service_file: str, log_directory: str):
        """
        Initializes the QueryProcessor.
        """
        self.logger = self._setup_logger(log_directory)
        
        if not groq_api_key:
            self.logger.critical("Groq API key not provided.")
            raise ValueError("GROQ_API_KEY is required.")
        
        self.groq_client = Groq(api_key=groq_api_key)
        self.address_file = address_file
        self.service_file = service_file

        self.finders = {
            'time': TimeMatcher(),
            'address': AddressFinder(),
            'service': KeywordSynonymFinder()
        }
        self.logger.info("QueryProcessor initialized successfully.")

    def _setup_logger(self, log_directory: str):
        """Configures and returns a logger instance."""
        os.makedirs(log_directory, exist_ok=True)
        log_filename = datetime.now().strftime(f'{log_directory}/%Y-%m-%d_%H-%M-%S_form_query.log')
        
        logger = logging.getLogger(f'QueryProcessor_{id(self)}')
        logger.setLevel(logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        if not logger.handlers:
            file_handler = logging.FileHandler(log_filename)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)
            
        return logger

    # In the QueryProcessor class within cypher_query.py

    def _get_categorized_keywords(self, user_query: str, step_counter):
        """Uses an LLM to analyze and categorize the user's query."""
        step_str = f"STEP {next(step_counter)}:"
        self.logger.info(f"{step_str} \n\n Analyzing user query with dispatcher LLM.")
        self.logger.info(f"  - INPUT (user_query): '{user_query}'")

        # --- PROMPT MODIFICATION IS HERE ---
        prompt = f"""
        You are a query analysis and routing expert. Your task is to analyze the user's query and extract keywords related to three specific categories: time, service, and location.
        The current date is July 23, 2025. The user is located in Philadelphia, PA. Use this for context.

        **--- RULES ---**
        1.  Analyze the user's query: "{user_query}"
        2.  When a service is described with an attribute (like 'free', '24-hour', 'emergency'), you MUST keep the attribute and the service together in the `service_keywords` field.
        3.  If a word could be a service or part of a location (like a street name), use context. A proper name like 'Wadsworth' or 'Haverford' is more likely a location in Philadelphia than a service.
        4.  Return a single JSON object with the keys "time_keywords", "service_keywords", and "location_keywords".
        5.  If a category is not mentioned, return an empty string for that key.

        **--- Nodes and Their Attributes ---**
        1.  "Location" Node's attributes: 'streetAddress', 'city', 'state', 'zipCode'.
        2.  "Service" Node's attributes: 'name', 'type' (Free or Paid).
        3.  "Time" Node's attributes: 'day', 'hour'.


        **--- EXAMPLES ---**
        Query 1: "I need a halal meal this evening in West Philly"
        Response 1: {{"time_keywords": "this evening", "service_keywords": "halal meal", "location_keywords": "West Philly"}}

        Query 2: "haircut"
        Response 2: {{"time_keywords": "", "service_keywords": "haircut", "location_keywords": ""}}
        
        Query 3: "free copy"
        Response 3: {{"time_keywords": "", "service_keywords": "free copy", "location_keywords": ""}}
        
        Query 4: "Wadsworth"
        Response 4: {{"time_keywords": "", "service_keywords": "", "location_keywords": "Wadsworth"}}
        ---
        Now, execute your task for the user's query.
        """
        # --- END OF PROMPT MODIFICATION ---

        try:
            response = self.groq_client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            result_json_str = response.choices[0].message.content
            parsed_json = json.loads(result_json_str)
            self.logger.info(f"  - OUTPUT (raw_llm_response): {result_json_str}")
            self.logger.info(f"  - OUTPUT (parsed_json): {parsed_json}")
            return parsed_json
        except Exception as e:
            self.logger.error(f"{step_str} Error calling dispatcher LLM: {e}")
            return None

    def generate_cypher_query(self, user_query: str) -> str:
        """
        Processes a single user query to generate a complete Cypher query string
        based on a dynamic template.
        """
        self.logger.info(f"\n\n ========= New Query Received: '{user_query}' =========\n")
        step_counter = iter(range(1, 100))
        
        # Initialize variables
        matching_times = []
        service_results = []
        matched_addresses = [] 

        # 1. Dispatcher Analysis
        categorized_query = self._get_categorized_keywords(user_query, step_counter)
        if not categorized_query:
            self.logger.error("Stopping processing for this query due to dispatcher failure.")
            return ""

        # 2. Time Intelligence
        time_keywords = categorized_query.get("time_keywords", "")
        if time_keywords:
            step_str = f"STEP {next(step_counter)}:"
            self.logger.info(f"{step_str} Calling Time Intelligence.")
            self.logger.info(f"  - INPUT: '{time_keywords}'")
            try:
                matching_times = self.finders['time'].find_matching_times(time_keywords)
                self.logger.info(f"  - OUTPUT: {matching_times}")
                print(f"\nTime finder returned {len(matching_times)} results.")
            except Exception as e:
                self.logger.error(f"{step_str} An error occurred in the TimeMatcher: {e}")

        # 3. Location Intelligence
        location_keywords = categorized_query.get("location_keywords", "")
        if location_keywords:
            step_str = f"STEP {next(step_counter)}:"
            self.logger.info(f"{step_str} Calling Location Intelligence.")
            self.logger.info(f"  - INPUT: '{location_keywords}'")
            try:
                matched_addresses = self.finders['address'].find_addresses(location_keywords, self.address_file)
                self.logger.info(f"  - OUTPUT (matched_addresses): {matched_addresses}")
                print(f"Location finder returned {len(matched_addresses)} potential location matches.")
            except Exception as e:
                self.logger.error(f"{step_str} An error occurred in Location Intelligence: {e}")

        # 4. Service Intelligence
        service_keywords = categorized_query.get("service_keywords", "")
        if service_keywords:
            step_str = f"STEP {next(step_counter)}:"
            self.logger.info(f"{step_str} \n\n Calling Service Intelligence.")
            self.logger.info(f"  - INPUT: '{service_keywords}'")
            try:
                keyword_list = self.finders['service'].read_keywords(self.service_file)
                if keyword_list:
                    service_results = self.finders['service'].find_interchangeable_keywords(service_keywords, keyword_list)
                    self.logger.info(f"  - OUTPUT (service_results): {service_results}")
                    print(f"Service finder returned {len(service_results)} results.")
                else:
                    self.logger.warning(f"Could not read services from {self.service_file}")
            except Exception as e:
                self.logger.error(f"{step_str} An error occurred in the KeywordSynonymFinder: {e}")

        # 5. Cypher Query Generation from Template
        step_str = f"STEP {next(step_counter)}:"
        self.logger.info(f"{step_str} \n\n Generating final Cypher Query from template.")

        # --- Initialize filters ---
        org_name_filter = "  // AND toLower(TRIM(replace(org.name, '\\u00A0', ' '))) CONTAINS toLower('YOUR_NAME_HERE')"
        org_phone_filter = "  // AND toLower(TRIM(replace(org.phone, '\\u00A0', ' '))) CONTAINS toLower('YOUR_PHONE_HERE')"
        org_status_filter = "  // AND toLower(TRIM(replace(org.status, '\\u00A0', ' '))) CONTAINS toLower('YOUR_STATUS_HERE')"
        loc_filter = "  // AND EXISTS{(org)-[:HAS_LOCATION]->(l:Location WHERE YOUR_LOCATION_CONDITION_HERE)}"
        svc_name_filter = "  // AND EXISTS{(org)-[:PROVIDES]->(s:Service WHERE toLower(TRIM(s.name)) CONTAINS toLower('YOUR_SERVICE_NAME_HERE'))}"
        svc_type_filter = "  // AND EXISTS{(org)-[:PROVIDES]->(s:Service WHERE toLower(TRIM(s.type)) CONTAINS toLower('YOUR_SERVICE_TYPE_HERE'))}"
        time_day_filter = "  // AND EXISTS{(org)-[:HAS_HOURS]->(t:Time WHERE toLower(TRIM(t.day)) CONTAINS toLower('YOUR_TIME_DAY_HERE'))}"
        time_hours_filter = "  // AND EXISTS{(org)-[:HAS_HOURS]->(t:Time WHERE toLower(TRIM(t.hours)) CONTAINS toLower('YOUR_TIME_HOURS_HERE'))}"

        # --- Focusing Logic based on Scenarios S1, S2, S3, S4 ---
        is_time_specific = 0 < len(matching_times) <= 5
        is_loc_specific = 0 < len(matched_addresses) <= 5
        is_svc_specific = 0 < len(service_results) <= 5
        specific_categories_exist = is_time_specific or is_loc_specific or is_svc_specific
        
        apply_time_filter = (time_keywords and (not specific_categories_exist or is_time_specific))
        apply_loc_filter = (location_keywords and (not specific_categories_exist or is_loc_specific))
        apply_svc_filter = (service_keywords and (not specific_categories_exist or is_svc_specific))

        if not specific_categories_exist and len(matching_times) > 5 and len(matched_addresses) > 5 and len(service_results) > 5:
            apply_time_filter = apply_loc_filter = apply_svc_filter = False
            self.logger.info("Scenario S3 detected: All keywords are too general. No filters will be applied.")

        # --- Activate and populate filters based on the focusing logic ---

        # Service Filter
        if apply_svc_filter:
            all_service_kws = list(set([kw.lower() for kw in [service_keywords] + service_results if kw]))
            remaining_service_kws = all_service_kws.copy()
            service_type_conditions = []
            if 'free' in remaining_service_kws:
                service_type_conditions.append("toLower(TRIM(s.type)) CONTAINS toLower('Free')")
                remaining_service_kws.remove('free')
            if 'paid' in remaining_service_kws:
                service_type_conditions.append("toLower(TRIM(s.type)) CONTAINS toLower('Paid')")
                remaining_service_kws.remove('paid')
            if service_type_conditions:
                svc_type_filter = f"  AND EXISTS{{(org)-[:PROVIDES]->(s:Service WHERE {' OR '.join(service_type_conditions)})}}"
            if remaining_service_kws:
                service_name_conditions = ' OR '.join([f"toLower(TRIM(s.name)) CONTAINS toLower('{kw}')" for kw in remaining_service_kws])
                svc_name_filter = f"  AND EXISTS{{(org)-[:PROVIDES]->(s:Service WHERE {service_name_conditions})}}"

        # Location Filters
        if apply_loc_filter:
            street_address_matches = []
            zip_code_matches = []
            location_conditions = []
            is_explicit_zip_query = location_keywords.isdigit() and len(location_keywords) == 5
            for item in matched_addresses:
                if item.isdigit() and len(item) == 5:
                    zip_code_matches.append(item)
                else:
                    street_address_matches.append(item)
            if not is_explicit_zip_query:
                zip_code_matches = zip_code_matches[:2]
            if street_address_matches:
                for addr in street_address_matches:
                    escaped_addr = addr.replace("'", "\\'")
                    location_conditions.append(f"l.streetAddress CONTAINS '{escaped_addr}'")
            if zip_code_matches:
                for zip_code in zip_code_matches:
                    location_conditions.append(f"l.zipCode CONTAINS '{zip_code}'")
            if location_conditions:
                combined_location_logic = ' OR '.join(location_conditions)
                loc_filter = f"  AND EXISTS{{(org)-[:HAS_LOCATION]->(l:Location WHERE {combined_location_logic})}}"
        
        # --- NEW: Time Filter ---
        if apply_time_filter:
            day_conditions = []
            hours_conditions = []
            days_of_week = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

            # Partition the results from TimeMatcher into days and hours
            for t in matching_times:
                if t.lower() in days_of_week:
                    day_conditions.append(f"toLower(TRIM(t.day)) CONTAINS toLower('{t}')")
                else:
                    hours_conditions.append(f"toLower(TRIM(t.hours)) CONTAINS toLower('{t}')")

            # Activate the day filter if any day conditions were found
            if day_conditions:
                time_day_filter = f"  AND EXISTS{{(org)-[:HAS_HOURS]->(t:Time WHERE {' OR '.join(day_conditions)})}}"

            # Activate the hours filter if any hour conditions were found
            if hours_conditions:
                time_hours_filter = f"  AND EXISTS{{(org)-[:HAS_HOURS]->(t:Time WHERE {' OR '.join(hours_conditions)})}}"
        
        # --- Assemble the final query ---
        final_query = f"""
MATCH (org:Organization)

// To use a filter, remove the '//' from the start of the line and edit the value.
WHERE 1=1 // This dummy condition lets you safely uncomment any AND line below.

  // -- Filters on Organization Properties --
{org_name_filter}
{org_phone_filter}
{org_status_filter}

  // -- Filters on Location Properties --
{loc_filter}

  // -- Filters on Service Properties --
{svc_name_filter}
{svc_type_filter}

  // -- Filters on Time Properties --
{time_day_filter}
{time_hours_filter}

// The RETURN clause remains the same to prevent data repetition.
RETURN org,
       [(org)-[:HAS_LOCATION]->(loc) | loc] AS locations,
       [(org)-[:PROVIDES]->(svc) | svc] AS services,
       [(org)-[:HAS_HOURS]->(tm) | tm] AS operatingHours
"""
        self.logger.info(f"  - OUTPUT (Generated Cypher Query):\n{final_query}")
        print("\n--- Generated Cypher Query ---")
        print(final_query)
        print("----------------------------")

        return final_query

def main():
    """
    Main function to demonstrate the QueryProcessor class in an interactive loop.
    This part runs only when the script is executed directly.
    """
    print("Starting Interactive Query Processor...")
    load_dotenv()
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    # PLEASE UPDATE THESE PATHS to 'keywords.txt' and your desired log directory
    BASE_DIR = 'Local_DreamKG/v5_real_data' # Assuming script is run from the project root
    ADDRESS_FILE = os.path.join(BASE_DIR, 'keywords.txt') 
    SERVICE_FILE = os.path.join(BASE_DIR, 'keywords.txt')
    LOG_DIR = os.path.join(BASE_DIR, 'logs')

    try:
        processor = QueryProcessor(
            groq_api_key=GROQ_API_KEY,
            address_file=ADDRESS_FILE,
            service_file=SERVICE_FILE,
            log_directory=LOG_DIR
        )
    except Exception as e:
        logging.critical(f"A critical error occurred during initialization: {e}")
        return

    while True:
        print("\n" + "="*50)
        user_query = input("Enter your search query (or type 'exit' to quit): ")
        if user_query.lower() in ['exit', 'quit']:
            print("Goodbye!")
            break
        if not user_query.strip():
            print("Query cannot be empty. Please try again.")
            continue
        processor.generate_cypher_query(user_query)

if __name__ == "__main__":
    main()