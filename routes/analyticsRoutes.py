from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from service.analyticsService import execute_pandas_query, export_leads_to_excel
import io

router = APIRouter(prefix="/analytics", tags=["Analytics"])

class QueryRequest(BaseModel):
    question: str

@router.post("/query")
async def query_data(payload: QueryRequest):
    if not payload.question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    try:
        result = execute_pandas_query(payload.question)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export")
async def export_data():
    try:
        excel_buffer = export_leads_to_excel()
        
        headers = {
            'Content-Disposition': 'attachment; filename="leads_export.xlsx"'
        }
        
        return StreamingResponse(
            excel_buffer,
            headers=headers,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
