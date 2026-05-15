import warnings
warnings.filterwarnings(action='ignore')

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
scorer_llm = ChatOllama(model="gemma4:31b-cloud")



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
    org_resume_score:int
    resume_score:int
    new_resume_name:str


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

class schema_for_scorer_node(BaseModel):
    score:int
    
parser_for_scorer_node=PydanticOutputParser(pydantic_object=schema_for_scorer_node)

async def scorer_node(state:schema):
    sys_prompt=f"""You are a Resume Scoring engine. Your sole job is to score how well a resume matches a given Job Description (JD).

You will receive:
- A resume in raw LaTeX (.tex) format
- A Job Description (JD) in plain text

LaTeX Parsing Instructions:
- Extract and evaluate only the actual content — ignore all LaTeX commands, macros, and formatting syntax (e.g., \\textbf, \\begin, \\itemize, etc.)
- Treat \\item entries as bullet points
- Sections are typically defined by \\section or \\subsection — use these to identify Experience, Skills, Education, Projects, etc.

Score the resume on a scale of 1–100, representing the likelihood of it being SHORTLISTED by a real recruiter or ATS system.

Scoring Weights:
- Skills & tools match: 35%
- Work experience relevance & seniority fit: 30%
- Quantified achievements & impact: 20%
- Education & certifications: 15%

Be strict. A score above 90 means strong fit.

Output Format - 
{parser_for_scorer_node.get_format_instructions()}
"""
    human_prompt=f"Job description - {state['parsed_jd']} \n Resume - {state['resume_latex']}"
    
    res=await scorer_llm.ainvoke([sys_prompt,human_prompt])
    res=await parser_for_scorer_node.ainvoke(res.content)
    
    return {'resume_score':res.score}
    

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
    sys_prompt=f"""
You are an expert resume optimiser specialising in tailoring LaTeX resumes to job descriptions and improving ATS compatibility.

You will receive two inputs:
1. JD ANALYSIS — a structured summary of the job description extracted by a JD parser
2. LATEX RESUME — the candidate's current resume in raw LaTeX format
3. New resume name - new resume should be saved by this name

Your task is to analyse the resume against the JD and suggest ONLY modifications that would improve:
- ATS (Applicant Tracking System) compatibility
- Keyword alignment with the JD
- Recruiter readability and relevance
- Selection chances for the role

Important Instructions:
- DO NOT create, invent, exaggerate, or hallucinate any new experience, projects, skills, metrics, achievements, certifications, responsibilities, or details.
- DO NOT assume information that is not already present in the resume.
- ONLY suggest:
  - rewording existing content
  - restructuring sections
  - improving keyword usage
  - changing formatting/order
  - removing weak or irrelevant content
  - highlighting already existing relevant experience
  - ATS-friendly improvements
- If a required skill or experience is missing from the resume, mention it as a missing gap instead of generating content for it.
- Keep suggestions realistic and strictly grounded in the provided resume content.

Output Requirements:
- Return all suggested changes as clear actionable bullet points.
- Each point should explain WHAT to change .
- If no meaningful optimisation is required, return:
  is_change_required = False

Output Format:
{parser_for_optimiser_node.get_format_instructions()}
"""

    human_prompt = f"""JD ANALYSIS - {state['parsed_jd']} \n\n\n Latex Reume - {state['resume_latex']} \n\n New resume name - {state['new_resume_name']}"""

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
    
    Your task is to update as per required changes and use tools to run and save the updated latex at the given path.
    
    """

    if state["max_tool_calls_for_rewritting_resume"] == 0:
        return {"resume_updated": False}

    inp = []
    if len(state["messages"]) == 0:
        human_prompt = f"Resume - {state['resume_latex']} \n\n Job Description - {state['jd']}"
        inp = [SystemMessage(content=sys_prompt), HumanMessage(content=human_prompt)]
    else:
        inp = state["messages"]

    res = await resume_tailor_model.ainvoke(inp)
    return {
        "messages": [res],
        "max_tool_calls_for_rewritting_resume": state[
            "max_tool_calls_for_rewritting_resume"
        ] - 1,
        'resume_updated':True
    }

def update_params_node(state:schema):
    return {'org_resume_path':'C:\\Downloads\\resume.tex','org_resume_score':state['resume_score']}

def tailor_condn(state: schema):
    return state["is_change_required"]

def tool_call_condition(state:schema):
    if state['messages'][-1].tool_calls and state['resume_updated']:
        return "tools"
    elif not state['resume_updated']:
        return "end"
    
    return 'next'

def score_update_resume_cond(state:schema):
    return state['resume_updated']

graph = StateGraph(schema)

graph.add_node("jd_parser_node",jd_parser_node)
graph.add_node("resume_reader_node",resume_reader_node)
graph.add_node("resume_reader_node2",resume_reader_node)
graph.add_node("optimiser_node",optimiser_node)
graph.add_node("tailor_resume_node",tailor_resume_node)
graph.add_node("scorer_node",scorer_node)
graph.add_node("scorer_node2",scorer_node)
graph.add_node("update_params_node",update_params_node)
graph.add_node("tools",ToolNode([latex_writer_tool]))

graph.add_edge(START, "jd_parser_node")
graph.add_edge(START, "resume_reader_node")
graph.add_edge("resume_reader_node", "scorer_node")
graph.add_edge("scorer_node", "optimiser_node")
graph.add_edge("jd_parser_node", "optimiser_node")
graph.add_conditional_edges(
    "optimiser_node", tailor_condn, {True: "tailor_resume_node", False: END}
)
graph.add_conditional_edges("tailor_resume_node",tool_call_condition,{"tools":"tools","end":END,'next':'update_params_node'})   
graph.add_edge("tools",'tailor_resume_node')
graph.add_edge('update_params_node','resume_reader_node2')
graph.add_edge('resume_reader_node2','scorer_node2')
graph.add_edge('scorer_node2',END)


workflow = graph.compile()
png_bytes = workflow.get_graph().draw_mermaid_png()

# Save the bytes to a local file
with open("langgraph_workflow.png", "wb") as f:
    f.write(png_bytes)

async def run_workflow(input_dct):
    # out = await workflow.ainvoke(input_dct)
    try:
        completed_node=''
        last_state=None
        async for chunk in workflow.astream(input_dct,stream_mode=["updates",'values']):
            mode, data = chunk
            if mode == "updates":
                completed_node = list(data.keys())[0]
            elif mode == "values":
                last_state = data 
        
        if completed_node=='optimiser_node':
            return {"status":"sucess",'message':'No update required','org_resume_score':last_state['resume_score']}

        # if last_state['resume_updated']==False:
        #     return {"status":"failed","message":"Update failed after fix latex code max iternation time"}
        
        return {"status":"sucess","message":"updated resume is present at given directory with name resume.pdf","org_resume_score":last_state['org_resume_score'],'updated_resume_score':last_state['resume_score']}
        
    except Exception as E:
        return {"status":"failed","error":str(E),"last_completed_node":completed_node}


jd="""Role: Applied AI Research Engineer — Multimodal & Vision-Language Models
Company: AI Research Lab / Enterprise AI Team
Location: Bangalore / Hybrid
Experience: 1–3 years

