import pandas as pd
import io
import duckdb
from db import conn
from openai import OpenAI
import os
from dotenv import load_dotenv
import re

load_dotenv()

client = OpenAI()
AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")

def get_messages_df() -> pd.DataFrame:
    """Attributes: gmail_id, first_name, last_name, email, subject, company, body, etc."""
    # We use the existing duckdb connection to fetch the dataframe
    return conn.execute("SELECT * FROM gmail_messages").df()

def execute_pandas_query(question: str) -> str:
    """
    1. Loads data from DuckDB into a DataFrame.
    2. Asks AI to write pandas code to answer 'question'.
    3. Executes the code and returns the result.
    """
    df = get_messages_df()
    
    # We want the AI to think the dataframe is named 'df'.
    # We'll provide the columns to help it write correct code.
    columns_info = ", ".join(df.columns)
    
    system_prompt = (
        "You are a Python data analyst helper. "
        "You are given a pandas DataFrame named 'df' containing email leads. "
        f"Columns: {columns_info}. "
        "User will ask a question about this data. "
        "You must generate ONLY the python code (no markdown, no triple backticks) "
        "that calculates the answer and stores it in a variable named 'result'. "
        "Do not print anything. Just set 'result'. "
        "If the result is a dataframe or series, 'result' should be that object. "
        "If the question cannot be answered with the data, set 'result' to a string explaining why."
    )
    
    response = client.chat.completions.create(
        model=AI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0,
    )
    
    code = response.choices[0].message.content.strip()
    
    # Simple cleanup if the model still outputs backticks
    code = re.sub(r"^```python", "", code, flags=re.MULTILINE)
    code = re.sub(r"^```", "", code, flags=re.MULTILINE)
    code = code.strip()
    
    # Execution context
    local_vars = {"df": df, "pd": pd}
    
    try:
        exec(code, {}, local_vars)
        result = local_vars.get("result", "No result variable set by generated code.")
        
        # Format the result for display
        if isinstance(result, (pd.DataFrame, pd.Series)):
            return result.to_markdown()
        return str(result)
        
    except Exception as e:
        return f"Error executing generated code:\n{code}\n\nException: {e}"

def export_leads_to_excel() -> io.BytesIO:
    """
    Exports the gmail_messages table to an Excel file in memory.
    """
    df = get_messages_df()
    output = io.BytesIO()
    
    # Use 'xlsxwriter' or 'openpyxl' as engine. default is commonly openpyxl for xlsx.
    # We'll stick to default and assume openpyxl is installed.
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Leads")
        
    output.seek(0)
    return output
