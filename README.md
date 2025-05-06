# AI Research Assistant

A chatbot that automatically collects and processes the top 20 most prominent AI research papers, allowing you to ask questions about cutting-edge AI research. Built with Streamlit and LangChain.

## Setup

1. Create a `.env` file by copying `.env.example` and add your OpenAI API key:
```
OPENAI_API_KEY=your-api-key-here
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Start the article updater:
```bash
python ai_articles_updater.py
```
This will:
- Automatically search for the most prominent AI papers
- Download them to the `pdfDatabase` directory
- Update the collection daily at midnight

4. Run the application:
```bash
streamlit run app.py
```

## Usage

1. The application automatically loads all PDF documents from the `pdfs` directory
2. Wait for the documents to be processed
3. Start asking questions about the content of the PDFs
4. View the chat history below the input field

## Adding New Documents

To add new PDF documents:
1. Place the PDF files in the `pdfs` directory
2. Restart the application
