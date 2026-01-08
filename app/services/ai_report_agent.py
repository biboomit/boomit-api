from typing import List
from uuid import uuid4
from datetime import datetime
import json
from app.core.config import bigquery_config
from app.schemas.ai_report_agent import AIReportAgentCreate, AIReportAgentInDB
from google.cloud import bigquery
import os

class AIReportAgentService:
    def __init__(self):
        self.client = bigquery_config.get_client()
        self.table =  bigquery_config.get_table_id("DIM_AI_REPORT_AGENT_CONFIGS")

    def count_user_agents(self, user_id: str) -> int:
        query = f"SELECT COUNT(*) as count FROM `{self.table}` WHERE user_id = @user_id"
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("user_id", "STRING", user_id)]
        )
        result = self.client.query(query, job_config=job_config).result()
        return list(result)[0]["count"]

    def create_agent(self, agent: AIReportAgentCreate, user_id: str) -> AIReportAgentInDB:
        if self.count_user_agents(user_id) >= 5:
            raise ValueError("Máximo 5 agentes por usuario")
        now = datetime.utcnow()
        row = {
            "id": agent.id,
            "user_id": user_id,
            "agent_name": agent.agent_name,
            "company": agent.company,
            "config_context": json.dumps(agent.config_context),
            "attribution_source": agent.attribution_source,
            "marketing_funnel": json.dumps(agent.marketing_funnel),
            "color_palette": agent.color_palette.json(),
            "logo_base64": agent.logo_base64,
            "selected_blocks": json.dumps(agent.selected_blocks),
            "blocks_config": json.dumps([b.dict() for b in agent.blocks_config]),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        errors = self.client.insert_rows_json(self.table, [row])
        if errors:
            raise RuntimeError(f"Error al guardar: {errors}")
        # Deserialize for response
        response_row = row.copy()
        for field in ["config_context", "marketing_funnel", "color_palette", "selected_blocks", "blocks_config"]:
            if isinstance(response_row.get(field), str):
                response_row[field] = json.loads(response_row[field])
        return AIReportAgentInDB(**response_row)

    def list_agents(self, user_id: str) -> List[AIReportAgentInDB]:
        query = f"SELECT * FROM `{self.table}` WHERE user_id = @user_id ORDER BY created_at DESC LIMIT 5"
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("user_id", "STRING", user_id)]
        )
        result = self.client.query(query, job_config=job_config).result()
        agents = []
        for row in result:
            agent = dict(row)
            # Deserialize only if value is a string (defensive)
            for field in ["config_context", "marketing_funnel", "color_palette", "selected_blocks", "blocks_config"]:
                if isinstance(agent.get(field), str):
                    agent[field] = json.loads(agent[field])
            agents.append(AIReportAgentInDB(**agent))
        return agents
