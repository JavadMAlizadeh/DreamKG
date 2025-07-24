import os
import logging
from datetime import datetime
import json
import time # <-- Added for timing operations
from dotenv import load_dotenv
from neo4j import GraphDatabase, exceptions
from groq import Groq

# Import the user-provided query generator
from cypher_query import QueryProcessor

class Neo4jApp:
    """
    Orchestrates the process of generating a Cypher query from natural language,
    executing it on Neo4j, and polishing the results with an LLM.
    """
    def __init__(self):
        """
        Initializes the application, loads configuration, and sets up connections.
        """
        # Load environment variables from .env file
        load_dotenv()

        # --- Use a relative path for the log directory ---
        script_dir = os.path.dirname(__file__)
        self.log_directory = os.path.join(script_dir, 'logs')
        self.logger = self._setup_logger()

        self.logger.info("Initializing Neo4j Application...")

        # --- Get API Keys and Credentials ---
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.neo4j_uri = os.getenv("NEO4J_URI")
        self.neo4j_user = os.getenv("NEO4J_USERNAME")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD")

        if not all([self.groq_api_key, self.neo4j_uri, self.neo4j_user, self.neo4j_password]):
            self.logger.critical("Missing one or more required environment variables. Check your .env file or Streamlit secrets.")
            raise ValueError("Required environment variables are not set.")

        # --- Initialize Clients and Drivers ---
        try:
            # Initialize the Groq client
            self.groq_client = Groq(api_key=self.groq_api_key)
            self.logger.info("Groq client initialized successfully.")

            # --- CORRECTED PART: Use a relative path for keywords.txt ---
            # This ensures it finds the file when deployed on Streamlit Cloud.
            keywords_path = os.path.join(script_dir, 'keywords.txt')
            self.logger.info(f"Looking for keywords file at: {keywords_path}")

            self.query_processor = QueryProcessor(
                groq_api_key=self.groq_api_key,
                address_file=keywords_path,
                service_file=keywords_path,
                log_directory=self.log_directory
            )
            self.logger.info("QueryProcessor initialized successfully.")

            # Connect to Neo4j
            self.driver = GraphDatabase.driver(self.neo4j_uri, auth=(self.neo4j_user, self.neo4j_password))
            self.driver.verify_connectivity()
            self.logger.info("Neo4j driver initialized and connection verified. \n")

        except Exception as e:
            self.logger.critical(f"A critical error occurred during initialization: {e}")
            raise

    def _setup_logger(self):
        """Configures and returns a logger instance for the main application."""
        os.makedirs(self.log_directory, exist_ok=True)
        log_filename = datetime.now().strftime(f'{self.log_directory}/%Y-%m-%d_%H-%M-%S_main_app.log')

        logger = logging.getLogger('Neo4jApp')
        logger.setLevel(logging.INFO)

        # Prevent duplicate handlers if the script is re-run in the same process
        if not logger.handlers:
            # File handler
            file_handler = logging.FileHandler(log_filename)
            file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

            # Console handler
            stream_handler = logging.StreamHandler()
            stream_formatter = logging.Formatter('%(levelname)s: %(message)s')
            stream_handler.setFormatter(stream_formatter)
            logger.addHandler(stream_handler)

        return logger

    def execute_cypher_query(self, query: str):
        """
        Executes a Cypher query against the Neo4j database.
        """
        if not query or not query.strip():
            self.logger.warning("Attempted to execute an empty Cypher query.")
            return []

        self.logger.info(f"INPUT to Neo4j Executor (Cypher Query):\n{query}")
        start_time = time.monotonic()

        records_list = []
        try:
            with self.driver.session() as session:
                result = session.run(query)
                records_list = [record.data() for record in result]
            
            duration = time.monotonic() - start_time
            # Log the output from this function, now including the duration
            self.logger.info(f"OUTPUT from Neo4j Executor ({len(records_list)} records found in {duration:.2f}s):\n{json.dumps(records_list, indent=2)}")
            return records_list
        except exceptions.CypherSyntaxError as e:
            self.logger.error(f"Cypher Syntax Error: {e}")
        except exceptions.ServiceUnavailable as e:
            self.logger.error(f"Neo4j connection error: {e}. Is the database running?")
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during query execution: {e}")
        return []

    def polish_results_with_llm(self, results: list, original_query: str):
        """
        Sends the raw database results to an LLM to generate a user-friendly summary.
        """
        if not results:
            self.logger.info("No results to polish. Returning a standard message.")
            return "I couldn't find any results matching your query. Please try being more specific or rephrasing your request."

        results_str = json.dumps(results, indent=2)
        self.logger.info(f"INPUT to Polishing LLM (Original Query): '{original_query}'")
        self.logger.info(f"INPUT to Polishing LLM (Neo4j Results):\n{results_str}")

        prompt = f"""
        You are a highly precise and helpful assistant. Your task is to transform raw database search results into a clear and, above all, **accurate** user-friendly summary.
        The user asked: "{original_query}"
        Here are the raw search results from the knowledge graph in JSON format:
        {results_str}

        **--- CRITICAL INSTRUCTIONS ---**
        1.  **Adhere Strictly to the Data**: Your primary goal is to be factual. Do NOT invent information or make assumptions. Your response must be directly supported by the JSON data.
        2.  **Verify Service Costs**: The user may ask for "free" services. For each service you mention, you MUST check its "type" field in the JSON data.
            * If the user asks for a free service and the data confirms `"type": "Free"`, state that the service is free.
            * If the user asks for a free service but the data shows its `"type": "Paid"`, you MUST explicitly state that the service is paid. This is the most important rule.
        3.  **Handle Mismatches Intelligently**: If you cannot find a perfect match for the user's request, offer the closest alternative found in the data.
            * **Example**: If the user asks for "free printing" and you only find "paid printing" and "free Wi-Fi", you should say: "While I couldn't find free printing, the Wadsworth Library at 1500 Wadsworth Avenue does offer paid printing services. They also provide other free services like Wi-Fi and public computer access."
        4.  **Synthesize, Don't Just List**: Create a coherent, natural-language list. Group information for the same organization logically.
        5.  **Avoid Technical Jargon**: Do not use words like "JSON", "nodes", "records", or "database".

        Now, generate the polished and factually accurate response for the provided results based on these strict instructions.
        """

        try:
            start_time = time.monotonic()
            response = self.groq_client.chat.completions.create(
                model="llama3-70b-8192",  # This model is sufficient with a good prompt
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0, # Set temperature to 0.0 for maximum factuality
            )
            duration = time.monotonic() - start_time
            
            polished_text = response.choices[0].message.content
            usage = response.usage
            
            log_message = (
                f"OUTPUT from Polishing LLM (took {duration:.2f}s | "
                f"Prompt: {usage.prompt_tokens}, Completion: {usage.completion_tokens}, Total: {usage.total_tokens} tokens):\n"
                f"{polished_text}"
            )
            self.logger.info(log_message)
            return polished_text
        except Exception as e:
            self.logger.error(f"Error calling Groq API for polishing: {e}")
            return "Please make your request more specific!"

    def process_user_request(self, user_query: str):
        """
        The main orchestration method for handling a single user request.
        """
        self.logger.info(f"============================== New User Request Received: '{user_query}' =============================== \n")
        print("\nThinking...")
        total_start_time = time.monotonic()

        # 1. Generate Cypher Query
        self.logger.info(f"STEP 1: Generating Cypher Query...")
        self.logger.info(f"INPUT to QueryProcessor: '{user_query}'")
        
        gen_start_time = time.monotonic()
        cypher_query = self.query_processor.generate_cypher_query(user_query)
        gen_duration = time.monotonic() - gen_start_time
        
        if not cypher_query or not cypher_query.strip():
            self.logger.error("QueryProcessor failed to generate a Cypher query. Aborting.")
            print("I'm sorry, I couldn't understand your request. Could you please rephrase it?")
            return
            
        self.logger.info(f"OUTPUT from QueryProcessor (took {gen_duration:.2f}s):\n{cypher_query}")
        # NOTE: To capture token usage here, the 'generate_cypher_query' method in 'cypher_query.py'
        # must be updated to return the token information from its Groq API call along with the query string.
        # self.logger.warning("Token usage for query generation is not logged. See code comments for details.")

        # 2. Execute Query in Neo4j
        self.logger.info(f"STEP 2: Executing query in Neo4j...")
        raw_results = self.execute_cypher_query(cypher_query)

        # 3. Polish Results with LLM
        self.logger.info(f"STEP 3: Polishing results with LLM...")
        polished_response = self.polish_results_with_llm(raw_results, user_query)

        # 4. Display Final Response
        total_duration = time.monotonic() - total_start_time
        print("\n--- Here's what I found for you ---\n")
        print(polished_response)
        print("\n" + "="*50)
        self.logger.info(f"--- Finished Processing Request for: '{user_query}' in {total_duration:.2f}s --- \n")

    def close(self):
        """Closes the Neo4j database connection."""
        if self.driver:
            self.logger.info("Closing Neo4j connection.")
            self.driver.close()

    def process_user_request_for_streamlit(self, user_query: str):
        """
        Orchestration method for Streamlit. It returns the final response as a string.
        """
        self.logger.info(f"================== New Streamlit Request: '{user_query}' ==================\n")

        # 1. Generate Cypher Query
        cypher_query = self.query_processor.generate_cypher_query(user_query)
        if not cypher_query or not cypher_query.strip():
            self.logger.error("QueryProcessor failed to generate a Cypher query.")
            return "I'm sorry, I couldn't understand your request. Could you please rephrase it?"

        # 2. Execute Query
        raw_results = self.execute_cypher_query(cypher_query)

        # 3. Polish results (or handle no results)
        polished_response = self.polish_results_with_llm(raw_results, user_query)
        
        self.logger.info(f"--- Finished Processing Streamlit Request for: '{user_query}' --- \n")
        return polished_response

def main():
    """
    Main function to run the interactive application.
    """
    app = None
    try:
        app = Neo4jApp()
        print("Welcome to the Smart Search Assistant! I can help you find information.")
        print("Type your query below, or type 'exit' to quit.")
        print("="*50)

        while True:
            user_input = input("Your request: ")
            if user_input.lower() in ['exit', 'quit']:
                print("Goodbye!")
                break
            if not user_input.strip():
                print("Please enter a valid request.")
                continue

            app.process_user_request(user_input)

    except Exception as e:
        # Use the root logger in case the app logger failed to initialize
        logging.critical(f"The application failed to start or run: {e}", exc_info=True)
        print(f"\nA critical error occurred. Please check the logs in the '{'logs'}' directory for details.")
    finally:
        if app:
            app.close()

if __name__ == "__main__":
    main()