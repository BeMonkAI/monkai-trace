"""Session management with timeout support"""

import time
import logging
from typing import Optional, Dict
from threading import Lock, Thread, Event
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Gerencia sessões com timeout de inatividade.
    
    Features:
    - Timeout configurável (default: 120 segundos)
    - Thread-safe para ambientes multi-threaded
    - Auto-limpeza de sessões expiradas via daemon thread
    - Suporte a user_id customizado
    """
    
    def __init__(self, inactivity_timeout: int = 120, auto_cleanup_interval: int = 300):
        """
        Args:
            inactivity_timeout: Segundos de inatividade para considerar sessão fechada
            auto_cleanup_interval: Intervalo em segundos para limpeza automática (0 = desabilitado)
        """
        self.inactivity_timeout = inactivity_timeout
        self._sessions: Dict[str, Dict] = {}
        self._lock = Lock()
        self._shutdown_event = Event()
        
        if auto_cleanup_interval > 0:
            self._cleanup_thread = Thread(
                target=self._auto_cleanup_loop,
                args=(auto_cleanup_interval,),
                daemon=True
            )
            self._cleanup_thread.start()
    
    def _auto_cleanup_loop(self, interval: int) -> None:
        """Background loop that periodically cleans up expired sessions."""
        while not self._shutdown_event.wait(timeout=interval):
            removed = self.cleanup_expired()
            if removed > 0:
                logger.debug(f"Auto-cleanup removed {removed} expired sessions")
    
    def shutdown(self) -> None:
        """Signal the cleanup thread to stop."""
        self._shutdown_event.set()
    
    def get_or_create_session(
        self, 
        user_id: str, 
        namespace: str,
        force_new: bool = False
    ) -> str:
        """
        Retorna session_id existente ou cria nova se:
        - Não existe sessão para este user_id
        - Sessão existente expirou (> inactivity_timeout)
        - force_new=True
        
        Returns:
            session_id no formato: {namespace}-{user_id}-{timestamp_inicio}
        """
        with self._lock:
            current_time = time.time()
            
            if user_id in self._sessions and not force_new:
                session_data = self._sessions[user_id]
                time_since_last = current_time - session_data['last_activity']
                
                # Sessão ainda ativa?
                if time_since_last < self.inactivity_timeout:
                    # Atualizar last_activity
                    session_data['last_activity'] = current_time
                    return session_data['session_id']
                else:
                    # Sessão expirou
                    logger.info(f"Session expired for {user_id} (inactive for {int(time_since_last)}s)")
            
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            session_id = f"{namespace}-{user_id}-{timestamp}"
            
            self._sessions[user_id] = {
                'session_id': session_id,
                'last_activity': current_time,
                'created_at': current_time
            }
            
            return session_id
    
    def update_activity(self, user_id: str) -> None:
        """Atualiza timestamp de última atividade"""
        with self._lock:
            if user_id in self._sessions:
                self._sessions[user_id]['last_activity'] = time.time()
    
    def close_session(self, user_id: str) -> None:
        """Força fechamento de sessão"""
        with self._lock:
            if user_id in self._sessions:
                del self._sessions[user_id]
    
    def cleanup_expired(self) -> int:
        """Remove sessões expiradas. Retorna número de sessões removidas."""
        with self._lock:
            current_time = time.time()
            expired = []
            
            for user_id, data in self._sessions.items():
                if current_time - data['last_activity'] > self.inactivity_timeout:
                    expired.append(user_id)
            
            for user_id in expired:
                del self._sessions[user_id]
            
            return len(expired)
    
    def get_session_info(self, user_id: str) -> Optional[Dict]:
        """Retorna informações da sessão ativa"""
        with self._lock:
            if user_id in self._sessions:
                data = self._sessions[user_id]
                return {
                    'session_id': data['session_id'],
                    'duration': time.time() - data['created_at'],
                    'inactive_for': time.time() - data['last_activity']
                }
            return None


class PersistentSessionManager(SessionManager):
    """
    SessionManager com persistência server-side.
    
    Consulta o backend MonkAI para verificar sessões ativas,
    garantindo continuidade de sessão em ambientes stateless
    (REST APIs, serverless, workers, etc.).
    
    Features:
    - Cache local para chamadas rápidas no mesmo processo
    - Fallback para backend quando cache local não tem a sessão
    - Fallback para comportamento in-memory se o backend falhar
    - Backward-compatible com SessionManager
    
    Usage:
        from monkai_trace import MonkAIClient
        from monkai_trace.session_manager import PersistentSessionManager
        
        client = MonkAIClient(tracer_token="tk_xxx")
        manager = PersistentSessionManager(client, inactivity_timeout=300)
        
        session_id = manager.get_or_create_session("user-123", "my-namespace")
    """
    
    def __init__(self, client: 'MonkAIClient', inactivity_timeout: int = 120):
        """
        Args:
            client: MonkAIClient instance (used for HTTP calls to backend)
            inactivity_timeout: Seconds of inactivity before new session
        """
        super().__init__(inactivity_timeout)
        self._client = client
    
    def get_or_create_session(
        self,
        user_id: str,
        namespace: str,
        force_new: bool = False
    ) -> str:
        """
        Retorna session_id existente ou cria nova, consultando o backend.
        
        Fluxo:
        1. Checar cache local (rápido, evita HTTP em chamadas sequenciais)
        2. Se não encontrar no cache: consultar backend (persistente)
        3. Se backend falhar: fallback para comportamento in-memory
        
        Returns:
            session_id no formato: {namespace}-{user_id}-{timestamp}
        """
        # Step 1: Check local cache first (fast path)
        with self._lock:
            if user_id in self._sessions and not force_new:
                data = self._sessions[user_id]
                if time.time() - data['last_activity'] < self.inactivity_timeout:
                    data['last_activity'] = time.time()
                    return data['session_id']
        
        # Step 2: Query backend for persistent session
        try:
            result = self._client.get_or_create_session(
                namespace=namespace,
                user_id=user_id,
                inactivity_timeout=self.inactivity_timeout,
                force_new=force_new
            )
            session_id = result['session_id']
            reused = result.get('reused', False)
            
            # Update local cache
            with self._lock:
                self._sessions[user_id] = {
                    'session_id': session_id,
                    'last_activity': time.time(),
                    'created_at': time.time()
                }
            
            action = "Reused" if reused else "Created"
            logger.info(f"PersistentSessionManager {action} session: {session_id}")
            return session_id
            
        except Exception as e:
            logger.warning(f"PersistentSessionManager server lookup failed, using local fallback: {e}")
            return super().get_or_create_session(user_id, namespace, force_new)
