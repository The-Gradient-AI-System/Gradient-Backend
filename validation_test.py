from fastapi.testclient import TestClient
from main import app
import pandas as pd
import io
import os

client = TestClient(app)

def test_query():
    print("Testing /analytics/query...")
    # Requires OpenAI API key to work fully, but we can check if it tries.
    # If no API key, it might fail or return error, but let's see.
    # Assuming the environment has the key as it was already running AI services.
    
    question = "How many rows are there?"
    response = client.post("/analytics/query", json={"question": question})
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("Response:", response.json())
    else:
        print("Error:", response.text)

def test_export():
    print("\nTesting /analytics/export...")
    response = client.get("/analytics/export")
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        content = response.content
        print(f"Content length: {len(content)} bytes")
        
        # Verify it's a valid excel file
        try:
            df = pd.read_excel(io.BytesIO(content))
            print("Successfully read Excel file.")
            print(f"Columns: {df.columns.tolist()}")
            print(f"Rows: {len(df)}")
        except Exception as e:
            print(f"Failed to read Excel content: {e}")
    else:
        print("Error:", response.text)

if __name__ == "__main__":
    # Ensure checking from the correct directory so database is found
    # db.py looks for "db/database.duckdb" relative to itself.
    # We are running this script from likely the project root or we need to be careful.
    
    # We'll just run the tests
    try:
        test_query()
        test_export()
    except Exception as e:
        print(f"Test failed with exception: {e}")
