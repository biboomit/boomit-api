import json
from openai import OpenAI
from app.core.config import OpenAIConfig
from app.integrations.openai.report_generation_prompt import REPORT_GENERATION_PROMPT

class OpenAIReportGenerationIntegration:
    """
    Integration class for generating intelligent reports using OpenAI API.
    This class sends a single request with all the context (analytics, agent config, chart contracts, rules)
    and expects a structured JSON response for the report.
    """
    def __init__(self):
        self.api_key = OpenAIConfig().get_api_key()
        self.client = OpenAI(api_key=self.api_key)
        self.model = OpenAIConfig().get_model()

    def generate_report(self, analytics_data, agent_config, chart_contracts, global_rules):
        """
        Generate a report using OpenAI API.
        Args:
            analytics_data: List of analytics dicts
            agent_config: Dict with agent configuration
            chart_contracts: Dict with chart contracts and index
            global_rules: Dict with global rules
        Returns:
            Structured JSON response from OpenAI
        """
        # Prepare prompt
        analytics_json = json.dumps(analytics_data, ensure_ascii=False)
        config_json = json.dumps(agent_config, ensure_ascii=False)
        chart_contracts_json = json.dumps(chart_contracts, ensure_ascii=False)
        global_rules_json = json.dumps(global_rules, ensure_ascii=False)
        prompt = REPORT_GENERATION_PROMPT.format(
            analytics_data=analytics_json,
            report_config=config_json,
            chart_contracts=chart_contracts_json,
            global_rules=global_rules_json
        )
        # Call OpenAI API
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Eres un generador de reportes de datos para analistas. Responde solo en JSON estructurado."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=4000
        )
        # Parse and return structured JSON
        return json.loads(response.choices[0].message.content)
