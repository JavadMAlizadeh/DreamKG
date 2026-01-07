# DreamKG

DreamKG is a **conversational system** designed to help **people experiencing homelessness** and **social workers** quickly find nearby social services such as food banks, libraries, shelters, mental health support, and Social Security offices.

The system combines **large language models (LLMs)**, **Neo4j knowledge graphs**, **spatial intelligence**, and a **Streamlit interface** to deliver simple, trustworthy, and context-aware answers to natural language questions like:

> *“Is there a food pantry near me?”*
> *“Are they open today?”*
> *“Do they have Wi‑Fi?”*

DreamKG is built to work quietly in the background while prioritizing **clarity, accessibility, and follow‑up understanding**.

---

## 🌐 Project Websites

* **DREAM-KG website:** [https://dreamkg.com/](https://dreamkg.com/)
* **Proto-OKN initiative:** [https://www.proto-okn.net/](https://www.proto-okn.net/)

---

## 🧭 Proto-OKN Context

DREAM-KG is part of a broader NSF-funded national initiative called **Building the Prototype Open Knowledge Network (Proto-OKN)**.

On **September 26, 2023**, the U.S. National Science Foundation (NSF), in collaboration with **five other U.S. government agencies**, announced an investment of **$26.7 million across 18 projects** through the Proto-OKN program.

Proto-OKN aims to create a **publicly accessible, interconnected network of data repositories and knowledge graphs** to support **data-driven, AI-based solutions** for major societal and economic challenges.

---

## ✨ Key Features

### 🧠 Conversational Memory

* Remembers previously returned organizations
* Resolves pronouns and follow‑up questions ("they", "them", "those places")
* Avoids forcing users to repeat context

### 📍 Spatial Intelligence

* Detects location intent automatically
* Supports landmarks, streets, zip codes, and proximity phrases
* Computes distance using Neo4j spatial functions
* Expands search radius when no results are found

### 🧩 Knowledge Graph Backend (Neo4j)

* Organizations, services, locations, and hours are modeled explicitly
* Returns **all services** for matched organizations (not just filtered ones)
* APOC-enabled temporal queries for hours (e.g., *open after 5pm*)

### 🗣️ LLM‑Driven Query Understanding

* Converts natural language → Cypher queries
* Uses strict prompt rules to ensure executable Cypher only
* Intelligent service keyword normalization (e.g., *wifi → wi‑fi*)

### 🧾 Two‑Tier Response Design

* **Short view**: name, distance, phone, address, key services
* **Expandable view**: full hours + complete service list
* Designed for non‑technical users

### 📊 Logging & Evaluation

* Session‑based logging
* Uploads complete logs to Google Sheets
* Token usage, latency, and execution metrics supported

---

## 🏗️ System Architecture

```
User → Streamlit UI
     → QueryService (LLM + Memory + Spatial Intelligence)
     → Neo4j Knowledge Graph
     → ResponseService (Two‑Tier Output)
     → Streamlit Display
     → Google Sheets Logger (optional)
```

---

## 📂 Project Structure

```
.
├── streamlit_app.py          # Main Streamlit UI
├── config.py                 # Central configuration & secrets
├── requirements.txt          # Python dependencies
│
├── database/
│   └── neo4j_client.py       # Neo4j connection & schema handling
│
├── models/
│   ├── spatial_intelligence.py   # Location detection & geocoding
│   └── conversation_memory.py    # Conversational memory logic
│
├── services/
│   ├── query_service.py      # Core NL → Cypher pipeline
│   ├── response_service.py   # Two‑tier response generation
│   └── google_sheets_logger.py
│
├── templates/
│   └── prompts.py            # Strict Cypher + QA prompt templates
│
├── logs/                     # Session log files
└── README.md
```

---

## 🚀 Getting Started

### 1️⃣ Prerequisites

* Python 3.9+
* Neo4j 5.x with APOC enabled
* Google Cloud service account (for logging)
* Groq API key

---

### 2️⃣ Installation

```bash
pip install -r requirements.txt
```

---

### 3️⃣ Configuration

All secrets are loaded via **Streamlit Secrets**.

Example `.streamlit/secrets.toml`:

```toml
NEO4J_URI = "bolt+s://..."
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "password"
GROQ_API_KEY = "your_key"

[google_credentials]
type = "service_account"
project_id = "dreamkg"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n..."
client_email = "logger@dreamkg.iam.gserviceaccount.com"
```

---

### 4️⃣ Run the App

```bash
streamlit run streamlit_app.py
```

---

## 🔍 How Queries Work

1. **User asks a question** in plain language
2. System detects:

   * spatial intent
   * service intent
   * follow‑up context
3. LLM generates **strict Cypher** (no prose)
4. Neo4j executes query
5. Results are formatted into two tiers
6. Memory is updated for follow‑ups

---

## 🧠 Conversational Memory Design

* Stores last results + spatial context
* Decides when memory should be reused
* Rewrites queries by substituting pronouns
* Clears memory when a new independent search fails

Example:

> User: *“Libraries near City Hall”*
> User: *“Are they open on Tuesday?”*

The second query automatically references the previously returned libraries.

---

## 📍 Spatial Intelligence Highlights

* Landmark‑aware (City Hall, Temple University, Center City, etc.)
* Avoids false positives for time phrases ("around 8pm")
* Uses distance as the **only** spatial filter for spatial queries

---

## 📊 Logging & Metrics

Each session:

* Generates a unique log file
* Stores full conversation + execution details
* Uploads logs to Google Sheets (one row per session)

Metrics supported:

* Token usage (input/output)
* Time to first token
* LLM latency
* Neo4j execution time
* Expanded‑radius search detection

---

## 🎯 Intended Users

* People experiencing homelessness
* Social workers & case managers
* Community outreach organizations
* Researchers working on AI for social good

---

## 🔒 Design Principles

* Accessibility over technical complexity
* Short answers first, details on demand
* No requirement for technical knowledge
* Trustworthy, explainable retrieval

---

## 📌 Limitations & Future Work

* Currently focused on Philadelphia
* Requires curated Neo4j data
* Future plans:

  * Multi‑city support
  * Multilingual interface
  * Voice input
  * Offline kiosk deployment

---

## 🤝 Contributing

Contributions are welcome.

Suggested areas:

* Knowledge graph enrichment
* UX improvements
* Memory reasoning enhancements
* Evaluation & benchmarking

---

## 📄 License

This project is released under an open‑source license for research and social impact use.

---

## 📬 Contact

For questions or collaboration, please contact the project maintainers.
