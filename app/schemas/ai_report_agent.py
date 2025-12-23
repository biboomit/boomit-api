from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime

class ColorPalette(BaseModel):
    primary: str
    secondary: str
    accent: str
    neutral: str

class BlockConfig(BaseModel):
    block_key: str
    title: Optional[str]
    description: Optional[str]
    logo_base64: Optional[str]
    analysis_dates_from: Optional[str]
    analysis_dates_to: Optional[str]

class AIReportAgentCreate(BaseModel):
    agent_name: str
    company: str
    general_context: str
    attribution_source: str
    marketing_funnel: List[str]
    color_palette: ColorPalette
    logo_base64: str
    selected_blocks: List[str]
    blocks_config: List[BlockConfig]

class AIReportAgentInDB(AIReportAgentCreate):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
