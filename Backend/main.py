from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import sys
sys.path.append("C:\\Users\\panka\\genai_project\\tailor_resume")

from workflow.main import run_workflow
import uvicorn
app=FastAPI()

origins = [
    "http://localhost",
    "http://127.0.0.1:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      
    allow_credentials=True,
    allow_methods=["*"],      
    allow_headers=["*"],      
    )

class inp_data(BaseModel):
    job_description:str
    resume_path:str
    
@app.post("/tailor_resume")
async def tailor_resume(inp:inp_data):
    inp = {"org_resume_path": inp.resume_path, "max_tool_calls_for_rewritting_resume": 5, "jd": inp.job_description}
    try :
        res=await run_workflow(inp)
        # for changing default address of resume edit it in MCP
        if res['status']=="sucess":
            return JSONResponse(status_code=200,content=res)
        return JSONResponse(status_code=500,content=res)
    # this try except is not required as run_workflow handles errors
    except Exception as E:
        print(E)
        return JSONResponse(status_code=500,content={"res":"an error occured","status":"failed"})
    
if __name__=="__main__":
    uvicorn.run(app)