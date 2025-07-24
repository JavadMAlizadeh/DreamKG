import os
import re
import json
from groq import Groq
from dotenv import load_dotenv

class AddressFinder:
    """
    A class to find addresses using a hybrid approach of AI-driven geocoding
    and local keyword searching.
    """
    def __init__(self):
        """
        Initializes the AddressFinder, loading the Groq API key and the LLM.
        """
        load_dotenv()
        groq_api_key = os.environ.get("GROQ_API_KEY")

        if not groq_api_key:
            raise ValueError("GROQ_API_KEY not found in .env file. Please add it.")
        self.llm = Groq(api_key=groq_api_key)

    def read_addresses(self, file_path):
        """Reads all non-empty address lines from a given text file."""
        try:
            with open(file_path, "r") as f:
                return [line.strip() for line in f.readlines() if line.strip()]
        except FileNotFoundError:
            print(f"Error: The file at {file_path} was not found.")
            return []

    def _preprocess_addresses(self, all_lines):
        """Creates a dictionary mapping ZIP codes to addresses."""
        zip_to_addresses = {}
        zip_regex = re.compile(r'\b(\d{5})\b')
        for line in all_lines:
            match = zip_regex.search(line)
            if match:
                zip_code = match.group(1)
                if zip_code not in zip_to_addresses:
                    zip_to_addresses[zip_code] = []
                zip_to_addresses[zip_code].append(line)
        return zip_to_addresses

    def _get_target_zips_from_llm(self, user_address):
        """Uses an LLM to convert user input into a list of ZIP codes."""
        prompt = f"""
        You are a geocoding assistant. Your sole function is to identify a primary US ZIP code and its adjacent ZIP codes from a user's query. Return a single JSON object with one key, "zip_codes", containing a list of all identified ZIP codes (the primary one first).

        **Example 1:**
        - User's Location: "Spring Garden, Philadelphia"
        - Your Response: {{"zip_codes": ["19130", "19123", "19103", "19102", "19121", "19122"]}}

        **Example 2:**
        - User's Location: "19147"
        - Your Response: {{"zip_codes": ["19147", "19146", "19106", "19107", "19148", "19145"]}}
        
        ---
        **Your Task:**
        User's Location: "{user_address}"
        Now, provide only the JSON response.
        """
        try:
            response = self.llm.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            return data.get("zip_codes", [])
        except Exception as e:
            print(f"An error occurred while contacting the LLM: {e}")
            return []

    def find_addresses(self, user_input: str, address_file_path: str) -> list[str]:
        """
        Performs the full hybrid (geographic + keyword) search and returns a
        list of unique, sorted address strings. This is the new primary method.
        """
        all_addresses = self.read_addresses(address_file_path)
        if not all_addresses:
            return []

        address_index = self._preprocess_addresses(all_addresses)

        # --- Search Part 1: Geographic Search ---
        target_zips = self._get_target_zips_from_llm(user_input)
        geographic_matches = []
        if target_zips:
            for zip_code in target_zips:
                geographic_matches.extend(address_index.get(zip_code, []))

        # --- Search Part 2: Keyword Search ---
        keyword_matches = [
            addr for addr in all_addresses
            if user_input.lower() in addr.lower()
        ]
        
        # --- Combine and Finalize Results ---
        combined_results = set(geographic_matches)
        combined_results.update(keyword_matches)
        
        return sorted(list(combined_results))

    def run(self):
        """Main loop to run the standalone address finder application."""
        address_file_path = "DreamKG/keywords.txt"
        
        print("\nWelcome to the Address Finder! 🗺️")
        print("I will find addresses from your list that are in the same or adjacent ZIP codes, AND any addresses that contain your search term.")
        print("-" * 30)

        while True:
            user_input = input("Enter a reference address, city, or ZIP code (or 'quit' to exit): ")
            if user_input.lower() == 'quit':
                break

            if not user_input.strip():
                print("Please enter a location.")
                continue

            # Use the new primary method to get the final list
            final_list = self.find_addresses(user_input, address_file_path)

            if final_list:
                print(f"\nFound {len(final_list)} unique address(es) from combined search:")
                for address in final_list:
                    print(f"- {address}")
            else:
                print("\nNo addresses found from either geographic or keyword search.")

            print("-" * 30)


if __name__ == "__main__":
    finder = AddressFinder()
    finder.run()