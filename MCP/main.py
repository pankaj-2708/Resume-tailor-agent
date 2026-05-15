from fastmcp import FastMCP
import subprocess
import os

mcp = FastMCP()


resume_directory = "C:\\Downloads"


@mcp.tool()
def latex_reader_tool(path: str):
    "This is a latex reader tool . Provide it a .tex file and it will return latex of the given file"
    try:
        with open(path) as f:
            x = f.read()
        return {"status": "sucess", "latex": x}
    except Exception as E:
        return {"status": "failed", "error": str(E)}


@mcp.tool()
def latex_compiler_and_document_saver(latex: str,new_resume_name:str):
    """This tool compile the given latex code and save it as a pdf
        New resume name should be a string without .pdf and without any directory address
    """

    try:
        if '.pdf' == new_resume_name[-4:]:
            new_resume_name=new_resume_name[:-4]
        tex_path = os.path.join(resume_directory, f"{new_resume_name}.tex")
        with open(tex_path, "w") as f:
            f.write(latex)
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "resume.tex"],
            capture_output=True,
            text=True,
            cwd=resume_directory,
        )

        if result.returncode == 0:
            return {"status": "sucess"}

        return {"status": "failed", "error": result.stderr}
    except Exception as E:
        return {"status": "failed", "error": str(E)}


if __name__ == "__main__":
    mcp.run()

# command for testing - npx @modelcontextprotocol/inspector uv run MCP/main.py
