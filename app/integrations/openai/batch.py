
import asyncio
import json
from datetime import datetime
from app.core.config import OpenAIConfig, bigquery_config
from app.integrations.openai.review_model_response import ReviewAnalysis
import httpx
import pandas as pd
import random
import string
from google.cloud import bigquery
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

class OpenAIConcurrentIntegration:
    """Procesa reviews de BigQuery una a una usando OpenAI concurrentemente y guarda resultados en archivo."""

    def __init__(self):
        self.api_key = OpenAIConfig().get_api_key()
        self.model = OpenAIConfig().get_model()
        self.system_prompt = OpenAIConfig().batch_system_prompt()
        self.max_concurrent = int(os.getenv("OPENAI_MAX_CONCURRENT", 20))
        self.client = bigquery_config.get_client()
        self.review_his_table = bigquery_config.get_table_id("DIM_REVIEWS_HISTORICO")
        self.analysis_table_id = bigquery_config.get_table_id_with_dataset(
            "AIOutput", "Reviews_Analysis"
        )

    async def fetch_reviews(self, app_id: str, source: str = None):
        # Usa el cliente real de BigQuery si está disponible
        client = self.client
        query = f'''
            SELECT content, score, fecha
            FROM `{self.review_his_table}`
            WHERE app_id = @app_id
        '''
        query_parameters = [bigquery.ScalarQueryParameter("app_id", "STRING", app_id)]
        if source:
            query += " AND LOWER(source) = @source"
            query_parameters.append(bigquery.ScalarQueryParameter("source", "STRING", source.lower()))
        query += " ORDER BY fecha DESC"
        job_config = None
        try:
            job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        except ImportError:
            pass
        results = client.query(query, job_config=job_config).result()
        # logger.info(f"📝 Fetched {len(list(results))} reviews for app_id: {app_id} and source: {source}")
        return [(row.content, row.score, row.fecha) for row in results]

    async def analyze_review(self, review, client):
        content, score, fecha = review
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"{score}: {content}"}
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "ReviewAnalysis",
                    "strict": True,
                    "schema": ReviewAnalysis.model_json_schema()
                }
            }
        }
        try:
            resp = await client.post(url, headers=headers, json=body, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return {
                "review_texto": content,
                "review_rating": score,
                "review_fecha": str(fecha),
                "openai_response": data
            }
        except Exception as e:
            return {
                "review_texto": content,
                "review_rating": score,
                "review_fecha": str(fecha),
                "error": str(e)
            }

    async def process_reviews_concurrently(self, app_id: str, source: str = None):
        """Procesa reviews concurrentemente y guarda resultados en BigQuery."""

        reviews = await self.fetch_reviews(app_id, source)
        results = []
        sem = asyncio.Semaphore(self.max_concurrent)
        analyzed_at = datetime.utcnow()

        async with httpx.AsyncClient() as client:
            async def sem_task(review):
                async with sem:
                    return await self.analyze_review(review, client)
            tasks = [sem_task(review) for review in reviews]
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)

        # Construir DataFrame para bulk insert
        def generar_codigo():
            numbers = "".join(random.choices(string.digits, k=6))
            return f"ra{numbers}"

        rows = []
        for r in results:
            # Si hubo error, no insertamos
            if "error" in r:
                continue
            rows.append({
                "analysis_id": generar_codigo(),
                "app_id": app_id,
                "json_data": json.dumps(r["openai_response"], ensure_ascii=False),
                "analyzed_at": analyzed_at,
                "review_date": r["review_fecha"]
            })

        if not rows:
            return []

        df = pd.DataFrame(rows)

        # Convertir tipos
        df["analyzed_at"] = pd.to_datetime(df["analyzed_at"])
        df["review_date"] = pd.to_datetime(df["review_date"]).dt.date

        # Insertar en BigQuery
        bq_client = bigquery.Client()
        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_APPEND",
        )
        job = bq_client.load_table_from_dataframe(df, self.analysis_table_id, job_config=job_config)
        job.result()

        return rows
