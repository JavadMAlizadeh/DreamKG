import os
import json
from groq import Groq
from dotenv import load_dotenv

class KeywordSynonymFinder:
    """
    A class to find all synonyms for a given keyword from a list of keywords
    using the Groq LLM API.
    """

    def __init__(self):
        """
        Initializes the KeywordSynonymFinder by loading the API key
        and setting up the Groq client.
        """
        # Load environment variables from a .env file
        load_dotenv()
        groq_api_key = os.environ.get("GROQ_API_KEY")

        if not groq_api_key:
            raise ValueError("GROQ_API_KEY not found in .env file or environment variables.")

        # Initialize the Groq client
        self.llm = Groq(api_key=groq_api_key)
        print("Groq client initialized successfully.")

    def read_keywords(self, file_path: str) -> list[str]:
        """
        Reads keywords from a given text file.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                keywords = [line.strip() for line in f if line.strip()]
            print(f"Successfully loaded {len(keywords)} keywords from {file_path}.")
            return keywords
        except FileNotFoundError:
            print(f"Error: The file at {file_path} was not found.")
            return []

    def find_interchangeable_keywords(self, user_keyword: str, keyword_list: list[str]) -> list[str]: # CHANGED
        """
        Uses the Groq LLM to find all closely related keywords from a list
        by deconstructing the user's query.
        
        Returns a list of matching keywords. # CHANGED
        """
        if not keyword_list:
            print("No keywords loaded to compare against.")
            return [] # CHANGED

        # This prompt is the same as before.
        prompt = f"""
        The following list of keywords represents service categories and their attributes: {', '.join(keyword_list)}.
        The user's full search query is: "{user_keyword}".

        Your task is to intelligently deconstruct the user's query and find ALL related keywords from the provided list.
        You must understand that some words in the query are attributes (like 'free') of a main service (like 'scan'). Your goal is to find alternatives for the service AND include the mentioned attributes if they exist in the list.

        Follow these steps:
        1.  **Analyze the Query:** In the user's query "{user_keyword}", identify the primary service keyword and any attribute keywords.
        2.  **Find Service Synonyms:** Search the keyword list for all words related to the primary service. For example, if the service is 'scan', related keywords could be 'Scanning' or 'Copiers'.
        3.  **Find Attribute Keywords:** Search the keyword list for any words that exactly match the attributes you identified in step 1. For example, if the attribute is 'free', find 'Free' in the list.
        4.  **Combine and Return:** Combine the results from steps 2 and 3.

        Return a JSON object with one key: "synonyms".
        - The value for "synonyms" should be a JSON array containing all the relevant service synonyms AND attribute keywords found in the list.
        - If none are relevant, the value should be an empty array [].
        """

        print(f"\nSending complex prompt to Groq LLM for query: '{user_keyword}'...")
        try:
            response = self.llm.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )

            response_content = response.choices[0].message.content
            print("Received response from LLM.")
            data = json.loads(response_content)

            # --- KEY CHANGE IS HERE ---
            # Instead of formatting a string, return the list directly.
            found_keywords = data.get("synonyms", [])
            
            if found_keywords:
                # Return the list of keywords directly
                return sorted([kw.lower() for kw in found_keywords])
            else:
                # Return an empty list if nothing is found
                return []

        except json.JSONDecodeError:
            print("Error: Failed to decode JSON response from the LLM.") # CHANGED
            return [] # CHANGED
        except Exception as e:
            print(f"An error occurred while communicating with the Groq API: {e}") # CHANGED
            return [] # CHANGED

def main():
    """
    Main function to run the synonym finder application.
    """
    try:
        finder = KeywordSynonymFinder()
        # The path to your keywords file.
        keyword_file_path = "/Users/javad/Documents/MEGA/Workspace/VisualStudio/Local_DreamKG/v5_real_data/keywords.txt"
        keywords = finder.read_keywords(keyword_file_path)

        if not keywords:
            print(f"Please ensure the file exists at '{keyword_file_path}' and contains keywords.")
            return

        while True:
            # The main loop now sends the entire user input string again.
            user_input = input("\nEnter a keyword to find related words (or type 'exit' to quit): ")
            if user_input.lower() == 'exit':
                break

            result = finder.find_interchangeable_keywords(user_input, keywords)
            print(result)

    except ValueError as e:
        print(e)

if __name__ == "__main__":
    main()