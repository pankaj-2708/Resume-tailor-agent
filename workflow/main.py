from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import ToolNode
from langchain_ollama import ChatOllama
import asyncio
from typing import Annotated, TypedDict, Optional, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_core.output_parsers import PydanticOutputParser
from langgraph.graph.message import add_messages
from langchain_mcp_adapters.client import MultiServerMCPClient
import json
load_dotenv()


async def load_tools():
    servers = {
        "python_tools": {
            "transport": "stdio",
            "command": "uv",
            "args": [
                "run",
                "fastmcp",
                "run",
                "C:\\Users\\panka\\genai_project\\tailor_resume\\MCP\\main.py",
            ],
        }
    }

    client = MultiServerMCPClient(servers)
    tools = await client.get_tools()
    return tools


tools = asyncio.run(load_tools())
latex_reader_tool = [i for i in tools if i.name == "latex_reader_tool"][0]
latex_writer_tool = [i for i in tools if i.name == "latex_compiler_and_document_saver"][
    0
]

jd_parser_llm = ChatOllama(model="gemma4:31b-cloud")
resume_tailor_model = ChatOllama(model="gemma4:31b-cloud").bind_tools(
    [latex_writer_tool]
)
optimiser_llm = ChatOllama(model="gemma4:31b-cloud")
optimiser_llm = ChatOllama(model="gemma4:31b-cloud")


class schema(TypedDict):
    resume_latex: str
    org_resume_path: str
    is_change_required: bool
    changes_required: str
    jd: str
    parsed_jd: str
    messages: Annotated[List[BaseMessage], add_messages]
    resume_updated: bool
    max_tool_calls_for_rewritting_resume: int


class jd_summary_schema(BaseModel):
    parsed_jd: str = Field(..., description="Parsed jd")


jd_parser_node_parser = PydanticOutputParser(pydantic_object=jd_summary_schema)


async def jd_parser_node(state: schema):
    sys_prompt = f"""
    You are an expert JD (Job Description) analyst specializing in resume tailoring.
    The user will provide a job description. Your task is to carefully read it and extract ONLY the information that is directly useful for tailoring a resume to this role.

    Output a plain text summary with clearly labeled sections in this exact order:

    JOB TITLE & SENIORITY:
    State the role title and seniority level (e.g. Junior, Mid, Senior, Lead).

    ROLE SUMMARY:
    2-3 sentences capturing what this role is fundamentally about and what kind of candidate they are looking for.

    REQUIRED SKILLS & TECH STACK:
    List every hard skill, tool, language, framework, or technology explicitly marked as required or essential. One item per line.

    PREFERRED / NICE-TO-HAVE SKILLS:
    List skills mentioned as preferred, bonus, or a plus. One item per line. Write "None mentioned" if absent.

    KEY RESPONSIBILITIES:
    List the core responsibilities in bullet points. Focus on action-oriented items that a resume bullet point could directly mirror.

    EXPERIENCE & EDUCATION REQUIREMENTS:
    State years of experience required and any education requirements explicitly mentioned.

    IMPORTANT NOTES:
    Any other detail that would influence how the resume should be tailored — e.g. domain knowledge required, specific industry experience, certifications, or cultural/work style signals.

    Rules:
    - Extract only what is explicitly stated or strongly implied in the JD. Do not infer or hallucinate details.
    - If a section has no relevant information, write "Not mentioned" — do not skip the section.
    - Do not add commentary, greetings, or explanations. Output only the labeled sections \n Output format - {jd_parser_node_parser.get_format_instructions()}
    """

    human_prompt = f"JD - {state['jd']}"

    res = await jd_parser_llm.ainvoke(
        [SystemMessage(content=sys_prompt), HumanMessage(content=human_prompt)]
    )
    res = await jd_parser_node_parser.ainvoke(res)

    return {"parsed_jd": res.parsed_jd}


class ResumeReadingException(Exception):
    def __init__(self, err):
        super().__init__(f"Error occured in reading resume - {err}")
        
async def resume_reader_node(state: schema):
    x = await latex_reader_tool.ainvoke(input={"path":state["org_resume_path"]})
    
    x= json.loads(x[0]['text'])
    if x['status']!='sucess':
        raise ResumeReadingException(x['error'])
    return {"resume_latex": x['latex']}


class schema_for_optimiser_node(BaseModel):
    is_change_required: bool = Field(
        ..., description="True if changes required false otherwise"
    )
    changes_required: Optional[str] = Field(
        default="", description="All changes required in bullet points"
    )


parser_for_optimiser_node = PydanticOutputParser(
    pydantic_object=schema_for_optimiser_node
)


async def optimiser_node(state: schema):
    sys_prompt = f"""
    You are an expert resume optimiser specialising in tailoring LaTeX resumes to job descriptions.

    You will receive two inputs:
    1. JD ANALYSIS — a structured summary of the job description extracted by a JD parser
    2. LATEX RESUME — the candidate's current resume in raw LaTeX format

    Your task is to return changes that are required in resume to optimise it for job description.
    
    Note - Return all of the changes required as clear instructions in bullet points.
    - If no changes required return is_change_required as False
    Output Format - {parser_for_optimiser_node.get_format_instructions()}
    """

    human_prompt = f"""JD ANALYSIS - {state['parsed_jd']} \n\n\n Latex Reume - {state['resume_latex']}"""

    res = await optimiser_llm.ainvoke([sys_prompt, human_prompt])
    res = await parser_for_optimiser_node.ainvoke(res.content)

    return {
        "changes_required": res.changes_required,
        "is_change_required": res.is_change_required,
    }


