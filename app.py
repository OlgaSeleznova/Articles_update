
import streamlit as st
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List
from pydantic.v1 import BaseModel
from langgraph.graph import MessagesState, StateGraph
from langchain_community.document_loaders import FileSystemBlobLoader
from langchain_community.document_loaders.generic import GenericLoader
from langchain_community.document_loaders.parsers import PyPDFParser
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langgraph.graph import END
from langgraph.prebuilt import ToolNode, tools_condition
from dotenv import load_dotenv
import os
import traceback
import time

load_dotenv()

# Streamlit UI setup
st.set_page_config(
    page_title="Mental Health PDF Chatbot",
    page_icon="🧠",
    layout="wide"
)
st.title("🧠 Mental Health PDF Chatbot")
st.write("Ask questions about the mental health research!")

# Display PDF status
# if not os.path.exists("pdfs/") or not any(f.endswith('.pdf') for f in os.listdir("pdfs/") if os.path.isfile(os.path.join("pdfs/", f))):
#     st.warning("⚠️ No PDF files found. Please add PDF files to the 'pdfs/' directory to start asking questions.")

# --- OpenAI API Key Handling ---
if "OPENAI_API_KEY" not in st.session_state:
    st.session_state.OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

if not st.session_state.OPENAI_API_KEY:
    st.sidebar.warning("Please enter your OpenAI API key to use the chatbot.")
    api_key_input = st.sidebar.text_input(
        "OpenAI API Key",
        type="password",
        placeholder="sk-...",
        help="Get your key at [https://platform.openai.com/account/api-keys](https://platform.openai.com/account/api-keys)",
        key="api_key_input"
    )
    if api_key_input:
        st.session_state.OPENAI_API_KEY = api_key_input
        os.environ["OPENAI_API_KEY"] = api_key_input
        st.experimental_rerun()
else:
    os.environ["OPENAI_API_KEY"] = st.session_state.OPENAI_API_KEY

# Initialize OpenAI chat model
llm = ChatOpenAI(model="gpt-4", temperature=0.5)

# Define state for application
class State(BaseModel):
    question: str
    context: List[Document]
    answer: str

    class Config:
        arbitrary_types_allowed = True


def load_chunk_pdfs(pdf_path):
    if not os.path.exists(pdf_path):
        os.makedirs(pdf_path)
        st.error(f"No PDF directory found. Created {pdf_path} directory. Please add PDF files to this directory.")
        return []
        
    loader = GenericLoader(
        blob_loader=FileSystemBlobLoader(
            path=pdf_path,
            glob="*.pdf",
        ),
        blob_parser=PyPDFParser(),
    )
    docs = loader.load()
    
    if not docs:
        st.error(f"No PDF files found in {pdf_path}. Please add PDF files to continue.")
        return []
        
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)
    return splits

# Load and chunk the PDFs
all_splits = load_chunk_pdfs("pdfDatabase/")

# Initialize vector store only if we have documents
if all_splits:
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
    vector_store = Chroma.from_documents(
        all_splits,
        embedding=embeddings,
        persist_directory="./mentalhealthdata",
        collection_name="mentalhealthdata")



graph_builder = StateGraph(MessagesState)



@tool(response_format="content_and_artifact")
def retrieve(query: str):
    """Retrieve information related to a query."""
    if not all_splits:
        return "No documents available. Please add PDF files to the pdfs/ directory.", []
        
    retrieved_docs = vector_store.similarity_search(query, k=2)
    serialized = "\n\n".join(
        (f"Source: {doc.metadata}\n" f"Content: {doc.page_content}")
        for doc in retrieved_docs
    )
    return serialized, retrieved_docs



# Step 1: Generate an AIMessage that may include a tool-call to be sent.
def query_or_respond(state: MessagesState):
    """Generate tool call for retrieval or respond."""
    llm_with_tools = llm.bind_tools([retrieve])
    response = llm_with_tools.invoke(state["messages"])
    # MessagesState appends messages to state instead of overwriting
    return {"messages": [response]}


# Step 2: Execute the retrieval.
tools = ToolNode([retrieve])

# Step 3: Generate a response using the retrieved content.
def generate(state: MessagesState):
    """Generate answer."""
    # Get generated ToolMessages
    recent_tool_messages = []
    for message in reversed(state["messages"]):
        if message.type == "tool":
            recent_tool_messages.append(message)
        else:
            break
    tool_messages = recent_tool_messages[::-1]

    # Format into prompt
    docs_content = "\n\n".join(doc.content for doc in tool_messages)
    system_message_content = (
        "You are an assistant for question-answering tasks. "
        "Use the following pieces of retrieved context to answer "
        "the question. If you don't know the answer, say that you "
        "don't know. Use three sentences maximum and keep the "
        "answer concise."
        "\n\n"
        f"{docs_content}"
    )
    conversation_messages = [
        message
        for message in state["messages"]
        if message.type in ("human", "system")
        or (message.type == "ai" and not message.tool_calls)
    ]
    prompt = [SystemMessage(system_message_content)] + conversation_messages

    # Run
    response = llm.invoke(prompt)
    return {"messages": [response]}



graph_builder.add_node(query_or_respond)
graph_builder.add_node(tools)
graph_builder.add_node(generate)

graph_builder.set_entry_point("query_or_respond")
graph_builder.add_conditional_edges(
    "query_or_respond",
    tools_condition,
    {END: END, "tools": "tools"},
)
graph_builder.add_edge("tools", "generate")
graph_builder.add_edge("generate", END)

graph = graph_builder.compile()


# --- Streamlit Chat UI ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Display chat history
for i, (user_msg, ai_msg) in enumerate(st.session_state.chat_history):
    with st.chat_message("user"):
        st.write(user_msg)
    with st.chat_message("assistant"):
        st.write(ai_msg)

user_question = st.chat_input("Ask a question about the PDF...")
if user_question:
    with st.chat_message("user"):
        st.write(user_question)
    with st.chat_message("assistant"):
        with st.spinner("Researching..."):
            state = {"messages": [{"role": "user", "content": user_question}]}
            answer = None
            try:
                # Only display the final AI response (not tool or system messages)
                for step in graph.stream(state, stream_mode="values"):
                    # Find the last message that is an AI response (not a tool/tool_call)
                    ai_responses = [
                        msg for msg in step["messages"]
                        if getattr(msg, "type", None) == "ai" and not getattr(msg, "tool_calls", None)
                    ]
                    if ai_responses:
                        answer = ai_responses[-1].content
                if answer:
                    st.write(answer)
                else:
                    st.write("[No answer found]")
            except Exception as e:
                error_msg = f"Error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
                st.error(error_msg)
                print(error_msg)  # Also print to console for debugging
            st.session_state.chat_history.append((user_question, answer if answer else "[No answer]"))