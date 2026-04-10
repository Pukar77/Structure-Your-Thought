import os
import requests
from dotenv import load_dotenv
import json
from fastapi import FastAPI
from pydantic import BaseModel
from database import get_connection_string

app = FastAPI()

class UserInput(BaseModel):
    raw_input:str

load_dotenv()
token = os.getenv("HF_TOKEN")



API_URL = "https://router.huggingface.co/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

@app.post("/app/generate")
def generate_structure(request:UserInput):
    payload = {
        "messages": [
            {
                "role": "system",
                "content": """
    You are a senior software architect, AI engineer, and system designer.

    Your task is to convert unstructured user ideas into a complete, technically structured JSON blueprint for building a production-ready software system.
    


    Return strictly this JSON structure:
    {
    "problem_statement": "",
    "catchy_titles": [],
    "potential_features": [],
    "recommended_tech_stack": {
        "frontend": "",
        "backend": "",
        "database": "",
        "ai_models": [],
        "other_tools": []
    },
    "system_architecture": "",
    "database_schema": {
        "tables": []
    },
    "api_endpoints": [],
    "folder_structure": "",
    "monetization_suggestions": []
    }
    
    Some important rules:
    Return strictly valid JSON only.
    Do not wrap in markdown.
    Ensure JSON is syntactically valid.
    No trailing commas.
    No empty objects.
    """
            },
            {
                "role": "user",
                "content": f"Convert this raw idea into structured JSON:\n{request.raw_input}"
            }
        ],
        "model": "mistralai/Mistral-7B-Instruct-v0.2:featherless-ai"
    }

    response = requests.post(API_URL, headers=headers, json=payload)
    data = response.json()


    model_output = data["choices"][0]["message"]["content"]

    #Connection with our database
    conn = get_connection_string()

    cursor = conn.cursor()

    #inserting into database
    insert_query = """insert into project_thought ( problem_statement, catchy_titles, potential_features,frontend, backend, database, ai_models, other_tools,system_architecture, database_schema, api_endpoints,folder_structure, monetization_suggestions) values(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;"""

    # Parse the string response into a dict
    try:
        clean = model_output.strip().removeprefix("```json").removesuffix("```").strip()
        model_output_json = json.loads(clean)
    except json.JSONDecodeError as e:
        print("Failed to parse model response as JSON:", e)
        print("Raw output:", model_output)

    # Now use model_output_json (the dict) everywhere below
    tech_stack = model_output_json.get("recommended_tech_stack", {})

    cursor.execute(
        insert_query,
        (
            model_output_json.get("problem_statement"),
            json.dumps(model_output_json.get("catchy_titles", [])),
            json.dumps(model_output_json.get("potential_features", [])),
            tech_stack.get("frontend"),
            tech_stack.get("backend"),
            tech_stack.get("database"),
            json.dumps(tech_stack.get("ai_models", [])),
            json.dumps(tech_stack.get("other_tools", [])),
            model_output_json.get("system_architecture"),
            json.dumps(model_output_json.get("database_schema", {})),
            json.dumps(model_output_json.get("api_endpoints", [])),
            model_output_json.get("folder_structure"),
            json.dumps(model_output_json.get("monetization_suggestions", []))
        )
    )

    new_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    cursor.close()

    print(f"Structured idea saved to database with id={new_id}")
    return {
        "project_id":new_id
    }




