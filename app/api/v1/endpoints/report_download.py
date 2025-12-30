from fastapi import APIRouter, HTTPException, status, Response
from app.services.report_generation_service import ReportGenerationService

router = APIRouter()
service = ReportGenerationService()

@router.get(
    "/download-report/{pdf_file_name}",
    status_code=status.HTTP_200_OK,
    summary="Descarga el PDF generado del reporte",
    description="Descarga el archivo PDF generado, dado su nombre."
)
def download_report(pdf_file_name: str):
    try:
        pdf_bytes = service.get_pdf_file(pdf_file_name)
        if not pdf_bytes:
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        return Response(content=pdf_bytes, media_type="application/pdf", headers={
            "Content-Disposition": f"attachment; filename={pdf_file_name}"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
