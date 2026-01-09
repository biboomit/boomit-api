"""
Cliente para obtener tokens de identidad de GCP para invocar servicios Cloud Run.
"""
import logging
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2 import id_token

logger = logging.getLogger(__name__)


class GCPIdentityTokenClient:
    """
    Cliente para generar tokens de identidad (ID tokens) para autenticar
    peticiones a servicios Cloud Run u otros recursos protegidos de GCP.
    """
    
    def __init__(self):
        """Inicializa el cliente."""
        pass
        
    def get_identity_token(self, target_audience: str) -> Optional[str]:
        """
        Obtiene un token de identidad para el audience especificado.
        
        Args:
            target_audience: URL del servicio destino (ej: https://my-service.run.app)
            
        Returns:
            Token de identidad o None si no se pudo obtener
        """
        try:
            # Usar id_token.fetch_id_token que funciona tanto en local como en GKE/Cloud Run
            auth_req = Request()
            token = id_token.fetch_id_token(auth_req, target_audience)
            logger.info(f"[IDENTITY TOKEN] Token obtenido exitosamente para audience: {target_audience}")
            return token
                
        except Exception as e:
            logger.error(f"[IDENTITY TOKEN] Error al obtener token para {target_audience}: {e}")
            return None
    
    def get_authorized_headers(self, target_audience: str) -> dict:
        """
        Obtiene headers HTTP con el token de autorización incluido.
        
        Args:
            target_audience: URL del servicio destino
            
        Returns:
            Diccionario con headers, incluyendo Authorization si hay token
        """
        headers = {}
        token = self.get_identity_token(target_audience)
        if token:
            headers['Authorization'] = f'Bearer {token}'
        return headers
