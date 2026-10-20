import os
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from dotenv import load_dotenv

load_dotenv()

llm = ChatOpenAI(base_url='https://openrouter.ai/api/v1',model="gpt-4o-mini")


# --- 1. TOOLS ---
@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    resp = llm.invoke(f"Search the web for :\n{query}")
    return resp.content


@tool
def write_code(task: str) -> str:
    """Write Python code for a given task."""
    resp = llm.invoke(f"Write clean Python code to do this and return only code:\n{task}")
    return resp.content

@tool
def analyze_code(code: str) -> str:
    """Analyze code and return key insights."""
    resp = llm.invoke(f"Analyze the code and mention the objective, dependencies,business logic(if any):\n{code}")
    return resp.content
	
from langchain_core.messages import BaseMessage
from typing import TypedDict, Annotated
import operator


# --- 2. STATE ---
class State(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    next_agent: str
	
from langgraph.prebuilt import ToolNode 
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage


# --- 3. WORKER FACTORY ---
def make_worker(prompt: str, worker_tools: list):
    wllm = ChatOpenAI(api_key=os.getenv('OPENAI_API_KEY'),model="gpt-4o-mini",openai_api_base="https://openrouter.ai/api/v1").bind_tools(worker_tools)
    tnode = ToolNode(worker_tools)

    def worker(state: State) -> dict:
        print(f"[worker] {prompt}...")
        resp = wllm.invoke([SystemMessage(prompt)] + state["messages"])
        if resp.tool_calls:
            tool_resp = tnode.invoke({"messages": [resp]})
            print("****************")
            print(f"[worker] {tool_resp}")
            print("****************")
            return {"messages": [resp] + tool_resp["messages"]}
        return {"messages": [resp]}

    return worker


researcher = make_worker("You are a web research specialist. Use search_web.", [search_web])
coder = make_worker("You are a coding specialist. Use write_code.", [write_code])
analyst = make_worker("You are a data analyst. Use analyze_data.", [analyze_code])

from langgraph.graph import END
from typing import Literal

# --- 4. SUPERVISOR ---
VALID_AGENTS = {"researcher", "coder", "analyst", "finish"}


def supervisor_node(state: State) -> dict:
    sys = SystemMessage(
        "You are a supervisor managing three agents: researcher, coder, analyst.\n"
        "Based on the conversation, decide who should act next.\n"
        "Reply with ONLY one word — no punctuation, no explanation:\n"
        "  researcher  →  to search for information\n"
        "  coder       →  to write code\n"
        "  analyst     →  to analyze code\n"
        "  FINISH      →  when the task is complete\n"
        "Your entire response must be a single word from the list above."
    )
    resp = llm.invoke([sys] + state["messages"])

    # Parse: take only the first word and lowercase it
    raw = resp.content.strip().lower()
    decision = raw.split()[0].strip("*_.,!") if raw else "finish"

    # Fallback: if still not a valid option, default to FINISH
    if decision not in VALID_AGENTS:
        print(f"[supervisor] ⚠️  Unexpected response: {raw!r} → defaulting to FINISH")
        decision = "finish"

    print(f"[supervisor] → {decision}")
    return {"next_agent": decision, "messages": [resp]}


def route(state: State) -> Literal["researcher", "coder", "analyst", "__end__"]:
    return END if state["next_agent"] == "finish" else state["next_agent"]
	
	
from langgraph.graph import StateGraph, START, END

# --- 5. GRAPH ---
builder = StateGraph(State)
builder.add_node("supervisor", supervisor_node)
builder.add_node("researcher", researcher)
builder.add_node("coder", coder)
builder.add_node("analyst", analyst)
builder.add_edge(START, "supervisor")
builder.add_conditional_edges(
    "supervisor",
    route,
    {
        "researcher": "researcher",
        "coder": "coder",
        "analyst": "analyst",
        END: END,
    },
)
for w in ["researcher", "coder", "analyst"]:
    builder.add_edge(w, "supervisor")
graph = builder.compile()

# --- 6. VISUALIZE ---
from langchain_core.runnables.graph_mermaid import MermaidDrawMethod
# 1. Get the Mermaid structural layout text from the graph
mermaid_text = graph.get_graph().draw_mermaid()

# 2. Wrap it cleanly in Markdown code blocks
markdown_content = f"""# LangGraph Agent Visualization

```mermaid
{mermaid_text}
```
"""

# 3. Save it to a markdown file in your workspace
with open("graph.md", "w", encoding="utf-8") as f:
    f.write(markdown_content)

print("🎉 Success! Open 'graph.md' and press Ctrl+Shift+V to see your diagram.")



from langchain_core.messages import HumanMessage
from pprint import pprint

# --- 7. RUN ---
result = graph.invoke(
    {
        "messages": [HumanMessage("Write code to invert a string")],
        "next_agent": "",
    }
)
print("\n✅")
pprint(result["messages"])