About the Role
We are an applied research team working at the intersection of computer vision, NLP, and multimodal AI. We build and evaluate large vision-language models (VLMs), run rigorous ablations, and translate research into production systems. We need someone who bridges research and engineering.

Key Responsibilities
• Train and fine-tune Vision-Language Models (CLIP, LLaVA, Florence) on custom datasets
• Design evaluation frameworks: BLEU, ROUGE, CIDEr, and custom task-specific metrics
• Run systematic ablation studies on model architecture, prompting, and data quality
• Build multimodal RAG pipelines combining image embeddings and text retrieval
• Write clean, reproducible research code with proper experiment tracking
• Contribute to internal research reports and collaborate with senior researchers

Required Skills
• Strong background in both Computer Vision and NLP
• Experience fine-tuning large models; familiarity with PEFT methods
• Proficiency in PyTorch; experience reading and implementing research papers
• Strong understanding of evaluation metrics (ROUGE, BLEU, perplexity, etc.)
• Solid mathematical foundations: linear algebra, probability, and optimisation

Preferred / Good to Have
• Experience with VLMs or multimodal architectures (CLIP, BLIP, LLaVA, etc.)
• Familiarity with contrastive learning or diffusion models
• Publications or significant open-source contributions
• Experience with large-scale distributed training (DDP, FSDP)

Where You Need to Tailor / Upskill
• VLMs / multimodal architectures — your CV shows CV and NLP separately, not combined; highlight any cross-modal work or study CLIP/LLaVA before applying
• Research paper implementation — demonstrate this via GitHub; your projects are strong but more engineering-focused than research-focused
• Distributed training — add a note if you have any experience, even single-node multi-GPU
• Contrastive or generative vision models — your AdaIN neural style project is adjacent; frame it as generative vision research
• Consider adding a multimodal mini-project (image + text RAG, image captioning) to bridge the gap

Compensation
• CTC: ₹12–20 LPA depending on research output and experience
• Access to on-premise GPU cluster
• Conference sponsorship (NeurIPS, CVPR, ACL)."""
if __name__ == "__main__":
    inp = {"org_resume_path": "C:\\Downloads\\main.tex", "max_tool_calls_for_rewritting_resume": 5, "jd": jd,"new_resume_name":"new_resume"}
    x=asyncio.run(run_workflow(inp))
    print(x)