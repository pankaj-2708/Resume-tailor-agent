from langgraph.graph import START,END,StateGraph
from langchain_ollama import ChatOllama
import asyncio
from typing import Annotated,TypedDict,Optional,List
from pydantic import BaseModel,Field
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage,SystemMessage,BaseMessage
from langchain_core.output_parsers import PydanticOutputParser
from langgraph.graph.message import add_messages


load_dotenv()

jd_parser_llm=ChatOllama("gemma4:31b-cloud")
resume_tailor_model=ChatOllama("gemma4:31b-cloud")
optimiser_llm=ChatOllama("gemma4:31b-cloud")
optimiser_llm=ChatOllama("gemma4:31b-cloud")

class schema(TypedDict):
    resume_latex:str
    org_resume_path:str
    is_change_required:bool
    changes_required:str
    jd:str
    parsed_jd:str
    messages:Annotated[List[BaseMessage],add_messages]
    resume_updated:bool    
    max_tool_calls_for_rewritting_resume:int

class jd_summary_schema(BaseModel):
    parsed_jd:str=Field(...,description="Parsed jd")
    
jd_parser_node_parser=PydanticOutputParser(pydantic_object=jd_summary_schema)
        
async def jd_parser_node(state:schema):
    sys_prompt=f"""
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
    
    human_prompt=f"JD - {state['jd']}"
    
    res=await jd_parser_llm.ainvoke([SystemMessage(content=sys_prompt),HumanMessage(content=human_prompt)])
    res=await jd_parser_node_parser.ainvoke(res)
    
    return {"parsed_jd":res.parsed_jd}
    
    


async def resume_reader_node(state:schema):
    x=await resume_reader_tool.ainvoke(resume_path=state['resume_latex']).content
    return {"resume_latex":x}


class schema_for_optimiser_node(BaseModel):
    is_change_required:bool=Field(...,description="True if changes required false otherwise")
    changes_required:Optional[str]=Field(default="",description="All changes required in bullet points")
    
parser_for_optimiser_node=PydanticOutputParser(pydantic_object=schema_for_optimiser_node)    

async def optimiser_node(state:schema):
    sys_prompt=f"""
    You are an expert resume optimiser specialising in tailoring LaTeX resumes to job descriptions.

    You will receive two inputs:
    1. JD ANALYSIS — a structured summary of the job description extracted by a JD parser
    2. LATEX RESUME — the candidate's current resume in raw LaTeX format

    Your task is to return changes that are required in resume to optimise it for job description.
    
    Note - Return all of the changes required as clear instructions in bullet points.
    - If no changes required return is_change_required as False
    Output Format - {parser_for_optimiser_node.get_format_instructions()}
    """
    
    human_prompt=f"""JD ANALYSIS - {state['parsed_jd']} \n\n\n Latex Reume - {state['resume_latex']}"""
    
    res= await optimiser_llm.ainvoke([sys_prompt,human_prompt]).res
    res=await parser_for_optimiser_node.ainvoke(res)
    
    return {"changes_required":res.changes_required,"is_change_required":res.is_change_required}


async def tailor_resume_node(state:schema):
    sys_prompt=f"""
    You are resume tailorer .
    
    You will receive two inputs:
    1. Required changes : in bullet points.
    2. LATEX RESUME — the candidate's current resume in raw LaTeX format.
    3. update resume path — path where updates resume should be saved.
    
    Your task is to update as per required changes and use tools to run and save the updated latex at the given path.
    
    """
    
    if state['max_tool_calls_for_rewritting_resume']==0:
        return {"resume_updated":False}
    
    inp=[]
    if len(state['messages'])==0:
        human_prompt=f"Resume - {state['resume_latex']} \n\n jd - {state['jd']}"
        inp=[SystemMessage(content=sys_prompt),HumanMessage(content=human_prompt)]
    else:
        inp=state['messages']
        
    res=await resume_tailor_model.ainvoke(inp).content
    return {"messages":[res],"max_tool_calls_for_rewritting_resume":state['max_tool_calls_for_rewritting_resume']-1}
    
    
def tailor_condn(state:schema):
    return state['is_change_required']
    
graph=StateGraph(schema)

graph.add_node("jd_parser_node")
graph.add_node("resume_reader_node")
graph.add_node("optimiser_node")
graph.add_node("tailor_resume_node")

graph.add_edge(START,"jd_parser_node")
graph.add_edge(START,"resume_reader_node")
graph.add_edge("resume_reader_node","optimiser_node")
graph.add_edge("jd_parser_node","optimiser_node")
graph.add_conditional_edges("optimiser_node",tailor_condn,{True:"tailor_resume_node",False:END})
graph.add_edge("tailor_resume_node",END)

workflow=graph.compile()

async def run_workflow(input_dct):
    out=workflow.ainvoke(input_dct)
    return out

if __name__=="__main__":
    inp={
        "org_resume_path":"",
        "max_tool_calls_for_rewritting_resume":5,
        "jd":""
        
    }
    asyncio.run(run_workflow(inp))
    
