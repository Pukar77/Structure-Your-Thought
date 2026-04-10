from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from database import get_connection_string
import os
import requests
from dotenv import load_dotenv
import json
import base64
import tempfile
import zipfile
import uuid

load_dotenv()
app = FastAPI()

HF_TOKEN = os.getenv("HF_TOKEN")
API_URL = "https://router.huggingface.co/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}

def query(payload):
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"HuggingFace request failed: {str(e)}")

    # Try to parse JSON even on non-200 responses
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(status_code=502, detail=f"Non-JSON response from HuggingFace: {response.text}")

    # If HF returns an error, surface it (prevents KeyError on 'choices')
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail={"hf_status": response.status_code, "hf_response": data})

    # Unexpected shape (also prevents KeyError)
    if "choices" not in data:
        raise HTTPException(status_code=502, detail={"hf_status": response.status_code, "hf_response": data})

    return data

def get_database_schema(project_id):
    conn = get_connection_string()
    cursor = conn.cursor()
    select_query = """
        SELECT database_schema, potential_features
        FROM project_thought
        WHERE id = %s
    """
    cursor.execute(select_query, (project_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()

    if not result:
        return None

    schema, features = result
    return schema, features

def mermaid_to_image(mermaid_code):
    text_bytes = mermaid_code.encode("utf-8")
    base64_bytes = base64.b64encode(text_bytes)
    base64_string = base64_bytes.decode("utf-8")
    url = f"https://mermaid.ink/img/{base64_string}"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception("Failed to generate diagram image")
    return base64.b64encode(response.content).decode("utf-8")

def _cleanup_files(paths: list[str]):
    for p in paths:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass

@app.get("/generate-diagrams/{project_id}")
def generate_diagrams(project_id: int, background_tasks: BackgroundTasks):
    result = get_database_schema(project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")

    schema, features = result
    schema_text = json.dumps(schema, indent=2)
    features_text = json.dumps(features, indent=2)

    # ER prompt
    er_prompt = f"""You are a software architect.Generate Mermaid ER diagram code.DATABASE SCHEMA:{schema_text}FEATURES:{features_text}Return ONLY Mermaid ER diagram code."""
    er_response = query({
        "messages": [{"role": "user", "content": er_prompt}],
        "model": "zai-org/GLM-5:novita"
    })
    er_code = er_response["choices"][0]["message"]["content"]
    er_code = er_code.replace("```mermaid", "").replace("```", "").strip()
    er_image = mermaid_to_image(er_code)

    # Flowchart prompt
    flow_prompt = f"""You are a software architect.Generate Mermaid flowchart code.DATABASE SCHEMA:{schema_text}FEATURES:{features_text}Return ONLY Mermaid flowchart code."""
    flow_response = query({
        "messages": [{"role": "user", "content": flow_prompt}],
        "model": "zai-org/GLM-5:novita"
    })
    flow_code = flow_response["choices"][0]["message"]["content"]
    flow_code = flow_code.replace("```mermaid", "").replace("```", "").strip()
    flow_image = mermaid_to_image(flow_code)

    # Write images to temp files and return as a single FileResponse (zip)
    tmp_dir = tempfile.gettempdir()
    uid = uuid.uuid4().hex

    er_path = os.path.join(tmp_dir, f"er_diagram_{uid}.png")
    flow_path = os.path.join(tmp_dir, f"flowchart_diagram_{uid}.png")
    zip_path = os.path.join(tmp_dir, f"diagrams_{uid}.zip")

    with open(er_path, "wb") as f:
        f.write(base64.b64decode(er_image))

    with open(flow_path, "wb") as f:
        f.write(base64.b64decode(flow_image))

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(er_path, arcname="er_diagram.png")
        z.write(flow_path, arcname="flowchart_diagram.png")

    background_tasks.add_task(_cleanup_files, [er_path, flow_path, zip_path])

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"project_{project_id}_diagrams.zip"
    )