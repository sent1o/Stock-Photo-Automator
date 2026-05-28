# 🚀 Stock Photo Automator (Fooocus Pipeline)

A desktop application designed to fully automate the workflow of generating, upscaling, and tagging AI-generated images for stock photography platforms. 

Built as an MVP for a streamlined content creation pipeline, this tool connects a local Fooocus (Stable Diffusion) server with an automated UI, handling everything from batch generation to embedding AI-generated IPTC metadata.

## ✨ Features

* **GUI Dashboard:** Clean, user-friendly interface built with PyQt6 for managing paths, API keys, and monitoring background tasks.
* **Headless Automation:** Uses Playwright to interact with the local Fooocus web UI, bypassing the need for manual browser clicks during generation and upscaling.
* **Smart Prompt Management:** Automatically saves and loads text prompts for batch generation.
* **Automated Upscaling:** Grabs generated images, pushes them through the Fooocus 2x upscale pipeline, and saves them as production-ready JPEGs.
* **AI Metadata Injection:** Parses generation logs via BeautifulSoup, sends the original prompt to the OpenAI API (GPT-4o-mini), and automatically injects title, description, and 25 optimized keywords directly into the image's IPTC metadata.

## 🛠️ Tech Stack

* **Language:** Python 3.10+
* **UI Framework:** PyQt6
* **Automation:** Playwright
* **AI & API:** OpenAI API (GPT-4o-mini)
* **Data Processing:** BeautifulSoup4 (HTML parsing), IPTCInfo3 (Metadata injection)

## ⚙️ Prerequisites

1. Python installed on your system.
2. A local installation of Fooocus.
3. An active OpenAI API key.

## 🚀 Installation & Setup

1. Clone the repository:
   git clone https://github.com/yourusername/stock-photo-automator.git
   cd stock-photo-automator

2. Install dependencies:
   pip install -r requirements.txt
   playwright install chromium

3. Configure Environment:
   Create a .env file in the root directory and add your OpenAI API key:
   OPENAI_API_KEY=sk-your-api-key-here

## 🎯 Usage

1. Run the application:
   python main_ui.py
2. In the UI, set the path to your local Fooocus Root Folder.
3. Click "🚀 Запустити Fooocus" to start the local server in the background (or use the manual button to open it in your browser).
4. Generation Phase: Paste your prompts (one per line) and click Generate. Images will be saved to the 1_To_Upscale folder.
5. Upscale & Metadata Phase: Click the Upscale button. The app will process images from 1_To_Upscale, upscale them, fetch AI-generated keywords, embed the IPTC metadata, and output the final stock-ready files to 2_Ready_Stock.

## 📝 Note
This is an MVP built for a specific educational and content-creation workflow, focusing on functional automation over extensive error handling for edge cases.