import json
import logging
import asyncio
import ast
import datetime
import re
from openai import OpenAI
from app.core.config import OpenAIConfig
from app.integrations.openai.report_generation_prompt_highchart import REPORT_GENERATION_PROMPT
from app.services.prompt_service import PromptService


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
        self.prompt_service = PromptService()
        logger.debug("[OPENAI] Servicio de prompts dinámicos inicializado")

    async def _get_prompt_template(self, prompt_key: str = "-*-") -> str:
        """
        Obtiene el template del prompt desde BigQuery.
        Si falla, usa el prompt hardcoded como fallback.
        
        Args:
            prompt_key: Identificador del tipo de prompt
            
        Returns:
            String con el template del prompt
        """
        try:
            logger.debug(f"[OPENAI] Intentando cargar prompt dinámico: key={prompt_key}")
            prompt_content = await self.prompt_service.get_active_prompt(prompt_key)
            logger.info(f"✅ [OPENAI] Prompt dinámico cargado desde BD: key={prompt_key}")
            return prompt_content
        except Exception as e:
            logger.warning(f"⚠️ [OPENAI] No se pudo cargar prompt desde BD: {e}. Usando hardcoded como fallback.")
            return REPORT_GENERATION_PROMPT
    
    def _convert_datetime(self, obj):
        """
        Recursively convert datetime objects to ISO strings in dicts/lists.
        """
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
        
    def validate_prompt(self, analytics_data=None, agent_config=None, data_window=None, analytics_explanation=""):
        """
        Valida el template del prompt de OpenAI sin hacer la petición, para evitar gastar tokens.
        """
        logger.info(f"🛠️ [PROMPT VALIDATION] Validando el template del prompt de OpenAI...")
        analytics_data = self._convert_datetime(analytics_data or [{"fecha": "2025-12-30", "nombre_campana": "Test"}])
        agent_config = self._convert_datetime(agent_config or {"id": "test", "user_id": "user"})
        data_window = self._convert_datetime(data_window or {"data_window": {}})
        analytics_json = json.dumps(analytics_data)
        config_json = json.dumps(agent_config)
        data_window_json = json.dumps(data_window)
        logger.info("[PROMPT VALIDATION] Validando el template del prompt...")
        logger.debug(f"[PROMPT VALIDATION] analytics_json: {analytics_json}")
        logger.debug(f"[PROMPT VALIDATION] config_json: {config_json}")
        logger.debug(f"[PROMPT VALIDATION] data_window_json: {data_window_json}")
        try:
            # Obtener prompt dinámico o fallback
            prompt_template = asyncio.run(self._get_prompt_template())
            prompt = prompt_template.format(
                analytics_data=analytics_json,
                report_config=config_json,
                data_window=data_window_json,
                analytics_explanation=analytics_explanation
            )
            logger.info("[PROMPT VALIDATION] El template del prompt se construyó correctamente.")
            logger.debug(f"[PROMPT VALIDATION] Prompt ejemplo: {prompt[:1000]}")
            return True
        except Exception as e:
            logger.error(f"[PROMPT VALIDATION] Error al construir el prompt: {e}")
            return False
    
    def generate_report(self, analytics_data, agent_config, data_window=None, analytics_explanation=""):
        logger.info("📝 [OPENAI] Generando reporte con OpenAI...")
        """
        Generate a report using OpenAI API.
        Args:
            analytics_data: List of analytics dicts
            agent_config: Dict with agent configuration
            data_window: Dict with data window info (optional)
            analytics_explanation: Provider-specific description of the data format,
                dictionary and block rules (injected into prompt)
        Returns:
            Structured JSON response from OpenAI
        """
        # Convert all datetimes to strings before serializing
        analytics_data = self._convert_datetime(analytics_data)
        agent_config = self._convert_datetime(agent_config)
        data_window = self._convert_datetime(data_window)

        analytics_json = json.dumps(analytics_data, ensure_ascii=False)
        config_json = json.dumps(agent_config, ensure_ascii=False)
        data_window_json = json.dumps(data_window, ensure_ascii=False)

        # Agrega un log aqui siempre antes de la llamada a OpenAI
        logger.debug(f"📝 [OPENAI] Preparando prompt con datos: analytics_data={analytics_json[:200]}..., report_config={config_json[:1000]}..., data_window={data_window_json[:200]}...")
        logger.debug(f"[OPENAI] Longitudes: analytics_json={len(analytics_json)}, config_json={len(config_json)}, data_window_json={len(data_window_json)}")
        logger.info(f"[OPENAI] report_config completo: {config_json}")

        try:
            # Obtener prompt dinámico o fallback
            prompt_template = asyncio.run(self._get_prompt_template())
            prompt = prompt_template.format(
                analytics_data=analytics_json,
                report_config=config_json,
                data_window=data_window_json,
                analytics_explanation=analytics_explanation
            )
            logger.debug(f"[OPENAI] Longitud del prompt final: {len(prompt)}")
        except Exception as e:
            logger.error(f"❌ [OPENAI] Error al construir el prompt: {e}")
            logger.error(f"[OPENAI] analytics_json={analytics_json[:500]} ...")
            logger.error(f"[OPENAI] config_json={config_json[:500]} ...")
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
                max_completion_tokens=16384
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
                logger.error(f"❌ [OPENAI] Respuesta truncada por límite de tokens. finish_reason={finish_reason}. req_id={req_id}")
                logger.error(f"[OPENAI] Respuesta parcial: {raw_content[:500]}...")
                raise RuntimeError(f"La respuesta de OpenAI fue truncada (finish_reason={finish_reason}). Necesita aumentar max_completion_tokens o simplificar el prompt.")
            logger.debug(f"📝 [OPENAI] Respuesta cruda: {raw_content[:1000]}{'...' if len(raw_content) > 1000 else ''}")

            try:
                result = json.loads(raw_content)
            except Exception as e1:
                logger.warning(f"⚠️ [OPENAI] Error al parsear JSON directo: {e1}. Intentando limpiar la respuesta...")
                cleaned = raw_content.strip()
                cleaned = re.sub(r'^```(?:json)?\s*$|^```$', '', cleaned, flags=re.MULTILINE)
                try:
                    result = json.loads(cleaned)
                except Exception as e2:
                    logger.error(f"❌ [OPENAI] Error al parsear respuesta OpenAI tras limpiar: {e2}. Respuesta: {cleaned[:1000]}")
                    raise RuntimeError(f"No se pudo parsear la respuesta de OpenAI como JSON: {e2}")
            # Si el resultado es un string que parece JSON, intenta decodificar recursivamente
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
