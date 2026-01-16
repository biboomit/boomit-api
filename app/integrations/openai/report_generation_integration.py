import json
import logging
from openai import OpenAI
from app.core.config import OpenAIConfig
from app.integrations.openai.report_generation_prompt import REPORT_GENERATION_PROMPT


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# Asegura que siempre haya al menos un handler
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

class OpenAIReportGenerationIntegration:
    """
    Integration class for generating intelligent reports using OpenAI API.
    This class sends a single request with all the context (analytics, agent config, chart contracts, rules)
    and expects a structured JSON response for the report.
    """
    def __init__(self):
        logger.info("🤖 [OPENAI] Inicializando integración OpenAIReportGenerationIntegration")
        self.api_key = OpenAIConfig().get_api_key()
        self.client = OpenAI(api_key=self.api_key)
        self.model = OpenAIConfig().get_model()

    def _convert_datetime(self, obj):
        """
        Recursively convert datetime objects to ISO strings in dicts/lists.
        """
        import datetime
        if isinstance(obj, dict):
            return {k: self._convert_datetime(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_datetime(i) for i in obj]
        elif isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.date):
            return obj.isoformat()
        else:
            return obj
        
    def validate_prompt(self, analytics_data=None, agent_config=None, chart_contracts=None, global_rules=None, data_window=None):
        """
        Valida el template del prompt de OpenAI sin hacer la petición, para evitar gastar tokens.
        """
        logger.info(f"🛠️ [PROMPT VALIDATION] Validando el template del prompt de OpenAI...")
        analytics_data = self._convert_datetime(analytics_data or [{"fecha": "2025-12-30", "nombre_campana": "Test"}])
        agent_config = self._convert_datetime(agent_config or {"id": "test", "user_id": "user"})
        chart_contracts = self._convert_datetime(chart_contracts or {"index": {}})
        global_rules = self._convert_datetime(global_rules or {"global_rules": {}})
        data_window = self._convert_datetime(data_window or {"data_window": {}})
        analytics_json = json.dumps(analytics_data)
        config_json = json.dumps(agent_config)
        chart_contracts_json = json.dumps(chart_contracts)
        global_rules_json = json.dumps(global_rules)
        data_window_json = json.dumps(data_window)
        logger.info("[PROMPT VALIDATION] Validando el template del prompt...")
        logger.debug(f"[PROMPT VALIDATION] analytics_json: {analytics_json}")
        logger.debug(f"[PROMPT VALIDATION] config_json: {config_json}")
        logger.debug(f"[PROMPT VALIDATION] chart_contracts_json: {chart_contracts_json}")
        logger.debug(f"[PROMPT VALIDATION] global_rules_json: {global_rules_json}")
        logger.debug(f"[PROMPT VALIDATION] data_window_json: {data_window_json}")
        try:
            prompt = REPORT_GENERATION_PROMPT.format(
                analytics_data=analytics_json,
                report_config=config_json,
                chart_contracts=chart_contracts_json,
                global_rules=global_rules_json,
                data_window=data_window_json
            )
            logger.info("[PROMPT VALIDATION] El template del prompt se construyó correctamente.")
            logger.debug(f"[PROMPT VALIDATION] Prompt ejemplo: {prompt[:1000]}")
            return True
        except Exception as e:
            logger.error(f"[PROMPT VALIDATION] Error al construir el prompt: {e}")
            return False
    
    def generate_report(self, analytics_data, agent_config, chart_contracts, global_rules, data_window=None):
        logger.info("📝 [OPENAI] Generando reporte con OpenAI...")
        """
        Generate a report using OpenAI API.
        Args:
            analytics_data: List of analytics dicts
            agent_config: Dict with agent configuration
            chart_contracts: Dict with chart contracts and index
            global_rules: Dict with global rules
            data_window: Dict with data window info (optional)
        Returns:
            Structured JSON response from OpenAI
        """
        # Convert all datetimes to strings before serializing
        analytics_data = self._convert_datetime(analytics_data)
        agent_config = self._convert_datetime(agent_config)
        chart_contracts = self._convert_datetime(chart_contracts)
        global_rules = self._convert_datetime(global_rules)
        data_window = self._convert_datetime(data_window)

        analytics_json = json.dumps(analytics_data, ensure_ascii=False)
        config_json = json.dumps(agent_config, ensure_ascii=False)
        chart_contracts_json = json.dumps(chart_contracts, ensure_ascii=False)
        global_rules_json = json.dumps(global_rules, ensure_ascii=False)
        data_window_json = json.dumps(data_window, ensure_ascii=False)

        # Agrega un log aqui siempre antes de la llamada a OpenAI
        logger.debug(f"📝 [OPENAI] Preparando prompt con datos: analytics_data={analytics_json[:200]}..., report_config={config_json[:1000]}..., chart_contracts={chart_contracts_json[:200]}..., global_rules={global_rules_json[:200]}..., data_window={data_window_json[:200]}...")
        logger.debug(f"[OPENAI] Longitudes: analytics_json={len(analytics_json)}, config_json={len(config_json)}, chart_contracts_json={len(chart_contracts_json)}, global_rules_json={len(global_rules_json)}, data_window_json={len(data_window_json)}")
        logger.info(f"[OPENAI] report_config completo: {config_json}")

        try:
            prompt = REPORT_GENERATION_PROMPT.format(
                analytics_data=analytics_json,
                report_config=config_json,
                chart_contracts=chart_contracts_json,
                global_rules=global_rules_json,
                data_window=data_window_json
            )
            logger.debug(f"[OPENAI] Longitud del prompt final: {len(prompt)}")
        except Exception as e:
            logger.error(f"❌ [OPENAI] Error al construir el prompt: {e}")
            logger.error(f"[OPENAI] analytics_json={analytics_json[:500]} ...")
            logger.error(f"[OPENAI] config_json={config_json[:500]} ...")
            logger.error(f"[OPENAI] chart_contracts_json={chart_contracts_json[:500]} ...")
            logger.error(f"[OPENAI] global_rules_json={global_rules_json[:500]} ...")
            logger.error(f"[OPENAI] data_window_json={data_window_json[:500]} ...")
            raise

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Eres un generador de reportes de datos para analistas. Responde solo en JSON estructurado."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_completion_tokens=4000
            )
            req_id = getattr(response, "request_id", None)
            logger.info(f"✅ [OPENAI] Respuesta recibida de OpenAI req_id={req_id}")

            # Guard rails: evitar parsear respuestas vacías o truncadas
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            raw_content = choice.message.content
            if not raw_content:
                safe_resp = getattr(response, "model_dump", None)
                as_dict = safe_resp() if callable(safe_resp) else str(response)
                logger.error(f"❌ [OPENAI] Respuesta sin content. req_id={req_id} response={str(as_dict)[:2000]}")
                raise RuntimeError("Respuesta de OpenAI vacía; no se pudo obtener JSON")
            if finish_reason and finish_reason != "stop":
                logger.warning(f"⚠️ [OPENAI] finish_reason={finish_reason}, posible truncamiento. req_id={req_id} raw_preview={raw_content[:400]}")
            logger.debug(f"📝 [OPENAI] Respuesta cruda: {raw_content[:1000]}{'...' if len(raw_content) > 1000 else ''}")

            try:
                result = json.loads(raw_content)
            except Exception as e1:
                logger.warning(f"⚠️ [OPENAI] Error al parsear JSON directo: {e1}. Intentando limpiar la respuesta...")
                import re
                cleaned = raw_content.strip()
                cleaned = re.sub(r'^```(?:json)?\s*$|^```$', '', cleaned, flags=re.MULTILINE)
                try:
                    result = json.loads(cleaned)
                except Exception as e2:
                    logger.error(f"❌ [OPENAI] Error al parsear respuesta OpenAI tras limpiar: {e2}. Respuesta: {cleaned[:1000]}")
                    raise RuntimeError(f"No se pudo parsear la respuesta de OpenAI como JSON: {e2}")
            # Si el resultado es un string que parece JSON, intenta decodificar recursivamente
            import ast
            max_attempts = 3
            attempts = 0
            while isinstance(result, str) and attempts < max_attempts:
                try:
                    result = json.loads(result)
                except Exception:
                    try:
                        # Como fallback, intenta con ast.literal_eval si es posible
                        result = ast.literal_eval(result)
                    except Exception:
                        break
                attempts += 1
            logger.debug(f"[OPENAI FINAL RESULT] type={type(result)}, value={str(result)[:1000]}")
            if isinstance(result, str):
                logger.error(f"❌ [OPENAI] Respuesta sigue siendo string tras varios intentos: {result[:1000]}")
                raise RuntimeError("La respuesta de OpenAI no es un JSON válido tras varios intentos de decodificación.")
            if not isinstance(result, dict):
                logger.error(f"❌ [OPENAI] Respuesta final no es un dict: {type(result)}: {str(result)[:1000]}")
                raise RuntimeError(f"La respuesta de OpenAI no es un dict: {type(result)}: {str(result)[:1000]}")
            return result
        except Exception as api_exc:
            logger.error(f"❌ [OPENAI] Error al comunicarse con OpenAI API: {api_exc}")
            raise RuntimeError(f"Error al comunicarse con OpenAI API: {api_exc}")
