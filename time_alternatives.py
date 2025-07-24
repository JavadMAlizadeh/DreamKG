import os
import json
from dotenv import load_dotenv
from groq import Groq

class TimeMatcher:
    """
    A class to find matching times from a file using an LLM.
    """
    def __init__(self, times_file_path='keywords.txt'):
        """
        Initializes the TimeMatcher by loading the API key, setting up the Groq client,
        and reading the specified times file.

        Args:
            times_file_path (str): The full path to the file containing the list of times.
        """
        # Load environment variables from a .env file
        load_dotenv()
        groq_api_key = os.environ.get("GROQ_API_KEY")

        if not groq_api_key:
            raise ValueError("GROQ_API_KEY not found in .env file or environment variables.")

        # Initialize the Groq client
        self.llm = Groq(api_key=groq_api_key)
        self.times_content = self._read_times_file(times_file_path)

    def _read_times_file(self, file_path):
        """
        Reads the contents of the specified times file.

        Args:
            file_path (str): The path to the times file.

        Returns:
            str: The content of the file as a single string.
        """
        try:
            with open(file_path, 'r') as f:
                return f.read()
        except FileNotFoundError:
            print(f"Error: The file at {file_path} was not found.")
            return ""

    def find_matching_times(self, user_query):
        """
        Uses the LLM to find times in the file that match the user's query.

        Args:
            user_query (str): The user's description of the time (e.g., "afternoon").

        Returns:
            list: A list of matching time strings, or an empty list if none are found.
        """
        if not self.times_content:
            return ["The times file is empty or could not be read."]

        # This prompt is updated to handle the unstructured list of keywords.
        prompt = f"""
        You are a smart search assistant. From the unstructured list of keywords provided below, find all entries that are a plausible match for the user's request.

        Available Keywords List:
        ---
        {self.times_content}
        ---

        User's Request: "{user_query}"

        Follow these rules for matching:
        1.  **Direct Match:** If the user's query (e.g., "Monday", "Chess", "19103") exists in the list, return it.
        2.  **Abbreviation/Partial Match:** If the request is a likely abbreviation (e.g., "mon" for "Monday"), return the full matching keyword from the list.
        3.  **Time Match:** If the request is a specific time (e.g., "8pm"), find any keyword in the list representing a time range that *includes* that time. For example, a query for "8pm" should match "9:00 AM - 8:00 PM".
        4.  **Contextual Guessing:** For queries like "afternoon," find time ranges that commonly represent afternoon (e.g., "10:00 AM - 5:00 PM"). Be aware that you cannot link a day to a time, so just return the matching time ranges.

        Return a JSON object with a single key "found_times" which is a list of all matching keywords from the original list.
        If no keywords match, return an empty list.
        """

        try:
            response = self.llm.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            # The response from the LLM is a JSON string, so we need to parse it.
            result = json.loads(response.choices[0].message.content)
            return result.get("found_times", [])
        except Exception as e:
            print(f"An error occurred while communicating with the LLM: {e}")
            return []

def main():
    """
    Main function to demonstrate the TimeMatcher.
    """
    try:
        # The TimeMatcher will now use the new default path specified in the __init__ method.
        time_matcher = TimeMatcher()
    except ValueError as e:
        print(e)
        print("Please make sure you have a .env file in the same directory with your GROQ_API_KEY.")
        return

    # Loop to continuously ask the user for input
    while True:
        query = input("Enter a time to search for (or type 'exit' to quit): ")
        if query.lower() in ['exit', 'quit']:
            break
        
        print(f"User query: '{query}'")
        print("-" * 20)

        # Find the matching times for the current query
        matching_times = time_matcher.find_matching_times(query)

        if matching_times:
            print("Found possible times:")
            for time in matching_times:
                print(f"- {time}")
        else:
            # If the list is empty, no times were found
            print("I couldn't find any time!!")
        print("\n" + "="*30 + "\n")

if __name__ == "__main__":
    main()