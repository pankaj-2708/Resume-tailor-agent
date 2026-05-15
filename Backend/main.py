from fastapi import FastAPI,BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import sys
import uuid
sys.path.append("C:\\Users\\panka\\genai_project\\tailor_resume")
from workflow.main import run_workflow
import uvicorn
import mysql.connector
import json

cnx = mysql.connector.connect(user='root', password='root',
                              host='127.0.0.1',
                              database='tailor_resume_db')

cursor = cnx.cursor()



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
    
jobs_table="job_status"
    
async def wrapper_for_run_workflow(inp,job_id):
    res=await run_workflow(inp)  
    cursor.execute(f"""Update {jobs_table} set status = %s , response = %s  where id=%s""",('completed',json.dumps(res),job_id))    
    cnx.commit()


@app.post("/create_job")
async def tailor_resume(inp:inp_data,background_tasks: BackgroundTasks):
    try:
        id=str(uuid.uuid4())
        cursor.execute(f"""insert into {jobs_table} (id,status,response) values (%s,%s,%s)""",(id,'running',''))    
        cnx.commit()    
        inp = {"org_resume_path": inp.resume_path, "max_tool_calls_for_rewritting_resume": 5, "jd": inp.job_description}
        background_tasks.add_task(wrapper_for_run_workflow,inp,id)
        return JSONResponse(content={"job_id":id,"status":"running"},status_code=200)
    except Exception as E:
        return JSONResponse(content={"error":str(E)},status_code=500)
        


@app.get("/job_status/{job_id}")
async def job_status(job_id:str):
    try:
        cursor.execute(f"""Select * from {jobs_table} where id= %s """,(job_id,))
        res=cursor.fetchone()
        # print(res)
        if res and res[0]=='running':
            return JSONResponse(content={"status":"running"},status_code=200)
        else:
            x={}
            x['status']=res[1]
            if res[2]!='':
                x['response']=json.loads(res[2])

            return JSONResponse(content=x,status_code=200)
    except Exception as E:
        return JSONResponse(content={"error":str(E)},status_code=500)
    
    
@app.get("/fetch_running_jobs/")
async def fetch_all_running_jobs():
    try:
        cursor.execute(f"""Select * from {jobs_table} where status= 'running'""")
        res=cursor.fetchall()
        ids=[]
        for i in res:
            ids.append(i[0])
        return JSONResponse(content={"running_ids":ids},status_code=200)
    except Exception as E:    
        return JSONResponse(content={"error":str(E)},status_code=500)
    
    
if __name__=="__main__":
    uvicorn.run(app="main:app",reload=True)