async def tailor_resume_node(state: schema):
    sys_prompt = f"""
    You are resume tailorer .
    
    You will receive two inputs:
    1. Required changes : in bullet points.
    2. LATEX RESUME — the candidate's current resume in raw LaTeX format.
    3. update resume path — path where updates resume should be saved.
    
    Your task is to update as per required changes and use tools to run and save the updated latex at the given path.
    
    """

    if state["max_tool_calls_for_rewritting_resume"] == 0:
        return {"resume_updated": False}

    inp = []
    if len(state["messages"]) == 0:
        human_prompt = f"Resume - {state['resume_latex']} \n\n jd - {state['jd']}"
        inp = [SystemMessage(content=sys_prompt), HumanMessage(content=human_prompt)]
    else:
        inp = state["messages"]

    res = await resume_tailor_model.ainvoke(inp)
    return {
        "messages": [res],
        "max_tool_calls_for_rewritting_resume": state[
            "max_tool_calls_for_rewritting_resume"
        ]
        - 1,
    }


def tailor_condn(state: schema):
    return state["is_change_required"]

def tool_call_condition(state:schema):
    if state['messages'][-1].tool_calls:
        return "tools"
    return END

graph = StateGraph(schema)

graph.add_node("jd_parser_node",jd_parser_node)
graph.add_node("resume_reader_node",resume_reader_node)
graph.add_node("optimiser_node",optimiser_node)
graph.add_node("tailor_resume_node",tailor_resume_node)
graph.add_node("tools",ToolNode([latex_writer_tool]))

graph.add_edge(START, "jd_parser_node")
graph.add_edge(START, "resume_reader_node")
graph.add_edge("resume_reader_node", "optimiser_node")
graph.add_edge("jd_parser_node", "optimiser_node")
graph.add_conditional_edges(
    "optimiser_node", tailor_condn, {True: "tailor_resume_node", False: END}
)
graph.add_conditional_edges("tailor_resume_node",tool_call_condition)   
graph.add_edge("tools",'tailor_resume_node')

workflow = graph.compile()


async def run_workflow(input_dct):
    out = await workflow.ainvoke(input_dct)
    return out


jd="""Job Title: Artificial Intelligence Intern
Company: Infrabyte Consulting
Location: Remote
Employment Type: Full-time Internship
Internship Duration: 1–3 Months
Stipend: ₹15,400 per month


About Infrabyte Consulting
Infrabyte Consulting is a consulting and technology solutions firm focused on applying artificial intelligence, advanced analytics, and automation to solve complex business and operational challenges. We combine strategic consulting frameworks with modern intelligent systems to help organizations improve efficiency, scalability, and innovation. Our internship programs are designed to provide practical exposure to AI implementation, consulting discipline, and real-world problem-solving.


About the Opportunity
Infrabyte Consulting is seeking an Artificial Intelligence Intern for candidates interested in intelligent systems, AI-driven innovation, and practical business applications of emerging technologies. This internship provides structured exposure to AI workflows, experimentation, and consulting-led technical execution in a remote professional environment.


What You’ll Do


* Assist in preparing and structuring datasets for AI applications
* Support experimentation with AI/ML algorithms for business or operational use cases
* Work on feature engineering, model testing, and analytical workflows
* Research practical AI methodologies and emerging intelligent systems
* Evaluate model outputs and support optimization processes
* Collaborate on AI-focused consulting projects requiring strategic problem-solving
* Document methodologies, experiments, and implementation findings
* Explore AI applications in automation, analytics, or operational systems


Who Can Apply


* Students or recent graduates in Artificial Intelligence, Computer Science, Data Science, or related fields
* Candidates passionate about AI systems, automation, and intelligent technologies
* Individuals with strong analytical, technical, and computational thinking abilities
* Applicants comfortable with remote execution and structured project environments


Required Skills


* Strong understanding of Python programming fundamentals
* Basic knowledge of AI and machine learning concepts
* Familiarity with data structures, algorithms, and analytical reasoning
* Understanding of statistics and probability basics
* Problem-solving mindset and technical curiosity
* Ability to document and communicate technical outcomes effectively


Preferred Qualifications


* Familiarity with TensorFlow, PyTorch, scikit-learn, or similar frameworks
* Academic or personal AI/ML projects
* Exposure to deep learning, NLP, or automation concepts
* Interest in consulting-led innovation and intelligent systems


What You’ll Gain


* Hands-on experience in AI implementation within consulting-oriented environments
* Exposure to real-world intelligent systems and business problem-solving
* Mentorship from experienced consulting and technical professionals
* Opportunity to strengthen technical experimentation, research, and strategic execution skills
* Portfolio-building through practical AI assignments
* Internship completion certificate based on performance


Work Environment


* Fully remote internship
* Structured AI and consulting project assignments
* Performance-focused mentorship and innovation-driven learning


Infrabyte Consulting is committed to fostering a professional, inclusive, and growth-oriented environment where future AI professionals can gain meaningful consulting and technical expertise."""
if __name__ == "__main__":
    inp = {"org_resume_path": "C:\\Downloads\\main.tex", "max_tool_calls_for_rewritting_resume": 5, "jd": jd}
    asyncio.run(run_workflow(inp))
