from dotenv import load_dotenv
import os
import gradio as gr
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from assignment_chat.prompts import return_instructions
from assignment_chat.guardrails import check_input, check_output
from assignment_chat.tools_din import (
    search_marketed_products,
    get_product_by_din,
    export_marketed_products_csv,
)
from assignment_chat.tools_search import semantic_product_search, find_similar_by_atc

load_dotenv(".env")
load_dotenv(".secrets")
os.environ["LANGSMITH_TRACING"] = "false"

llm = init_chat_model(
    "openai:gpt-4o-mini",
    base_url="https://k7uffyg03f.execute-api.us-east-1.amazonaws.com/prod/openai/v1",
    api_key="any value",
    default_headers={"x-api-key": os.getenv("API_GATEWAY_KEY")},
)

# The tools DINgs can use
tools = [
    search_marketed_products,       # Service 1: Health Canada API (ingredient -> marketed products)
    get_product_by_din,             # Service 1: Health Canada API (DIN -> product details)
    semantic_product_search,        # Service 2: semantic search in ChromaDB
    find_similar_by_atc,            # ATC similarity search with pandas
    export_marketed_products_csv,   # Service 3: function calling -> downloadable CSV
]
tools_by_name = {t.name: t for t in tools}   # lets us find a tool by its name
llm_with_tools = llm.bind_tools(tools)       # tells the AI these tools exist


def to_text(content) -> str:
    """Chat history can contain text or files. Keep only the text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):   # e.g. [{"type": "text", "text": "..."}]
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""                       # a file or image: nothing to send to the AI


def dings_chat(message, history):
    # 0. Guardrail layer 1: block restricted topics / prompt attacks BEFORE calling the AI
    refusal = check_input(message)
    if refusal:
        return refusal

    # 1. Start with the personality
    messages = [SystemMessage(content=return_instructions())]

    # 2. Add the conversation so far (memory). Files in the history are skipped.
    for msg in history:
        text = to_text(msg["content"])
        if not text:
            continue
        if msg["role"] == "user":
            messages.append(HumanMessage(content=text))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=text))

    # 3. Add the new message
    messages.append(HumanMessage(content=message))

    # 4. Ask the AI. It either answers, or asks to use a tool.
    response = llm_with_tools.invoke(messages)

    # 5. As long as the AI asks for tools: run them and send back the results
    files_to_send = []
    while response.tool_calls:
        messages.append(response)                       # the AI's tool request
        for call in response.tool_calls:
            tool = tools_by_name[call["name"]]          # find the tool it asked for
            result = tool.invoke(call["args"])          # run it
            if isinstance(result, dict) and "file_path" in result:
                files_to_send.append(result["file_path"])   # remember the CSV to attach
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
        response = llm_with_tools.invoke(messages)      # ask again, now with the results

    # 6. Guardrail layer 3: check the answer AFTER the AI wrote it
    answer = check_output(response.content, return_instructions())

    # 7. Final answer, plus any CSV files as downloads
    if files_to_send:
        return [answer] + [gr.File(path) for path in files_to_send]
    return answer


chat = gr.ChatInterface(fn=dings_chat, title="DINgs 🔔")
chat.launch()
