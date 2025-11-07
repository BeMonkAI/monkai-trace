"""Session management with timeout support"""

import time
from typing import Optional, Dict
from threading import Lock
from datetime import datetime, timedelta


class SessionManager:
    """
    Gerencia sessões com timeout de inatividade.
    
    Features:
    - Timeout configurável (default: 120 segundos)
    - Thread-safe para ambientes multi-threaded
    - Auto-limpeza de sessões expiradas
    - Suporte a user_id customizado
    """
    
    def __init__(self, inactivity_timeout: int = 120):
        """
        Args:
            inactivity_timeout: Segundos de inatividade para considerar sessão fechada
        """
        self.inactivity_timeout = inactivity_timeout
        self._sessions: Dict[str, Dict] = {}  # user_id -> {session_id, last_activity}
        self._lock = Lock()
    
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
                    print(f"[SessionManager] Session expired for {user_id} (inactive for {int(time_since_last)}s)")
            
            # Criar nova sessão
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
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
